import json
import os
import sys
import uuid
from datetime import datetime

import pika
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Load environment variables
load_dotenv()

class NotificationTester:
    def __init__(self):
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
        self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare the exchange as durable to match existing configuration
        self.channel.exchange_declare(
            exchange='notifications.direct', 
            exchange_type='direct',
            durable=True  # Match existing exchange configuration
        )
        
        # Declare queues with DLX configuration to match existing setup
        dlx_args = {
            'x-dead-letter-exchange': 'notifications.dlx'
        }
        
        # Try to declare email queue with passive=True first
        try:
            self.channel.queue_declare(
                queue='email.queue',
                durable=True,
                passive=True  # Just check if queue exists
            )
        except pika.exceptions.ChannelClosedByBroker as e:
            if 'PRECONDITION_FAILED' in str(e):
                # If queue doesn't exist, create it with DLX settings
                self.channel.queue_declare(
                    queue='email.queue',
                    durable=True,
                    arguments=dlx_args
                )
            else:
                raise
                
        # Try to declare push queue with passive=True first
        try:
            self.channel.queue_declare(
                queue='push.queue',
                durable=True,
                passive=True  # Just check if queue exists
            )
        except pika.exceptions.ChannelClosedByBroker as e:
            if 'PRECONDITION_FAILED' in str(e):
                # If queue doesn't exist, create it with DLX settings
                self.channel.queue_declare(
                    queue='push.queue',
                    durable=True,
                    arguments=dlx_args
                )
            else:
                raise
        
        # Bind queues to exchange with correct routing keys
        self.channel.queue_bind(
            exchange='notifications.direct', 
            queue='email.queue', 
            routing_key='notify.email'  # Using the correct routing key from rabbitmq.py
        )
        self.channel.queue_bind(
            exchange='notifications.direct', 
            queue='push.queue', 
            routing_key='notify.push'  # Using the correct routing key from rabbitmq.py
        )
        
        print("Notification Tester initialized. Ready to send test notifications.")
    
    def send_email_notification(self, to_email, subject, body, html_body=None):
        """Send a test email notification"""
        message = {
            "notification_id": str(uuid.uuid4()),
            "type": "email",
            "target": to_email,
            "subject": subject,
            "body": body,
            "html_body": html_body or f"<p>{body}</p>",  # Simple HTML fallback
            "metadata": {
                "sent_at": datetime.utcnow().isoformat(),
                "test": True,
                "service": "sendgrid"
            }
        }
        
        self.channel.basic_publish(
            exchange='notifications.direct',
            routing_key='notify.email',  # Updated to match the binding
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type='application/json'
            )
        )
        
        print(f"Sent email notification to {to_email} with ID: {message['notification_id']}")
    
    def send_push_notification(self, token, title, body, data=None):
        """Send a test push notification"""
        message = {
            "notification_id": str(uuid.uuid4()),
            "type": "push",
            "target": [token],
            "title": title,
            "body": body,
            "data": data or {},
            "metadata": {
                "sent_at": datetime.utcnow().isoformat(),
                "test": True
            }
        }
        
        self.channel.basic_publish(
            exchange='notifications.direct',
            routing_key='notify.push',  # Updated to match the binding
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type='application/json'
            )
        )
        
        print(f"Sent push notification to device {token} with ID: {message['notification_id']}")
    
    def close(self):
        """Close the connection"""
        self.connection.close()

if __name__ == "__main__":
    tester = NotificationTester()
    
    try:
        while True:
            print("\nChoose an option:")
            print("1. Send test email")
            print("2. Send test push notification")
            print("3. Exit")
            
            choice = input("Enter your choice (1-3): ")
            
            if choice == "1":
                to_email = input("Enter recipient email: ")
                subject = input("Enter email subject: ") or "Test Email from Notification System"
                body = input("Enter email body (plain text): ") or "This is a test email from the notification system."
                
                # Ask if they want to provide HTML content
                use_html = input("Include HTML content? (y/n, default: n): ").lower() == 'y'
                html_body = None
                if use_html:
                    html_body = input("Enter HTML content (or press Enter to use auto-generated HTML): ")
                    if not html_body:
                        # Simple HTML fallback
                        html_body = f"""
                        <html>
                            <body>
                                <h1>{subject}</h1>
                                <p>{body}</p>
                                <p><em>This is an automated message. Please do not reply.</em></p>
                            </body>
                        </html>
                        """
                
                print(f"\nSending email to: {to_email}")
                print(f"Subject: {subject}")
                print("-" * 50)
                tester.send_email_notification(to_email, subject, body, html_body)
                print("\nEmail queued successfully! Check the email service logs for details.")
                
            elif choice == "2":
                token = input("Enter device token (or press Enter to use a test token): ") or "test-device-token-123"
                title = input("Enter notification title: ") or "Test Notification"
                body = input("Enter notification body: ") or "This is a test notification"
                
                # Add some test data
                data = {
                    "type": "test_notification",
                    "timestamp": datetime.utcnow().isoformat(),
                    "click_action": "https://example.com/notifications"
                }
                
                print(f"\nSending push to token: {token}")
                print(f"Title: {title}")
                print(f"Body: {body}")
                print("-" * 50)
                tester.send_push_notification(token, title, body, data)
                print("\nPush notification queued successfully! Check the push service logs for details.")
                
            elif choice == "3":
                print("Exiting...")
                break
                
            else:
                print("Invalid choice. Please try again.")
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        tester.close()
