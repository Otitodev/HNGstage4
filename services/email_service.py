import os
import json
import logging
import pika
from typing import Optional, Dict, Any
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import BasicProperties

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@example.com')
        
        if not self.sendgrid_api_key:
            raise ValueError("SENDGRID_API_KEY environment variable is required")
            
        self.sendgrid_client = SendGridAPIClient(self.sendgrid_api_key)
        
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
        
        # Set up dead letter queue
        self.channel.queue_declare(
            queue='failed.queue',
            durable=True,
            arguments={
                'x-message-ttl': 86400000,  # 24 hours in milliseconds
                'x-max-length': 10000
            }
        )
        
        # Bind DLQ to DLX
        self.channel.queue_bind(
            exchange='notifications.dlx',
            queue='failed.queue',
            routing_key='email'
        )
        
        # Set up main queue with DLX
        self.channel.queue_declare(
            queue='email.queue',
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'notifications.dlx',
                'x-dead-letter-routing-key': 'email'
            }
        )
        
        # Bind main queue to exchange
        self.channel.queue_bind(
            exchange='notifications.direct',
            queue='email.queue',
            routing_key='notify.email'
        )
        
    def send_email(
        self,
        to_email: str,
        subject: str,
        content: str,
        template_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an email using SendGrid
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            content: Email content (HTML)
            template_id: Optional SendGrid template ID
            data: Optional template data
            
        Returns:
            Dict containing status and status code
        """
        try:
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
            response = self.sendgrid_client.send(mail)
            logger.info(f"Email sent to {to_email} with subject '{subject}'")
            
            return {
                'status': 'success',
                'status_code': response.status_code,
                'message_id': response.headers.get('X-Message-Id')
            }
            
        except Exception as e:
            error_msg = f"Failed to send email to {to_email}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise

    def _move_to_dlq(self, channel: BlockingChannel, method, properties: BasicProperties, body: bytes, error: str):
        """
        Move a failed message to the Dead Letter Queue
        
        Args:
            channel: RabbitMQ channel
            method: Delivery method
            properties: Message properties
            body: Message body
            error: Error message
        """
        try:
            # Publish to DLQ
            channel.basic_publish(
                exchange='notifications.dlx',
                routing_key='email',
                body=body,
                properties=properties
            )
            
            # Acknowledge the original message to remove it from the queue
            channel.basic_ack(delivery_tag=method.delivery_tag)
            
            logger.error(f"Moved message to DLQ: {error}")
            
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
            logger.debug(f"Processing message: {message}")
            
            # Basic validation
            required_fields = ['to', 'subject', 'content']
            if not all(field in message for field in required_fields):
                raise ValueError(f"Missing required fields. Required: {required_fields}")
            
            # Send email
            response = self.send_email(
                to_email=message['to'],
                subject=message['subject'],
                content=message['content'],
                template_id=message.get('template_id'),
                data=message.get('data')
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
            self.channel.stop_consuming()
            
        except Exception as e:
            logger.error(f"Error in consumer: {str(e)}", exc_info=True)
            self.channel.stop_consuming()
            
        finally:
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
