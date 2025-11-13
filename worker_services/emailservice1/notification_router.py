"""
Notification Router Service

Consumes messages from the 'notifications' queue (published by API Gateway)
and routes them to appropriate queues (email.queue, push.queue) based on
the notification channels specified in the message.
"""
import os
import json
import logging
import pika
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NotificationRouter:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        
        # Set up RabbitMQ connection
        self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare the main exchange
        self.channel.exchange_declare(
            exchange='notifications.direct',
            exchange_type='direct',
            durable=True
        )
        
        # Ensure input queue exists (where API gateway publishes)
        try:
            self.channel.queue_declare(queue='notifications', durable=True, passive=True)
            logger.info("Using existing 'notifications' queue")
        except:
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='notifications.direct', exchange_type='direct', durable=True)
            self.channel.queue_declare(queue='notifications', durable=True)
            logger.info("Created 'notifications' queue")
        
        # Ensure output queues exist (use passive to check first)
        try:
            self.channel.queue_declare(queue='email.queue', durable=True, passive=True)
            logger.info("Using existing 'email.queue'")
        except:
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='notifications.direct', exchange_type='direct', durable=True)
            self.channel.queue_declare(queue='email.queue', durable=True)
            logger.info("Created 'email.queue'")
            
        try:
            self.channel.queue_declare(queue='push.queue', durable=True, passive=True)
            logger.info("Using existing 'push.queue'")
        except:
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='notifications.direct', exchange_type='direct', durable=True)
            self.channel.queue_declare(queue='push.queue', durable=True)
            logger.info("Created 'push.queue'")
        
        # Bind output queues to exchange
        self.channel.queue_bind(
            exchange='notifications.direct',
            queue='email.queue',
            routing_key='notify.email'
        )
        
        self.channel.queue_bind(
            exchange='notifications.direct',
            queue='push.queue',
            routing_key='notify.push'
        )
        
        logger.info("Notification Router initialized and connected to RabbitMQ")
    
    def route_notification(self, message_data):
        """
        Route notification to appropriate queues based on delivery targets
        
        Expected message format from API Gateway:
        {
            "user_id": "...",
            "delivery_targets": {
                "email": "user@example.com",
                "phone": "+1234567890"
            },
            "user_preferences": {...},
            "rendered_content": {
                "subject": "...",
                "body": "...",
                "html": "..."
            },
            "metadata": {
                "template_key": "...",
                "preferred_language": "en"
            }
        }
        """
        user_id = message_data.get('user_id', 'unknown')
        delivery_targets = message_data.get('delivery_targets', {})
        rendered_content_raw = message_data.get('rendered_content', {})
        metadata = message_data.get('metadata', {})
        user_preferences = message_data.get('user_preferences', {})
        
        # Extract actual content from template service response
        # Template service returns: {"success": true, "data": {"subject": "...", "body": "...", "html_body": "..."}}
        if isinstance(rendered_content_raw, dict) and 'data' in rendered_content_raw:
            rendered_content = rendered_content_raw.get('data', {})
        else:
            rendered_content = rendered_content_raw
        
        routed_count = 0
        
        # Route to email queue if email target exists
        email_address = delivery_targets.get('email')
        if email_address:
            # Extract content - try different field names
            email_content = (
                rendered_content.get('html_body') or  # Template service uses 'html_body'
                rendered_content.get('html') or 
                rendered_content.get('body') or 
                rendered_content.get('content') or
                ''
            )
            
            email_subject = rendered_content.get('subject', 'Notification')
            
            logger.debug(f"Rendered content keys: {list(rendered_content.keys())}")
            logger.debug(f"Email subject: {email_subject}")
            logger.debug(f"Email content length: {len(email_content)}")
            
            if not email_content:
                logger.warning(f"No email content found in rendered_content: {rendered_content}")
            
            email_message = {
                'notification_id': user_id,
                'user_id': user_id,
                'to': email_address,
                'subject': email_subject,
                'content': email_content,
                'template_id': None,  # Already rendered by template service
                'data': {
                    'template_key': metadata.get('template_key'),
                    'language': metadata.get('preferred_language', 'en')
                }
            }
            
            self.channel.basic_publish(
                exchange='notifications.direct',
                routing_key='notify.email',
                body=json.dumps(email_message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            logger.info(f"Routed notification for user {user_id} to email.queue ({email_address})")
            routed_count += 1
        
        # Route to push queue if phone/FCM token exists
        phone_number = delivery_targets.get('phone')
        fcm_token = user_preferences.get('fcm_token')  # Assuming FCM token might be in preferences
        
        if phone_number or fcm_token:
            push_message = {
                'notification_id': user_id,
                'user_id': user_id,
                'target': fcm_token or phone_number,  # Use FCM token if available, otherwise phone
                'title': rendered_content.get('subject', 'Notification'),
                'body': rendered_content.get('body', ''),
                'data': {
                    'template_key': metadata.get('template_key'),
                    'language': metadata.get('preferred_language', 'en'),
                    'user_id': user_id
                }
            }
            
            self.channel.basic_publish(
                exchange='notifications.direct',
                routing_key='notify.push',
                body=json.dumps(push_message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            logger.info(f"Routed notification for user {user_id} to push.queue")
            routed_count += 1
        
        return routed_count
    
    def process_message(self, ch, method, properties, body):
        """Process incoming messages from the notifications queue"""
        try:
            message = json.loads(body)
            notification_id = message.get('notification_id', 'unknown')
            
            logger.info(f"📬 Processing notification: {notification_id}")
            logger.debug(f"Full message: {json.dumps(message, indent=2)}")
            
            # Route the notification
            routed_count = self.route_notification(message)
            
            if routed_count > 0:
                # Acknowledge the message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Successfully routed notification {notification_id} to {routed_count} queue(s)")
            else:
                # No channels specified, acknowledge anyway to remove from queue
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.warning(f"No channels specified for notification {notification_id}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON message: {str(e)}")
            # Acknowledge to remove bad message from queue
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            # Negative acknowledgement - requeue the message
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """Start consuming messages from the notifications queue"""
        logger.info("Starting notification router consumer...")
        
        # Configure quality of service
        self.channel.basic_qos(prefetch_count=1)
        
        # Set up consumer
        self.channel.basic_consume(
            queue='notifications',
            on_message_callback=self.process_message,
            auto_ack=False
        )
        
        try:
            logger.info("Waiting for notifications. To exit press CTRL+C")
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Stopping notification router...")
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
    # Start the notification router
    router = NotificationRouter()
    router.start_consuming()
