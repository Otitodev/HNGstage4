import os
import json
import logging
import pika
import firebase_admin
from firebase_admin import messaging
from firebase_admin import credentials
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class PushNotificationService:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self.firebase_credentials_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
        
        # Initialize Firebase Admin SDK
        try:
            if os.path.exists(self.firebase_credentials_path):
                cred = credentials.Certificate(self.firebase_credentials_path)
                self.firebase_app = firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully")
            else:
                logger.warning("Firebase credentials not found. Push notifications will be simulated.")
                self.firebase_app = None
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            self.firebase_app = None
        
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
                routing_key='push'  # Same routing key as the original queue
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
                queue='push.queue',
                durable=True,
                passive=True
            )
            logger.info("Using existing 'push.queue' with current settings")
        except pika.exceptions.ChannelClosedByBroker as e:
            # If queue doesn't exist, create it with our settings
            if 'PRECONDITION_FAILED' in str(e):
                logger.info("Creating 'push.queue' with DLX settings")
                self.channel.queue_declare(
                    queue='push.queue',
                    durable=True,
                    arguments={
                        'x-dead-letter-exchange': 'notifications.dlx',
                        'x-dead-letter-routing-key': 'push'
                    }
                )
            else:
                raise
        self.channel.queue_bind(
            exchange='notifications.direct',
            queue='push.queue',
            routing_key='push'
        )
        
        logger.info("Push Notification Service initialized and connected to RabbitMQ")
    
    def send_push_notification(self, token: str, title: str, body: str, data: dict = None):
        """Send a push notification using Firebase Cloud Messaging"""
        try:
            if not self.firebase_app:
                logger.info(f"[SIMULATED] Sending push to {token}: {title} - {body}")
                return True
                
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=token,
                data=data or {}
            )
            
            response = messaging.send(message)
            logger.info(f"Push notification sent successfully: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send push notification: {str(e)}")
            return False
    
    def process_message(self, ch, method, properties, body):
        """Process incoming messages from RabbitMQ"""
        try:
            message = json.loads(body)
            notification_id = message.get('notification_id', 'unknown')
            logger.info(f"Processing push notification: {notification_id}")
            
            # Extract push notification details
            tokens = message.get('target', [])
            if isinstance(tokens, str):
                tokens = [tokens]  # Convert single token to list
                
            title = message.get('title', 'New Notification')
            body = message.get('body', '')
            data = message.get('data', {})
            
            # Send to all provided tokens
            success_count = 0
            for token in tokens:
                if self.send_push_notification(token, title, body, data):
                    success_count += 1
            
            if success_count > 0:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Successfully sent {success_count}/{len(tokens)} push notifications")
            else:
                # Negative acknowledgement - requeue the message
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                logger.error(f"Failed to send push notifications for: {notification_id}")
                
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
                                'queue': 'push.queue',
                                'time': None,
                                'exchange': 'notifications.direct',
                                'routing-keys': ['push']
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
        logger.info("Starting push notification service consumer...")
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue='push.queue',
            on_message_callback=self.process_message,
            auto_ack=False
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Stopping push notification service...")
            self.connection.close()

if __name__ == "__main__":
    # Start the push notification service
    service = PushNotificationService()
    service.start_consuming()
