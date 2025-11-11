import pika
import os
import json
from dotenv import load_dotenv

load_dotenv()

# --- Configuration (Must match your .env file) ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_IN = "notifications"

def check_queue():
    """Connects to RabbitMQ, gets one message, prints it, and ACKs."""
    print(f"Connecting to RabbitMQ at {RABBITMQ_URL}")
    
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        
        # Ensure the queue exists
        channel.queue_declare(queue=QUEUE_IN, durable=True)

        # Get one message (non-blocking)
        method_frame, properties, body = channel.basic_get(queue=QUEUE_IN, auto_ack=False)

        if method_frame:
            print("\n✅ SUCCESS: Message retrieved from queue.\n")
            print("-" * 50)
            
            # Decode and pretty-print the JSON payload
            payload = json.loads(body.decode('utf-8'))
            print(json.dumps(payload, indent=4))
            
            print("-" * 50)
            
            # Acknowledge the message so it is removed from the queue
            channel.basic_ack(method_frame.delivery_tag)
            connection.close()
            
        else:
            print(f"❌ FAILURE: No messages in queue '{QUEUE_IN}'.")
            connection.close()

    except pika.exceptions.AMQPConnectionError as e:
        print(f"\n❌ ERROR: Could not connect to RabbitMQ. Check URL and server status. Error: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: An unexpected error occurred: {e}")

if __name__ == "__main__":
    check_queue()