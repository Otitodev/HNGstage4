# Email Service Documentation

## Overview

The Email Service is a microservice that consumes email notification requests from RabbitMQ and delivers them via SendGrid. It provides reliable email delivery with dead letter queue support for failed messages and supports both plain HTML emails and SendGrid dynamic templates.

## Architecture

### Message Flow

```
Producer → notifications.direct → email.queue → Email Service → SendGrid → Recipient
                                       ↓ (on failure)
                                  notifications.dlx → failed.queue
```

### Components

- **Main Exchange**: `notifications.direct` (direct exchange)
- **Main Queue**: `email.queue` (receives email requests)
- **Routing Key**: `notify.email`
- **Dead Letter Exchange**: `notifications.dlx` (fanout exchange)
- **Dead Letter Queue**: `failed.queue` (stores failed emails)

## Prerequisites

### Required Software

1. **Python 3.7+**
2. **RabbitMQ Server** (local or cloud)
3. **SendGrid Account** with API key

### Python Dependencies

```bash
pip install pika sendgrid
```

## Configuration

### Environment Variables

Create a `.env` file in your project root:

```env
# RabbitMQ Connection
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# SendGrid Configuration
SENDGRID_API_KEY=SG.your_sendgrid_api_key_here
FROM_EMAIL=noreply@yourdomain.com
```

### SendGrid Setup

1. Sign up at [SendGrid](https://sendgrid.com/)
2. Go to **Settings** → **API Keys**
3. Click **Create API Key**
4. Select **Full Access** or **Restricted Access** with Mail Send permissions
5. Copy the API key to your `.env` file

**Important:** Verify your sender email address in SendGrid:
- Go to **Settings** → **Sender Authentication**
- Verify a single sender email OR authenticate your domain

## Queue Configuration

### Main Queue (`email.queue`)

- **Durable**: Yes (survives broker restart)
- **Routing Key**: `notify.email`
- **Dead Letter Exchange**: `notifications.dlx`
- **Dead Letter Routing Key**: `email`

### Dead Letter Queue (`failed.queue`)

- **Durable**: Yes
- **Message TTL**: 24 hours (86400000 ms)
- **Max Length**: 10,000 messages
- **Purpose**: Stores failed emails for debugging and retry

## Message Format

### Basic Email Message

```json
{
  "to": "recipient@example.com",
  "subject": "Welcome to Our Service",
  "content": "<h1>Welcome!</h1><p>Thank you for signing up.</p>"
}
```

### Email with SendGrid Template

```json
{
  "to": "user@example.com",
  "subject": "Order Confirmation",
  "content": "<p>Fallback content if template fails</p>",
  "template_id": "d-1234567890abcdef",
  "data": {
    "order_number": "12345",
    "customer_name": "John Doe",
    "total_amount": "$99.99",
    "items": [
      {"name": "Product A", "price": "$49.99"},
      {"name": "Product B", "price": "$50.00"}
    ]
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `to` | string | Yes | Recipient email address |
| `subject` | string | Yes | Email subject line |
| `content` | string | Yes | HTML email content (fallback if template fails) |
| `template_id` | string | No | SendGrid dynamic template ID (format: `d-xxxxx`) |
| `data` | object | No | Dynamic template variables |

## Running the Service

### Start the Service

```bash
python services/email_service.py
```

### Expected Output

```
2024-11-13 10:30:00 - INFO - Starting email service consumer...
2024-11-13 10:30:00 - INFO - Waiting for messages. To exit press CTRL+C
```

### Graceful Shutdown

Press `Ctrl+C` to stop the service:

```
2024-11-13 10:35:00 - INFO - Stopping email service...
2024-11-13 10:35:00 - INFO - RabbitMQ connection closed
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

# Simple email message
message = {
    "to": "user@example.com",
    "subject": "Test Email",
    "content": "<h1>Hello!</h1><p>This is a test email.</p>"
}

# Publish to exchange
channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(message),
    properties=pika.BasicProperties(
        delivery_mode=2,  # persistent message
        content_type='application/json'
    )
)

print("Email message published!")
connection.close()
```

### Using SendGrid Template

```python
# Email with dynamic template
template_message = {
    "to": "customer@example.com",
    "subject": "Your Order Confirmation",
    "content": "<p>Order confirmed</p>",
    "template_id": "d-1234567890abcdef",
    "data": {
        "customer_name": "Jane Smith",
        "order_id": "ORD-12345",
        "order_date": "2024-11-13",
        "items": [
            {"name": "Widget", "quantity": 2, "price": "$20.00"}
        ],
        "total": "$40.00"
    }
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(template_message),
    properties=pika.BasicProperties(
        delivery_mode=2,
        content_type='application/json'
    )
)
```

### Using RabbitMQ Management UI

1. Open `http://localhost:15672` (default: guest/guest)
2. Go to **Queues** → `email.queue`
3. Expand **Publish message**
4. Set **Payload**:
```json
{
  "to": "test@example.com",
  "subject": "Test",
  "content": "<p>Test message</p>"
}
```
5. Click **Publish message**

## SendGrid Templates

### Creating a Template

1. Go to SendGrid → **Email API** → **Dynamic Templates**
2. Click **Create a Dynamic Template**
3. Name your template (e.g., "Order Confirmation")
4. Click **Add Version** → Choose a design
5. Use handlebars syntax for variables: `{{customer_name}}`
6. Copy the Template ID (format: `d-xxxxxxxxxxxxx`)

### Template Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>Order Confirmation</title>
</head>
<body>
    <h1>Thank you, {{customer_name}}!</h1>
    <p>Your order #{{order_id}} has been confirmed.</p>
    
    <h2>Order Details:</h2>
    <ul>
    {{#each items}}
        <li>{{this.name}} - {{this.quantity}} x {{this.price}}</li>
    {{/each}}
    </ul>
    
    <p><strong>Total: {{total}}</strong></p>
    
    <p>Order Date: {{order_date}}</p>
</body>
</html>
```

### Using the Template

```python
message = {
    "to": "customer@example.com",
    "subject": "Order Confirmation",
    "content": "<p>Fallback content</p>",
    "template_id": "d-your-template-id-here",
    "data": {
        "customer_name": "John Doe",
        "order_id": "12345",
        "order_date": "2024-11-13",
        "items": [
            {"name": "Product A", "quantity": 1, "price": "$29.99"}
        ],
        "total": "$29.99"
    }
}
```

## Error Handling

### Message Processing Outcomes

| Scenario | Action | Result |
|----------|--------|--------|
| Email sent successfully | `basic_ack` | Message removed from queue |
| SendGrid API error | Move to DLQ | Message stored in `failed.queue` |
| Invalid JSON | Move to DLQ | Message stored with error details |
| Missing required fields | Move to DLQ | Validation error logged |
| Network error | Move to DLQ | Retry possible from DLQ |

### Dead Letter Queue

Failed messages are moved to `failed.queue` with original properties preserved. Common failure reasons:

- Invalid recipient email address
- SendGrid API rate limits exceeded
- Invalid API key
- Network connectivity issues
- Malformed JSON messages

**Retention:** Messages in DLQ are kept for 24 hours, then automatically deleted.

## Monitoring

### Log Levels

The service logs at INFO level by default. Key log messages:

```
INFO - Starting email service consumer...
INFO - Email sent to user@example.com with subject 'Welcome'
ERROR - Failed to send email to invalid@email: Invalid email address
ERROR - Moved message to DLQ: Invalid JSON message
```

### SendGrid Dashboard

Monitor email delivery in SendGrid:
1. Go to **Activity** in SendGrid dashboard
2. View delivery status, opens, clicks, bounces
3. Check for blocked or bounced emails

### Monitoring Checklist

- [ ] Service is running and consuming messages
- [ ] SendGrid API key is valid and not expired
- [ ] Sender email is verified in SendGrid
- [ ] Check `failed.queue` for failed emails
- [ ] Monitor SendGrid quota and rate limits
- [ ] Review bounce and spam reports

## Troubleshooting

### Service Won't Start

**Issue:** `ValueError: SENDGRID_API_KEY environment variable is required`

**Solution:**
- Add `SENDGRID_API_KEY` to your `.env` file
- Verify the API key is valid in SendGrid dashboard
- Ensure `.env` file is in the correct directory

### Email Not Delivered

**Issue:** Email sent successfully but not received

**Solution:**
- Check recipient's spam/junk folder
- Verify sender email is authenticated in SendGrid
- Check SendGrid Activity feed for delivery status
- Verify recipient email address is valid
- Check for bounce notifications

### Template Not Working

**Issue:** Template variables not rendering

**Solution:**
- Verify `template_id` format: `d-xxxxxxxxxxxxx`
- Check template is active in SendGrid
- Ensure `data` field matches template variables
- Test template in SendGrid template editor

### Rate Limit Errors

**Issue:** `429 Too Many Requests` from SendGrid

**Solution:**
- Check your SendGrid plan limits
- Implement rate limiting in your producer
- Reduce `prefetch_count` to slow consumption
- Upgrade SendGrid plan if needed

### Connection Errors

**Issue:** `pika.exceptions.AMQPConnectionError`

**Solution:**
- Verify RabbitMQ is running
- Check `RABBITMQ_URL` in `.env`
- Test network connectivity to RabbitMQ host
- Verify credentials are correct

## Performance Tuning

### Prefetch Count

Current setting: `prefetch_count=1` (processes one message at a time)

For higher throughput:
```python
self.channel.basic_qos(prefetch_count=10)  # Process up to 10 messages
```

**Note:** Be mindful of SendGrid rate limits when increasing prefetch.

### Concurrent Workers

Run multiple service instances for parallel processing:

```bash
# Terminal 1
python services/email_service.py

# Terminal 2
python services/email_service.py

# Terminal 3
python services/email_service.py
```

RabbitMQ will distribute messages across all consumers.

### SendGrid Rate Limits

| Plan | Emails per Day | Emails per Second |
|------|----------------|-------------------|
| Free | 100 | N/A |
| Essentials | 40,000 - 100,000 | ~3-10 |
| Pro | 1,500,000+ | ~40+ |

## Security Best Practices

1. **Protect API Keys**
   - Never commit `.env` files to version control
   - Use environment variables in production
   - Rotate API keys regularly
   
2. **Validate Input**
   - Sanitize email addresses
   - Validate HTML content
   - Limit message size
   
3. **Sender Authentication**
   - Use authenticated domain (not free email providers)
   - Set up SPF, DKIM, and DMARC records
   - Verify sender identity in SendGrid
   
4. **Secure RabbitMQ**
   - Use strong passwords
   - Enable TLS: `amqps://` instead of `amqp://`
   - Restrict network access
   
5. **Content Security**
   - Sanitize user-generated content in emails
   - Avoid including sensitive data in email bodies
   - Use HTTPS links only

## Integration Examples

### User Registration Email

```python
def send_welcome_email(user_email, user_name):
    message = {
        "to": user_email,
        "subject": "Welcome to Our Platform!",
        "content": f"""
            <html>
            <body>
                <h1>Welcome, {user_name}!</h1>
                <p>Thank you for joining our platform.</p>
                <p>Get started by completing your profile.</p>
                <a href="https://example.com/profile">Complete Profile</a>
            </body>
            </html>
        """,
        "template_id": "d-welcome-template-id",
        "data": {
            "user_name": user_name,
            "profile_url": "https://example.com/profile"
        }
    }
    
    publish_to_rabbitmq(
        exchange='notifications.direct',
        routing_key='notify.email',
        message=message
    )
```

### Password Reset Email

```python
def send_password_reset(user_email, reset_token):
    reset_link = f"https://example.com/reset-password?token={reset_token}"
    
    message = {
        "to": user_email,
        "subject": "Password Reset Request",
        "content": f"""
            <html>
            <body>
                <h2>Password Reset</h2>
                <p>Click the link below to reset your password:</p>
                <a href="{reset_link}">Reset Password</a>
                <p>This link expires in 1 hour.</p>
                <p>If you didn't request this, please ignore this email.</p>
            </body>
            </html>
        """,
        "template_id": "d-password-reset-template",
        "data": {
            "reset_link": reset_link,
            "expiry_time": "1 hour"
        }
    }
    
    publish_to_rabbitmq(
        exchange='notifications.direct',
        routing_key='notify.email',
        message=message
    )
```

### Order Confirmation Email

```python
def send_order_confirmation(order):
    message = {
        "to": order['customer_email'],
        "subject": f"Order Confirmation #{order['id']}",
        "content": "<p>Your order has been confirmed.</p>",
        "template_id": "d-order-confirmation-template",
        "data": {
            "order_id": order['id'],
            "customer_name": order['customer_name'],
            "order_date": order['created_at'],
            "items": order['items'],
            "subtotal": order['subtotal'],
            "tax": order['tax'],
            "shipping": order['shipping'],
            "total": order['total'],
            "shipping_address": order['shipping_address'],
            "tracking_url": order.get('tracking_url', '')
        }
    }
    
    publish_to_rabbitmq(
        exchange='notifications.direct',
        routing_key='notify.email',
        message=message
    )
```

## API Reference

### Class: `EmailService`

#### Methods

##### `__init__()`
Initializes the service, connects to RabbitMQ, and sets up SendGrid client.

**Raises:**
- `ValueError`: If `SENDGRID_API_KEY` is not set

##### `send_email(to_email, subject, content, template_id=None, data=None)`
Sends an email via SendGrid.

**Parameters:**
- `to_email` (str): Recipient email address
- `subject` (str): Email subject line
- `content` (str): HTML email content
- `template_id` (str, optional): SendGrid template ID
- `data` (dict, optional): Template variables

**Returns:** 
```python
{
    'status': 'success',
    'status_code': 202,
    'message_id': 'abc123...'
}
```

**Raises:**
- `Exception`: If email sending fails

##### `process_message(channel, method, properties, body)`
Callback function that processes messages from RabbitMQ queue.

##### `start_consuming()`
Starts the consumer loop to listen for messages. Blocks until stopped.

## Testing

### Test Email Sending

```python
# test_email_service.py
import os
from services.email_service import EmailService

# Set environment variables
os.environ['SENDGRID_API_KEY'] = 'your-test-api-key'
os.environ['FROM_EMAIL'] = 'test@yourdomain.com'
os.environ['RABBITMQ_URL'] = 'amqp://guest:guest@localhost:5672/'

# Create service instance
service = EmailService()

# Test sending email
response = service.send_email(
    to_email='test@example.com',
    subject='Test Email',
    content='<h1>Test</h1><p>This is a test email.</p>'
)

print(f"Email sent: {response}")
```

### Test with RabbitMQ

```bash
# Publish test message
python -c "
import pika
import json

connection = pika.BlockingConnection(pika.URLParameters('amqp://guest:guest@localhost:5672/'))
channel = connection.channel()

message = {
    'to': 'test@example.com',
    'subject': 'Test',
    'content': '<p>Test message</p>'
}

channel.basic_publish(
    exchange='notifications.direct',
    routing_key='notify.email',
    body=json.dumps(message)
)

print('Test message published')
connection.close()
"
```

## FAQ

**Q: Can I send to multiple recipients?**  
A: Currently, the service sends to one recipient per message. To send to multiple recipients, publish multiple messages or modify the service to support BCC.

**Q: How do I handle attachments?**  
A: SendGrid supports attachments. You'll need to modify the `send_email` method to include attachment handling using SendGrid's `Attachment` helper.

**Q: What happens if SendGrid is down?**  
A: Messages will be moved to the dead letter queue and can be retried later.

**Q: Can I track email opens and clicks?**  
A: Yes, enable tracking in SendGrid settings. View analytics in the SendGrid dashboard.

**Q: How do I retry failed emails?**  
A: Manually republish messages from `failed.queue` back to `email.queue` using RabbitMQ management UI or a script.

**Q: Can I use a different email provider?**  
A: Yes, replace the SendGrid client with another provider's SDK (e.g., AWS SES, Mailgun, Postmark).

## Support

For issues or questions:
- Check service logs for error messages
- Inspect `failed.queue` for failed emails
- Review SendGrid Activity feed
- Check RabbitMQ Management UI for queue status
- Verify sender authentication in SendGrid

## License

[Your License Here]
