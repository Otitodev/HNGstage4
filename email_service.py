import os
import json
import logging
import pika
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class EmailService:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@example.com')
        self.sendgrid_client = SendGridAPIClient(self.sendgrid_api_key) if self.sendgrid_api_key else None
        
        # Set up RabbitMQ connection
        self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare the dead letter exchange as fanout (must match existing type)
        self.channel.exchange_declare(
            exchange='notifications.dlx',
            exchange_type='fanout',  # Changed to match existing exchange type
            durable=True
        )
        
        # Declare the main exchange
        self.channel.exchange_declare(
            exchange='notifications.direct',
            exchange_type='direct',
            durable=True
        )
        
        # Try to declare the dead letter queue with passive=True to check if it exists
        try:
            self.channel.queue_declare(
                queue='failed.queue',
                durable=True,
                passive=True  # Just check if queue exists
            )
            logger.info("Using existing 'failed.queue' with current settings")
        except pika.exceptions.ChannelClosedByBroker as e:
            # Queue doesn't exist or has different parameters, create it with our settings
            if 'PRECONDITION_FAILED' in str(e):
                logger.info("Creating 'failed.queue' with TTL and max length settings")
                self.channel.queue_declare(
                    queue='failed.queue',
                    durable=True,
                    arguments={
                        'x-message-ttl': 86400000,  # 24 hours in milliseconds
                        'x-max-length': 10000  # Max number of messages in DLQ
                    }
                )
            else:
                raise
                
        # Bind the queue to the DLX
        try:
            self.channel.queue_bind(
                exchange='notifications.dlx',
                queue='failed.queue',
                routing_key='email'  # Same routing key as the original queue
            )
        except pika.exceptions.ChannelClosedByBroker as e:
            if 'PRECONDITION_FAILED' in str(e):
                logger.warning("Failed to bind 'failed.queue' to 'notifications.dlx'. It may already be bound.")
            else:
                raise
        
        # Declare the main queue with DLX configuration
        try:
            # First try to declare with passive=True to check if it exists
            self.channel.queue_declare(
                queue='email.queue',
                durable=True,
                passive=True
            )
            logger.info("Using existing 'email.queue' with current settings")
        except pika.exceptions.ChannelClosedByBroker as e:
            # If queue doesn't exist, create it with our settings
            if 'PRECONDITION_FAILED' in str(e):
                logger.info("Creating 'email.queue' with DLX settings")
                self.channel.queue_declare(
                    queue='email.queue',
                    durable=True,
                    arguments={
                        'x-dead-letter-exchange': 'notifications.dlx',
                        'x-dead-letter-routing-key': 'email'
                    }
                )
            else:
                raise
        self.channel.queue_bind(
            exchange='notifications.direct',
            queue='email.queue',
            routing_key='email'
        )
        
        logger.info("Email Service initialized and connected to RabbitMQ")
    
    def send_email(self, to_email: str, subject: str, body: str, html_body: str = None):
        """Send an email using SendGrid API"""
        if not self.sendgrid_client:
            logger.warning("SendGrid API key not configured. Email sending is disabled.")
            logger.info(f"[SIMULATED] Email to {to_email} with subject: {subject}")
            return True
            
        try:
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                plain_text_content=body,
                html_content=html_body or body
            )
            
            response = self.sendgrid_client.send(message)
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Email sent to {to_email} with subject: {subject}")
                return True
            else:
                logger.error(f"Failed to send email. Status: {response.status_code}, Body: {response.body}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def process_message(self, ch, method, properties, body):
        """Process incoming messages from RabbitMQ"""
        try:
            message = json.loads(body)
            logger.info(f"Processing email notification: {message.get('notification_id')}")
            
            # Extract email details from message
            to_email = message.get('target')
            subject = message.get('subject', 'No Subject')
            body = message.get('body', '')
            html_body = message.get('html_body')
            
            # Send the email
            success = self.send_email(to_email, subject, body, html_body)
            
            if success:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Successfully processed notification: {message.get('notification_id')}")
            else:
                # Negative acknowledgement - requeue the message
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                logger.error(f"Failed to send email for notification: {message.get('notification_id')}")
                
                # Move to dead letter queue
                self.channel.basic_publish(
                    exchange='',
                    routing_key='failed.queue',
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # make message persistent
                        headers={
                            'x-death': [{
                                'count': 1,
                                'reason': 'rejected',
                                'queue': 'email.queue',
                                'time': None,
                                'exchange': 'notifications.direct',
                                'routing-keys': ['email']
                            }]
                        }
                    )
                )
                
        except json.JSONDecodeError:
            logger.error("Failed to decode message, discarding")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def start_consuming(self):
        """Start consuming messages from the queue"""
        logger.info("Starting email service consumer...")
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue='email.queue',
            on_message_callback=self.process_message,
            auto_ack=False
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Stopping email service...")
            self.connection.close()

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
