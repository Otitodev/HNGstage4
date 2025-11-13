# Local Testing Guide for Email & Push Services

## Overview

This guide walks you through testing your email and push notification services locally before deploying to AWS.

## Prerequisites

- Docker Desktop installed and running
- Python 3.7+ installed
- SendGrid API key (for email testing)
- Firebase credentials (optional, for push testing)

## Step 1: Set Up Environment Variables

Create or update your `.env` file:

```env
# RabbitMQ (local)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# SendGrid (get from https://sendgrid.com)
SENDGRID_API_KEY=SG.your_actual_sendgrid_api_key_here
FROM_EMAIL=noreply@yourdomain.com

# Firebase (optional - service will run in simulation mode without it)
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
```

## Step 2: Start RabbitMQ

Start RabbitMQ using Docker:

```bash
docker-compose up rabbitmq -d
```

Wait a few seconds for RabbitMQ to start, then verify:

```bash
# Check if RabbitMQ is running
docker ps | findstr rabbitmq
```

**Access RabbitMQ Management UI:**
- URL: http://localhost:15672
- Username: `guest`
- Password: `guest`

## Step 3: Install Python Dependencies

```bash
# Install dependencies for the services
pip install pika sendgrid firebase-admin python-dotenv
```

## Step 4: Test RabbitMQ Connection

Run the test script to verify RabbitMQ is working:

```bash
python test_services_local.py
```

**Expected output:**
```
============================================================
Local Service Testing Script
============================================================
Testing RabbitMQ connection...
✓ Successfully connected to RabbitMQ

--- Queue Status ---
email.queue: 0 messages
push.queue: 0 messages

--- Testing Email Service ---
✓ Published test email message to queue
  To: test@example.com
  Subject: Test Email from Local Testing

--- Testing Push Service ---
✓ Published test push notification to queue
  Title: Test Push Notification
  Body: This is a test push notification...

--- Queue Status ---
email.queue: 1 messages
push.queue: 1 messages
```

## Step 5: Start Email Service

Open a new terminal and start the email service:

```bash
python services/email_service.py
```

**Expected output:**
```
2024-11-13 10:30:00 - INFO - Starting email service consumer...
2024-11-13 10:30:00 - INFO - Waiting for messages. To exit press CTRL+C
2024-11-13 10:30:01 - INFO - Email sent to test@example.com with subject 'Test Email from Local Testing'
```

**If you see this error:**
```
ValueError: SENDGRID_API_KEY environment variable is required
```
- Make sure your `.env` file has `SENDGRID_API_KEY` set
- Verify the `.env` file is in the project root directory

**If SendGrid fails:**
- Check your API key is valid
- Verify your sender email is verified in SendGrid
- Check SendGrid dashboard for any issues

## Step 6: Start Push Service

Open another terminal and start the push service:

```bash
python services/push_service.py
```

**Expected output (with Firebase):**
```
2024-11-13 10:30:00 - INFO - Firebase Admin SDK initialized successfully
2024-11-13 10:30:00 - INFO - Push Notification Service initialized and connected to RabbitMQ
2024-11-13 10:30:00 - INFO - Starting push notification service consumer...
2024-11-13 10:30:01 - INFO - Processing push notification: test-001
2024-11-13 10:30:01 - INFO - [SIMULATED] Sending push to test-fcm-token-12345...
```

**Expected output (without Firebase - simulation mode):**
```
2024-11-13 10:30:00 - WARNING - Firebase credentials not found. Push notifications will be simulated.
2024-11-13 10:30:00 - INFO - Push Notification Service initialized and connected to RabbitMQ
2024-11-13 10:30:00 - INFO - Starting push notification service consumer...
2024-11-13 10:30:01 - INFO - [SIMULATED] Sending push to test-fcm-token-12345...
```

## Step 7: Send More Test Messages

### Test Email with Template

Create a test script `test_email_template.py`:

```python
import pika
import json

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

# Email with SendGrid template
message = {
    "to": "your-email@example.com",  # Use your real email
    "subject": "Welcome to Our Service",
    "content": "<p>Fallback content</p>",
    "template_id": "d-your-template-id",  # Optional
    "data": {
        "user_name": "John Doe",
        "verification_link": "https://example.com/verify"
    }
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(message),
    properties=pika.BasicProperties(
        delivery_mode=2,
        content_type='application/json'
    )
)

print("Email message sent!")
connection.close()
```

Run it:
```bash
python test_email_template.py
```

### Test Push Notification

Create `test_push_notification.py`:

```python
import pika
import json

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

message = {
    "notification_id": "order-123",
    "target": "your-fcm-token-here",  # Use real FCM token if testing with Firebase
    "title": "Order Confirmed",
    "body": "Your order #123 has been confirmed and is being processed.",
    "data": {
        "order_id": "123",
        "type": "order_update",
        "action": "view_order"
    }
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='push',
    body=json.dumps(message),
    properties=pika.BasicProperties(
        delivery_mode=2,
        content_type='application/json'
    )
)

print("Push notification sent!")
connection.close()
```

Run it:
```bash
python test_push_notification.py
```

## Step 8: Monitor with RabbitMQ Management UI

1. Open http://localhost:15672
2. Login with `guest` / `guest`
3. Go to **Queues** tab
4. You should see:
   - `email.queue`
   - `push.queue`
   - `failed.queue` (created after first failure)

**Check queue details:**
- Message rates (incoming/outgoing)
- Number of messages ready
- Number of messages unacknowledged
- Consumer count (should be 1 for each service)

## Step 9: Test Error Handling

### Test Invalid Email Message

```python
import pika
import json

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

# Missing required field 'subject'
invalid_message = {
    "to": "test@example.com",
    "content": "<p>Missing subject field</p>"
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(invalid_message)
)

print("Invalid message sent - should go to DLQ")
connection.close()
```

**Expected behavior:**
- Email service logs an error
- Message is moved to `failed.queue`
- Check the failed queue in RabbitMQ UI

### Test Invalid JSON

```python
import pika

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

# Send invalid JSON
channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body='this is not valid json'
)

print("Invalid JSON sent - should go to DLQ")
connection.close()
```

## Step 10: Verify Everything Works

### Checklist

- [ ] RabbitMQ is running and accessible
- [ ] Email service connects and consumes messages
- [ ] Push service connects and consumes messages
- [ ] Test email is sent successfully (check your inbox)
- [ ] Push notification is processed (simulated or real)
- [ ] Invalid messages go to dead letter queue
- [ ] Services log appropriately
- [ ] Can view queues in RabbitMQ Management UI

## Troubleshooting

### RabbitMQ Won't Start

```bash
# Check if port 5672 is already in use
netstat -ano | findstr :5672

# Stop and remove existing containers
docker-compose down
docker-compose up rabbitmq -d
```

### Email Service Can't Connect to RabbitMQ

**Error:** `pika.exceptions.AMQPConnectionError`

**Solutions:**
- Verify RabbitMQ is running: `docker ps`
- Check `RABBITMQ_URL` in `.env`
- Try: `amqp://guest:guest@localhost:5672/`

### SendGrid Errors

**Error:** `Unauthorized`
- Verify API key is correct
- Check API key has "Mail Send" permissions

**Error:** `Sender email not verified`
- Go to SendGrid → Settings → Sender Authentication
- Verify your sender email or domain

### Push Service Errors

**Error:** `Failed to initialize Firebase`
- Check `firebase-credentials.json` exists
- Verify file path in `.env`
- Service will run in simulation mode without Firebase

### Messages Not Being Consumed

**Issue:** Messages stay in queue

**Solutions:**
- Check service is running and not crashed
- Look for errors in service logs
- Verify queue bindings in RabbitMQ UI
- Restart the service

## Performance Testing

### Load Test Email Service

```python
import pika
import json
import time

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

# Send 100 test emails
for i in range(100):
    message = {
        "to": f"test{i}@example.com",
        "subject": f"Load Test Email {i}",
        "content": f"<p>This is test email number {i}</p>"
    }
    
    channel.basic_publish(
        exchange='notifications.direct',
        routing_key='notify.email',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    
    if (i + 1) % 10 == 0:
        print(f"Sent {i + 1} messages...")

print("Load test complete!")
connection.close()
```

**Monitor:**
- Service logs for processing speed
- RabbitMQ UI for message rates
- SendGrid dashboard for delivery status

## Clean Up

### Stop Services

Press `Ctrl+C` in each terminal running a service.

### Stop RabbitMQ

```bash
docker-compose down
```

### Clear Queues (Optional)

In RabbitMQ Management UI:
1. Go to **Queues** tab
2. Click on a queue
3. Click **Purge Messages**

Or via CLI:
```bash
docker exec -it <rabbitmq-container-id> rabbitmqctl purge_queue email.queue
docker exec -it <rabbitmq-container-id> rabbitmqctl purge_queue push.queue
```

## Next Steps

Once local testing is successful:

1. ✅ Services connect to RabbitMQ
2. ✅ Messages are processed correctly
3. ✅ Emails are sent via SendGrid
4. ✅ Push notifications work (simulated or real)
5. ✅ Error handling works (DLQ)

**You're ready to deploy to AWS!**

Follow the `AWS_DEPLOYMENT_GUIDE.md` for production deployment.

## Useful Commands

```bash
# Start only RabbitMQ
docker-compose up rabbitmq -d

# View RabbitMQ logs
docker-compose logs -f rabbitmq

# Check running containers
docker ps

# Stop all services
docker-compose down

# Start services with logs
docker-compose up

# Restart RabbitMQ
docker-compose restart rabbitmq
```

## Additional Testing Tools

### RabbitMQ CLI Tools

```bash
# List queues
docker exec <container-id> rabbitmqctl list_queues

# List exchanges
docker exec <container-id> rabbitmqctl list_exchanges

# List bindings
docker exec <container-id> rabbitmqctl list_bindings
```

### Python Interactive Testing

```python
# Start Python REPL
python

# Test connection
import pika
connection = pika.BlockingConnection(pika.URLParameters('amqp://guest:guest@localhost:5672/'))
channel = connection.channel()
print("Connected!")

# Check queue
result = channel.queue_declare(queue='email.queue', passive=True)
print(f"Messages in queue: {result.method.message_count}")
```

## Support

If you encounter issues:
1. Check service logs for error messages
2. Verify environment variables in `.env`
3. Check RabbitMQ Management UI
4. Review SendGrid Activity feed
5. Test with the provided test scripts
