import os
import json
import logging
import pika
import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import BasicProperties
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
RETRY_INTERVAL = 60  # Check failed queue every 60 seconds

# Database setup
Base = declarative_base()

class EmailNotificationLog(Base):
    """Model for email notifications log"""
    __tablename__ = 'email_notifications_log'
    
    id = Column(Integer, primary_key=True)
    notification_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False, index=True)
    subject = Column(Text, nullable=False)
    template_key = Column(String(100))
    status = Column(String(50), nullable=False, index=True)
    sendgrid_message_id = Column(String(255))
    sendgrid_status_code = Column(Integer)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    extra_data = Column('metadata', JSON)  # Use 'metadata' as column name but 'extra_data' as attribute
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = Column(DateTime)
    failed_at = Column(DateTime)

class EmailService:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@example.com')
        
        if not self.sendgrid_api_key:
            raise ValueError("SENDGRID_API_KEY environment variable is required")
            
        self.sendgrid_client = SendGridAPIClient(self.sendgrid_api_key)
        
        # Initialize database connection
        self.db_url = os.getenv('NEON_DATABASE_URL')
        if self.db_url:
            try:
                self.engine = create_engine(
                    self.db_url,
                    poolclass=NullPool,  # Use NullPool for better connection handling
                    pool_pre_ping=True,  # Verify connections before using
                    connect_args={'sslmode': 'require'}
                )
                self.SessionLocal = sessionmaker(bind=self.engine)
                
                # Create tables if they don't exist
                Base.metadata.create_all(self.engine)
                logger.info("✓ Database connection established")
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                self.engine = None
                self.SessionLocal = None
        else:
            logger.warning("No database URL provided, email logging will be disabled")
            self.engine = None
            self.SessionLocal = None
        
        # Set up RabbitMQ connection
        self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare the dead letter exchange
        self.channel.exchange_declare(
            exchange='notifications.dlx',
            exchange_type='fanout',
            durable=True
        )
        
        # Declare the main exchange
        self.channel.exchange_declare(
            exchange='notifications.direct',
            exchange_type='direct',
            durable=True
        )
        
        # Set up dead letter queue (try with passive first to check if exists)
        try:
            self.channel.queue_declare(queue='failed.queue', durable=True, passive=True)
            logger.info("Using existing 'failed.queue'")
        except:
            # Queue doesn't exist, create it
            self.channel = self.connection.channel()  # Recreate channel after error
            self.channel.exchange_declare(exchange='notifications.dlx', exchange_type='fanout', durable=True)
            self.channel.queue_declare(queue='failed.queue', durable=True)
            logger.info("Created 'failed.queue'")
        
        # Bind DLQ to DLX
        try:
            self.channel.queue_bind(
                exchange='notifications.dlx',
                queue='failed.queue',
                routing_key='email'
            )
        except:
            logger.warning("Could not bind failed.queue to DLX")
        
        # Set up main queue with DLX (try with passive first)
        try:
            self.channel.queue_declare(queue='email.queue', durable=True, passive=True)
            logger.info("Using existing 'email.queue'")
        except:
            # Queue doesn't exist, create it
            self.channel = self.connection.channel()  # Recreate channel after error
            self.channel.exchange_declare(exchange='notifications.direct', exchange_type='direct', durable=True)
            self.channel.queue_declare(
                queue='email.queue',
                durable=True,
                arguments={
                    'x-dead-letter-exchange': 'notifications.dlx',
                    'x-dead-letter-routing-key': 'email'
                }
            )
            logger.info("Created 'email.queue'")
        
        # Bind main queue to exchange
        try:
            self.channel.queue_bind(
                exchange='notifications.direct',
                queue='email.queue',
                routing_key='notify.email'
            )
        except:
            logger.warning("Could not bind email.queue to exchange")
        
        # Also ensure the 'notifications' queue exists (used by API gateway)
        try:
            self.channel.queue_declare(queue='notifications', durable=True, passive=True)
            logger.info("Using existing 'notifications' queue")
        except:
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue='notifications', durable=True)
            logger.info("Created 'notifications' queue")
        
        # Create a permanent DLQ for messages that exceed max retries
        try:
            self.channel.queue_declare(queue='email.dlq', durable=True, passive=True)
            logger.info("Using existing 'email.dlq'")
        except:
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue='email.dlq', durable=True)
            logger.info("Created 'email.dlq' for permanently failed messages")
        
        logger.info("Email Service initialized and connected to RabbitMQ")
        
        # Start retry worker thread
        self.retry_running = True
        self.retry_thread = threading.Thread(target=self._retry_worker, daemon=True)
        self.retry_thread.start()
        logger.info(f"Started retry worker (checks every {RETRY_INTERVAL}s, max {MAX_RETRIES} retries)")
        
    def _log_to_database(self, notification_id: str, user_id: str, recipient_email: str, 
                         subject: str, status: str, **kwargs):
        """Log email notification to database"""
        if not self.SessionLocal:
            return  # Database not configured
        
        try:
            session = self.SessionLocal()
            
            log_entry = EmailNotificationLog(
                notification_id=notification_id,
                user_id=user_id,
                recipient_email=recipient_email,
                subject=subject,
                status=status,
                template_key=kwargs.get('template_key'),
                sendgrid_message_id=kwargs.get('sendgrid_message_id'),
                sendgrid_status_code=kwargs.get('sendgrid_status_code'),
                retry_count=kwargs.get('retry_count', 0),
                error_message=kwargs.get('error_message'),
                extra_data=kwargs.get('metadata'),
                sent_at=kwargs.get('sent_at'),
                failed_at=kwargs.get('failed_at')
            )
            
            session.add(log_entry)
            session.commit()
            session.close()
            
            logger.debug(f"Logged notification {notification_id} to database with status: {status}")
            
        except Exception as e:
            logger.error(f"Failed to log to database: {e}")
            try:
                session.close()
            except:
                pass
    
    def _retry_worker(self):
        """Background worker that periodically retries failed messages"""
        logger.info("Retry worker started")
        
        while self.retry_running:
            try:
                time.sleep(RETRY_INTERVAL)
                
                # Create a new connection for the retry worker
                retry_connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                retry_channel = retry_connection.channel()
                
                # Check how many messages are in failed queue
                failed_queue = retry_channel.queue_declare(queue='failed.queue', durable=True, passive=True)
                message_count = failed_queue.method.message_count
                
                if message_count > 0:
                    logger.info(f"Found {message_count} messages in failed.queue, attempting retry...")
                    
                    retried = 0
                    moved_to_dlq = 0
                    
                    # Process each message
                    for _ in range(message_count):
                        method_frame, properties, body = retry_channel.basic_get(queue='failed.queue', auto_ack=False)
                        
                        if method_frame is None:
                            break
                        
                        try:
                            message = json.loads(body)
                            
                            # Get retry count from headers
                            headers = properties.headers or {}
                            retry_count = headers.get('x-retry-count', 0)
                            last_error = headers.get('x-last-error', 'Unknown error')
                            
                            if retry_count >= MAX_RETRIES:
                                # Move to permanent DLQ
                                retry_channel.basic_publish(
                                    exchange='',
                                    routing_key='email.dlq',
                                    body=body,
                                    properties=pika.BasicProperties(
                                        delivery_mode=2,
                                        headers={
                                            'x-retry-count': retry_count,
                                            'x-last-error': last_error,
                                            'x-final-failure-time': int(time.time())
                                        }
                                    )
                                )
                                retry_channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                                moved_to_dlq += 1
                                logger.warning(f"Message exceeded {MAX_RETRIES} retries, moved to email.dlq. Last error: {last_error}")
                            else:
                                # Retry: republish to email.queue with incremented retry count
                                retry_channel.basic_publish(
                                    exchange='notifications.direct',
                                    routing_key='notify.email',
                                    body=body,
                                    properties=pika.BasicProperties(
                                        delivery_mode=2,
                                        content_type='application/json',
                                        headers={
                                            'x-retry-count': retry_count + 1,
                                            'x-last-error': last_error
                                        }
                                    )
                                )
                                retry_channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                                retried += 1
                                logger.info(f"Retrying message (attempt {retry_count + 1}/{MAX_RETRIES})")
                        
                        except Exception as e:
                            logger.error(f"Error processing failed message: {e}")
                            retry_channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)
                    
                    if retried > 0:
                        logger.info(f"✓ Retried {retried} messages from failed.queue")
                    if moved_to_dlq > 0:
                        logger.warning(f"⚠ Moved {moved_to_dlq} messages to email.dlq (exceeded max retries)")
                
                retry_connection.close()
                
            except Exception as e:
                logger.error(f"Error in retry worker: {e}")
                time.sleep(10)  # Wait before retrying
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        content: str,
        template_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        notification_id: str = None,
        user_id: str = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Send an email using SendGrid and log to database
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            content: Email content (HTML)
            template_id: Optional SendGrid template ID
            data: Optional template data
            notification_id: Notification ID for tracking
            user_id: User ID for tracking
            retry_count: Current retry attempt
            
        Returns:
            Dict containing status and status code
        """
        try:
            logger.debug(f"Preparing email: to={to_email}, subject={subject}, from={self.from_email}")
            logger.debug(f"Content length: {len(content) if content else 0} chars")
            
            # Prepare email
            mail = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=content
            )
            
            # Add template if provided
            if template_id:
                mail.template_id = template_id
                if data:
                    mail.dynamic_template_data = data
            
            # Send the email
            logger.debug(f"Sending email via SendGrid...")
            response = self.sendgrid_client.send(mail)
            message_id = response.headers.get('X-Message-Id')
            
            logger.info(f"✓ Email sent to {to_email} with subject '{subject}' (status: {response.status_code})")
            
            # Log success to database
            self._log_to_database(
                notification_id=notification_id or 'unknown',
                user_id=user_id or 'unknown',
                recipient_email=to_email,
                subject=subject,
                status='sent',
                sendgrid_message_id=message_id,
                sendgrid_status_code=response.status_code,
                template_key=data.get('template_key') if data else None,
                retry_count=retry_count,
                metadata=data,
                sent_at=datetime.utcnow()
            )
            
            return {
                'status': 'success',
                'status_code': response.status_code,
                'message_id': message_id
            }
            
        except Exception as e:
            # Get detailed error information
            error_details = {
                'to_email': to_email,
                'subject': subject,
                'from_email': self.from_email,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
            
            # Try to get more details from SendGrid error
            if hasattr(e, 'body'):
                try:
                    error_body = json.loads(e.body) if isinstance(e.body, (str, bytes)) else e.body
                    error_details['sendgrid_errors'] = error_body.get('errors', [])
                except:
                    error_details['sendgrid_body'] = str(e.body)
            
            if hasattr(e, 'status_code'):
                error_details['status_code'] = e.status_code
            
            logger.error(f"✗ Failed to send email: {json.dumps(error_details, indent=2)}")
            
            # Log failure to database
            self._log_to_database(
                notification_id=notification_id or 'unknown',
                user_id=user_id or 'unknown',
                recipient_email=to_email,
                subject=subject,
                status='failed',
                error_message=str(e)[:500],
                template_key=data.get('template_key') if data else None,
                retry_count=retry_count,
                metadata=data,
                failed_at=datetime.utcnow()
            )
            
            raise

    def _move_to_dlq(self, channel: BlockingChannel, method, properties: BasicProperties, body: bytes, error: str):
        """
        Move a failed message to the Dead Letter Queue (failed.queue) for retry
        
        Args:
            channel: RabbitMQ channel
            method: Delivery method
            properties: Message properties
            body: Message body
            error: Error message
        """
        try:
            # Get current retry count from headers
            headers = properties.headers or {}
            retry_count = headers.get('x-retry-count', 0)
            
            # Publish to failed.queue with retry metadata
            channel.basic_publish(
                exchange='notifications.dlx',
                routing_key='email',
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json',
                    headers={
                        'x-retry-count': retry_count,
                        'x-last-error': str(error)[:500],  # Limit error message length
                        'x-failed-time': int(time.time())  # Convert to integer
                    }
                )
            )
            
            # Acknowledge the original message to remove it from the queue
            channel.basic_ack(delivery_tag=method.delivery_tag)
            
            logger.error(f"Moved message to failed.queue (retry {retry_count}/{MAX_RETRIES}): {error}")
            
        except Exception as e:
            logger.error(f"Failed to move message to DLQ: {str(e)}", exc_info=True)
            # Nack the message if we can't move it to DLQ
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def process_message(self, channel: BlockingChannel, method, properties: BasicProperties, body: bytes):
        """
        Process a message from RabbitMQ
        
        Args:
            channel: RabbitMQ channel
            method: Delivery method
            properties: Message properties
            body: Message body (JSON string)
        """
        try:
            message = json.loads(body)
            logger.info(f"📨 Received message: {json.dumps(message, indent=2)}")
            
            # Basic validation
            required_fields = ['to', 'subject', 'content']
            missing_fields = [f for f in required_fields if f not in message or not message[f]]
            
            if missing_fields:
                raise ValueError(f"Missing or empty required fields: {missing_fields}. Message: {message}")
            
            logger.info(f"Sending email to {message['to']} with subject: {message['subject']}")
            
            # Get retry count from headers
            headers = properties.headers or {}
            retry_count = headers.get('x-retry-count', 0)
            
            # Send email
            response = self.send_email(
                to_email=message['to'],
                subject=message['subject'],
                content=message['content'],
                template_id=message.get('template_id'),
                data=message.get('data'),
                notification_id=message.get('notification_id'),
                user_id=message.get('user_id'),
                retry_count=retry_count
            )
            
            # Acknowledge the message
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.debug(f"Message processed successfully: {response}")
            
            return response
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON message: {str(e)}"
            logger.error(error_msg)
            self._move_to_dlq(channel, method, properties, body, error_msg)
            
        except Exception as e:
            error_msg = f"Failed to process message: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._move_to_dlq(channel, method, properties, body, error_msg)
    
    def start_consuming(self):
        """
        Start consuming messages from the queue
        
        This method will block until the consumer is stopped
        """
        logger.info("Starting email service consumer...")
        
        # Configure quality of service
        self.channel.basic_qos(prefetch_count=1)
        
        # Set up consumer
        self.channel.basic_consume(
            queue='email.queue',
            on_message_callback=self.process_message,
            auto_ack=False
        )
        
        try:
            logger.info("Waiting for messages. To exit press CTRL+C")
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Stopping email service...")
            self.retry_running = False
            self.channel.stop_consuming()
            
        except Exception as e:
            logger.error(f"Error in consumer: {str(e)}", exc_info=True)
            self.retry_running = False
            self.channel.stop_consuming()
            
        finally:
            # Stop retry worker
            self.retry_running = False
            if hasattr(self, 'retry_thread') and self.retry_thread.is_alive():
                logger.info("Waiting for retry worker to stop...")
                self.retry_thread.join(timeout=5)
            
            # Ensure clean shutdown
            if self.connection and self.connection.is_open:
                self.connection.close()
                logger.info("RabbitMQ connection closed")

if __name__ == "__main__":
    # Check for required environment variables
    if not os.getenv('SENDGRID_API_KEY'):
        logger.warning("SENDGRID_API_KEY environment variable is not set.")
        logger.warning("Email sending will be simulated.")
    
    if not os.getenv('FROM_EMAIL'):
        logger.warning("FROM_EMAIL environment variable is not set.")
        logger.warning("Using default 'noreply@example.com' as sender email.")
    
    # Start the email service
    service = EmailService()
    service.start_consuming()
