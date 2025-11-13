# Push Notification Service Documentation

## Overview

The Push Notification Service is a microservice that consumes push notification requests from RabbitMQ and delivers them to mobile devices via Firebase Cloud Messaging (FCM). It provides reliable message delivery with dead letter queue support for failed notifications.

## Architecture

### Message Flow

```
Producer → notifications.direct → push.queue → Push Service → Firebase FCM → Mobile Device
                                       ↓ (on failure)
                                  notifications.dlx → failed.queue
```

### Components

- **Main Exchange**: `notifications.direct` (direct exchange)
- **Main Queue**: `push.queue` (receives notification requests)
- **Dead Letter Exchange**: `notifications.dlx` (fanout exchange)
- **Dead Letter Queue**: `failed.queue` (stores failed notifications)

## Prerequisites

### Required Software

1. **Python 3.7+**
2. **RabbitMQ Server** (local or cloud)
3. **Firebase Project** with Cloud Messaging enabled

### Python Dependencies

```bash
pip install pika firebase-admin python-dotenv
```

## Configuration

### Environment Variables

Create a `.env` file in your project root:

```env
# RabbitMQ Connection
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Firebase Credentials
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
```

### RabbitMQ Connection URL Format

```
amqp://username:password@host:port/vhost
```

**Examples:**
- Local: `amqp://guest:guest@localhost:5672/`
- Cloud: `amqp://user:pass@rabbitmq.example.com:5672/production`
- CloudAMQP: `amqp://user:pass@instance.cloudamqp.com/vhost`

### Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project → Project Settings → Service Accounts
3. Click "Generate New Private Key"
4. Save the JSON file as `firebase-credentials.json` in your project root

**Note:** If Firebase credentials are not found, the service runs in simulation mode (logs notifications without sending).

## Queue Configuration

### Main Queue (`push.queue`)

- **Durable**: Yes (survives broker restart)
- **Dead Letter Exchange**: `notifications.dlx`
- **Dead Letter Routing Key**: `push`

### Dead Letter Queue (`failed.queue`)

- **Durable**: Yes
- **Message TTL**: 24 hours (86400000 ms)
- **Max Length**: 10,000 messages
- **Purpose**: Stores failed notifications for debugging and retry

## Message Format

### Input Message Structure

Messages sent to `push.queue` must be JSON with the following structure:

```json
{
  "notification_id": "unique-id-123",
  "target": ["fcm_token_1", "fcm_token_2"],
  "title": "Notification Title",
  "body": "Notification message content",
  "data": {
    "custom_key": "custom_value",
    "action": "open_screen"
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `notification_id` | string | No | Unique identifier for tracking |
| `target` | string or array | Yes | FCM token(s) of recipient device(s) |
| `title` | string | No | Notification title (default: "New Notification") |
| `body` | string | No | Notification message content |
| `data` | object | No | Additional custom data payload |

### Example Messages

**Single Device:**
```json
{
  "notification_id": "order-123",
  "target": "dXYz123...FCMToken",
  "title": "Order Confirmed",
  "body": "Your order #123 has been confirmed",
  "data": {
    "order_id": "123",
    "type": "order_update"
  }
}
```

**Multiple Devices:**
```json
{
  "notification_id": "broadcast-456",
  "target": ["token1", "token2", "token3"],
  "title": "System Maintenance",
  "body": "Scheduled maintenance tonight at 2 AM"
}
```

## Running the Service

### Start the Service

```bash
python services/push_service.py
```

### Expected Output

```
2024-11-12 10:30:00 - INFO - Firebase Admin SDK initialized successfully
2024-11-12 10:30:00 - INFO - Push Notification Service initialized and connected to RabbitMQ
2024-11-12 10:30:00 - INFO - Starting push notification service consumer...
```

### Graceful Shutdown

Press `Ctrl+C` to stop the service:

```
2024-11-12 10:35:00 - INFO - Stopping push notification service...
```

## Publishing Messages

### Using Python (pika)

```python
import pika
import json

# Connect to RabbitMQ
connection = pika.BlockingConnection(
    pika.URLParameters('amqp://guest:guest@localhost:5672/')
)
channel = connection.channel()

# Prepare message
message = {
    "notification_id": "test-001",
    "target": "your-fcm-token-here",
    "title": "Test Notification",
    "body": "This is a test message",
    "data": {"test": "true"}
}

# Publish to exchange
channel.basic_publish(
    exchange='notifications.direct',
    routing_key='push',
    body=json.dumps(message),
    properties=pika.BasicProperties(
        delivery_mode=2,  # persistent message
        content_type='application/json'
    )
)

print("Message published!")
connection.close()
```

### Using RabbitMQ Management UI

1. Open `http://localhost:15672` (default credentials: guest/guest)
2. Go to **Queues** → `push.queue`
3. Expand **Publish message**
4. Set **Payload** to your JSON message
5. Click **Publish message**

### Using Command Line (rabbitmqadmin)

```bash
rabbitmqadmin publish exchange=notifications.direct routing_key=push \
  payload='{"target":"fcm-token","title":"Test","body":"Message"}'
```

## Error Handling

### Message Processing Outcomes

| Scenario | Action | Result |
|----------|--------|--------|
| All sends successful | `basic_ack` | Message removed from queue |
| All sends failed | `basic_nack` (no requeue) | Message moved to DLQ |
| Invalid JSON | `basic_nack` (no requeue) | Message discarded |
| Processing exception | `basic_nack` (no requeue) | Message moved to DLQ |

### Dead Letter Queue

Failed messages are automatically routed to `failed.queue` with metadata:

```json
{
  "x-death": [{
    "count": 1,
    "reason": "rejected",
    "queue": "push.queue",
    "exchange": "notifications.direct",
    "routing-keys": ["push"]
  }]
}
```

**Retention:** Messages in DLQ are kept for 24 hours, then automatically deleted.

## Monitoring

### Log Levels

The service logs at INFO level by default. Key log messages:

- **Initialization**: Firebase and RabbitMQ setup
- **Message Processing**: Each notification processed
- **Success**: Number of successful sends
- **Errors**: Failed sends, invalid messages, connection issues

### Example Logs

```
2024-11-12 10:30:15 - INFO - Processing push notification: order-123
2024-11-12 10:30:15 - INFO - Push notification sent successfully: projects/...
2024-11-12 10:30:15 - INFO - Successfully sent 1/1 push notifications
```

### Monitoring Checklist

- [ ] Service is running and consuming messages
- [ ] Firebase credentials are valid
- [ ] RabbitMQ connection is stable
- [ ] Check `failed.queue` for failed notifications
- [ ] Monitor Firebase quota usage

## Troubleshooting

### Service Won't Start

**Issue:** `pika.exceptions.AMQPConnectionError`

**Solution:**
- Verify RabbitMQ is running: `rabbitmqctl status`
- Check `RABBITMQ_URL` in `.env`
- Verify network connectivity to RabbitMQ host

### Firebase Errors

**Issue:** `Failed to initialize Firebase`

**Solution:**
- Verify `firebase-credentials.json` exists
- Check file path in `FIREBASE_CREDENTIALS_PATH`
- Validate JSON file is not corrupted
- Ensure Firebase project has FCM enabled

### Messages Not Being Consumed

**Issue:** Messages stay in queue

**Solution:**
- Check service logs for errors
- Verify queue binding: `rabbitmqctl list_bindings`
- Ensure no other consumer is connected
- Check prefetch settings

### Invalid Token Errors

**Issue:** `messaging.UnregisteredError`

**Solution:**
- Token may be expired or invalid
- User may have uninstalled the app
- Implement token refresh logic in your app
- Remove invalid tokens from your database

## Performance Tuning

### Prefetch Count

Current setting: `prefetch_count=1` (processes one message at a time)

For higher throughput:
```python
self.channel.basic_qos(prefetch_count=10)  # Process up to 10 messages
```

### Concurrent Workers

Run multiple service instances for parallel processing:

```bash
# Terminal 1
python services/push_service.py

# Terminal 2
python services/push_service.py

# Terminal 3
python services/push_service.py
```

RabbitMQ will distribute messages across all consumers.

## Security Best Practices

1. **Never commit credentials**
   - Add `.env` and `firebase-credentials.json` to `.gitignore`
   
2. **Use environment-specific credentials**
   - Development, staging, and production should have separate Firebase projects
   
3. **Secure RabbitMQ**
   - Use strong passwords
   - Enable TLS: `amqps://` instead of `amqp://`
   - Restrict network access
   
4. **Validate tokens**
   - Implement token validation before sending
   - Remove invalid tokens from database

## Integration Example

### Complete Workflow

```python
# 1. User registers device (mobile app)
# POST /api/users/register-device
{
  "user_id": "user-123",
  "fcm_token": "dXYz123...FCMToken",
  "platform": "android"
}

# 2. Store token in database
# users table: user_id, fcm_token, platform, created_at

# 3. Trigger notification (your application)
def send_notification(user_id, title, body):
    # Get user's FCM token from database
    token = get_user_fcm_token(user_id)
    
    # Publish to RabbitMQ
    message = {
        "notification_id": f"notif-{uuid.uuid4()}",
        "target": token,
        "title": title,
        "body": body,
        "data": {"user_id": user_id}
    }
    
    publish_to_rabbitmq(
        exchange='notifications.direct',
        routing_key='push',
        message=message
    )

# 4. Push service consumes and sends via Firebase
# 5. User receives notification on mobile device
```

## API Reference

### Class: `PushNotificationService`

#### Methods

##### `__init__()`
Initializes the service, connects to RabbitMQ, and sets up Firebase.

##### `send_push_notification(token, title, body, data=None)`
Sends a single push notification via Firebase.

**Parameters:**
- `token` (str): FCM device token
- `title` (str): Notification title
- `body` (str): Notification body
- `data` (dict, optional): Additional data payload

**Returns:** `bool` - True if successful, False otherwise

##### `process_message(ch, method, properties, body)`
Callback function that processes messages from RabbitMQ queue.

##### `start_consuming()`
Starts the consumer loop to listen for messages.

## FAQ

**Q: Can I send to multiple devices at once?**  
A: Yes, provide an array of FCM tokens in the `target` field.

**Q: What happens if Firebase is down?**  
A: Messages will be rejected and moved to the dead letter queue for retry.

**Q: How do I retry failed notifications?**  
A: Manually republish messages from `failed.queue` back to `push.queue`.

**Q: Can I customize notification appearance?**  
A: Yes, use the `data` field and handle it in your mobile app.

**Q: How many notifications can I send per second?**  
A: Firebase has rate limits. Check your Firebase project quota.

## Support

For issues or questions:
- Check logs in the service output
- Inspect `failed.queue` for failed messages
- Review Firebase Console for delivery reports
- Check RabbitMQ Management UI for queue status

## License

[Your License Here]
