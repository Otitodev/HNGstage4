import pika
import os
from dotenv import load_dotenv

# Load My environment variables
load_dotenv()

# --- Connection Setup ---
url = os.getenv("RABBITMQ_URL")
if not url:
    print("Error: RABBITMQ_URL environment variable is not set.")
    exit(1)

try:
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
except pika.exceptions.AMQPConnectionError as e:
    print(f"Error connecting to RabbitMQ: {e}")
    exit(1)

print("--- Initializing RabbitMQ Topology ---")

# --- 1. Dead Letter Exchange (DLX) Setup ---
# This exchange receives messages that fail permanently from the main queues.
DLX_EXCHANGE = "notifications.dlx"
DLQ_QUEUE = "failed.queue"

channel.exchange_declare(
    exchange=DLX_EXCHANGE, 
    exchange_type="fanout", # fanout simply routes to all bound queues
    durable=True
)

# Declare the Dead Letter Queue (DLQ)
channel.queue_declare(
    queue=DLQ_QUEUE, 
    durable=True
)
# The DLQ is bound to the DLX (it catches everything the DLX sends)
channel.queue_bind(
    exchange=DLX_EXCHANGE, 
    queue=DLQ_QUEUE
)

# --- 2. Main Exchange Setup ---
MAIN_EXCHANGE = "notifications.direct"
channel.exchange_declare(
    exchange=MAIN_EXCHANGE, 
    exchange_type="direct", 
    durable=True
)


# --- 3. Main Queues Setup (with DLQ arguments) ---

# Arguments to set the Dead Letter Exchange for the main queues
dlq_args = {
    "x-dead-letter-exchange": DLX_EXCHANGE,
    # Optional: x-dead-letter-routing-key can be used here if needed, 
    # but since DLX is fanout, we don't need it.
}

# Declare Email Queue and link it to the DLX
channel.queue_declare(
    queue="email.queue", 
    durable=True, 
    arguments=dlq_args
)

# Declare Push Queue and link it to the DLX
channel.queue_declare(
    queue="push.queue", 
    durable=True, 
    arguments=dlq_args
)


# --- 4. Bindings (Using Correct Routing Keys) ---
# Routing keys that match the system design document: notify.email and notify.push

# Bind Email Queue
channel.queue_bind(
    exchange=MAIN_EXCHANGE, 
    queue="email.queue", 
    routing_key="notify.email" # routing key
)

# Bind Push Queue
channel.queue_bind(
    exchange=MAIN_EXCHANGE, 
    queue="push.queue", 
    routing_key="notify.push" # routing key
)

print("✅ RabbitMQ topology setup completed!")
print(f"   Main Exchange: {MAIN_EXCHANGE}")
print(f"   Email Key: notify.email -> email.queue")
print(f"   Push Key: notify.push -> push.queue")
print(f"   Dead Letter Queue (DLQ): {DLQ_QUEUE}")

connection.close()