"""
Local testing script for Email and Push services
Tests the services by publishing messages to RabbitMQ
"""
import pika
import json
import time
import sys

def test_rabbitmq_connection(rabbitmq_url):
    """Test connection to RabbitMQ"""
    print("Testing RabbitMQ connection...")
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        print("✓ Successfully connected to RabbitMQ")
        connection.close()
        return True
    except Exception as e:
        print(f"✗ Failed to connect to RabbitMQ: {e}")
        return False

def publish_test_email(rabbitmq_url):
    """Publish a test email message"""
    print("\n--- Testing Email Service ---")
    
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        
        # Ensure exchange and queue exist
        channel.exchange_declare(
            exchange='notifications.direct',
            exchange_type='direct',
            durable=True
        )
        
        channel.queue_declare(
            queue='email.queue',
            durable=True
        )
        
        channel.queue_bind(
            exchange='notifications.direct',
            queue='email.queue',
            routing_key='notify.email'
        )
        
        # Create test message
        message = {
            "to": "test@example.com",
            "subject": "Test Email from Local Testing",
            "content": "<h1>Hello!</h1><p>This is a test email from your local environment.</p>"
        }
        
        # Publish message
        channel.basic_publish(
            exchange='notifications.direct',
            routing_key='notify.email',
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type='application/json'
            )
        )
        
        print(f"✓ Published test email message to queue")
        print(f"  To: {message['to']}")
        print(f"  Subject: {message['subject']}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"✗ Failed to publish email message: {e}")
        return False

def publish_test_push(rabbitmq_url):
    """Publish a test push notification message"""
    print("\n--- Testing Push Service ---")
    
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        
        # Ensure exchange and queue exist
        channel.exchange_declare(
            exchange='notifications.direct',
            exchange_type='direct',
            durable=True
        )
        
        channel.queue_declare(
            queue='push.queue',
            durable=True
        )
        
        channel.queue_bind(
            exchange='notifications.direct',
            queue='push.queue',
            routing_key='push'
        )
        
        # Create test message
        message = {
            "notification_id": "test-001",
            "target": "test-fcm-token-12345",
            "title": "Test Push Notification",
            "body": "This is a test push notification from your local environment.",
            "data": {
                "test": "true",
                "timestamp": str(time.time())
            }
        }
        
        # Publish message
        channel.basic_publish(
            exchange='notifications.direct',
            routing_key='push',
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type='application/json'
            )
        )
        
        print(f"✓ Published test push notification to queue")
        print(f"  Title: {message['title']}")
        print(f"  Body: {message['body']}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"✗ Failed to publish push message: {e}")
        return False

def check_queue_status(rabbitmq_url):
    """Check the status of queues"""
    print("\n--- Queue Status ---")
    
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()
        
        # Check email queue
        email_queue = channel.queue_declare(queue='email.queue', durable=True, passive=True)
        print(f"email.queue: {email_queue.method.message_count} messages")
        
        # Check push queue
        push_queue = channel.queue_declare(queue='push.queue', durable=True, passive=True)
        print(f"push.queue: {push_queue.method.message_count} messages")
        
        # Check failed queue
        try:
            failed_queue = channel.queue_declare(queue='failed.queue', durable=True, passive=True)
            print(f"failed.queue: {failed_queue.method.message_count} messages")
        except:
            print("failed.queue: Not created yet")
        
        connection.close()
        
    except Exception as e:
        print(f"Could not check queue status: {e}")

def main():
    """Main test function"""
    print("=" * 60)
    print("Local Service Testing Script")
    print("=" * 60)
    
    # RabbitMQ URL
    rabbitmq_url = 'amqp://guest:guest@localhost:5672/'
    
    # Test connection
    if not test_rabbitmq_connection(rabbitmq_url):
        print("\n⚠ Make sure RabbitMQ is running!")
        print("Run: docker-compose up rabbitmq")
        sys.exit(1)
    
    # Check initial queue status
    check_queue_status(rabbitmq_url)
    
    # Publish test messages
    email_success = publish_test_email(rabbitmq_url)
    push_success = publish_test_push(rabbitmq_url)
    
    # Check queue status after publishing
    check_queue_status(rabbitmq_url)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Email Service: {'✓ PASS' if email_success else '✗ FAIL'}")
    print(f"Push Service: {'✓ PASS' if push_success else '✗ FAIL'}")
    
    print("\n📝 Next Steps:")
    print("1. Start the email service: python services/email_service.py")
    print("2. Start the push service: python services/push_service.py")
    print("3. Watch the service logs to see messages being processed")
    print("4. Check RabbitMQ Management UI: http://localhost:15672 (guest/guest)")

if __name__ == "__main__":
    main()
