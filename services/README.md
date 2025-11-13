# Worker Services

Background services that process notifications from RabbitMQ queues. These services run on AWS ECS Fargate for 24/7 availability.

## 📦 Services

### Notification Router (`notification_router.py`)
Routes messages from the main `notifications` queue to specific channel queues.

**Queue Flow:**
```
notifications → Notification Router → email.queue
                                   → push.queue
```

**Features:**
- Consumes from `notifications` queue
- Extracts rendered content from template service response
- Routes to appropriate channels based on delivery targets
- Handles both email and push notifications

**Running:**
```bash
python notification_router.py
```

---

### Email Service (`email_service.py`)
Sends emails via SendGrid with comprehensive logging and retry logic.

**Features:**
- SendGrid integration
- Automatic retry (up to 5 attempts)
- PostgreSQL logging for analytics
- Dead letter queue for permanent failures
- Database schema auto-creation

**Queue Flow:**
```
email.queue → Email Service → SendGrid → Recipient
                ↓ (on failure)
           failed.queue → Retry (5x) → email.dlq
```

**Running:**
```bash
python email_service.py
```

**Database Logging:**
```bash
# View email logs
python check_email_logs.py

# Initialize database
python init_database.py
```

---

### Push Service (`push_service.py`)
Sends push notifications via Firebase Cloud Messaging.

**Features:**
- Firebase Cloud Messaging integration
- Automatic retry logic
- Dead letter queue support
- Simulation mode (without Firebase)

**Queue Flow:**
```
push.queue → Push Service → Firebase → Mobile Device
               ↓ (on failure)
          failed.queue → Retry
```

**Running:**
```bash
python push_service.py
```

**Firebase Setup:**
1. Download `firebase-credentials.json` from Firebase Console
2. Place in project root or set `FIREBASE_CREDENTIALS_PATH`
3. Service will run in simulation mode if credentials not found

---

## 🚀 Local Development

### Prerequisites
- Docker Desktop (for RabbitMQ)
- Python 3.11+
- SendGrid API key
- Neon PostgreSQL database
- Firebase credentials (optional)

### Setup

1. **Start RabbitMQ:**
```bash
docker-compose up rabbitmq -d
```

2. **Configure Environment:**
Create `.env` in project root:
```env
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
SENDGRID_API_KEY=SG.your_key_here
FROM_EMAIL=noreply@yourdomain.com
NEON_DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
```

3. **Initialize Database:**
```bash
python init_database.py
```

4. **Start Services:**
```bash
# Terminal 1
python notification_router.py

# Terminal 2
python email_service.py

# Terminal 3
python push_service.py
```

### Testing

```bash
# Run test script
python ../test_services_local.py

# Check email logs
python check_email_logs.py
```

---

## ☁️ AWS Deployment

### Quick Deploy

```powershell
# Build and push Docker images
.\deploy_to_aws.ps1

# Services will auto-deploy to AWS ECS
```

### Manage Services

```powershell
# Pause services (stop charges)
aws ecs update-service --cluster notification-services --service notification-router --desired-count 0 --region eu-north-1 --profile otito2
aws ecs update-service --cluster notification-services --service email-service --desired-count 0 --region eu-north-1 --profile otito2

# Resume services
aws ecs update-service --cluster notification-services --service notification-router --desired-count 1 --region eu-north-1 --profile otito2
aws ecs update-service --cluster notification-services --service email-service --desired-count 1 --region eu-north-1 --profile otito2
```

See [AWS_SERVICE_CONTROL.md](AWS_SERVICE_CONTROL.md) for complete guide.

---

## 📊 Monitoring

### CloudWatch Logs

```powershell
# Notification router
aws logs tail /ecs/notification-router --follow --region eu-north-1 --profile otito2

# Email service
aws logs tail /ecs/email-service --follow --region eu-north-1 --profile otito2

# Push service
aws logs tail /ecs/push-service --follow --region eu-north-1 --profile otito2
```

### Database Analytics

```bash
# View email delivery stats
python check_email_logs.py
```

**Metrics tracked:**
- Total emails sent
- Success/failure rates
- Retry attempts
- Error messages
- Delivery timestamps

---

## 🗂️ Queue Structure

### Main Queues

| Queue | Purpose | Consumer |
|-------|---------|----------|
| `notifications` | Incoming notifications from API Gateway | Notification Router |
| `email.queue` | Email notifications | Email Service |
| `push.queue` | Push notifications | Push Service |
| `failed.queue` | Failed messages for retry | Retry Worker (Email/Push) |
| `email.dlq` | Permanently failed emails | Manual review |

### Message Format

**notifications queue:**
```json
{
  "user_id": "uuid",
  "delivery_targets": {
    "email": "user@example.com",
    "phone": "+1234567890"
  },
  "rendered_content": {
    "success": true,
    "data": {
      "subject": "Your Weekly Digest",
      "body": "Plain text content",
      "html_body": "<html>...</html>"
    }
  },
  "metadata": {
    "template_key": "WEEKLY_DIGEST",
    "preferred_language": "en-US"
  }
}
```

**email.queue:**
```json
{
  "notification_id": "uuid",
  "user_id": "uuid",
  "to": "user@example.com",
  "subject": "Your Weekly Digest",
  "content": "<html>...</html>",
  "template_id": null,
  "data": {
    "template_key": "WEEKLY_DIGEST",
    "language": "en-US"
  }
}
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RABBITMQ_URL` | Yes | RabbitMQ connection string |
| `SENDGRID_API_KEY` | Yes (Email) | SendGrid API key |
| `FROM_EMAIL` | Yes (Email) | Verified sender email |
| `NEON_DATABASE_URL` | Yes (Email) | PostgreSQL connection string |
| `FIREBASE_CREDENTIALS_PATH` | No (Push) | Path to Firebase credentials |

### Retry Configuration

**Email Service:**
- Max retries: 5
- Retry interval: 60 seconds
- After 5 failures → moves to `email.dlq`

**Push Service:**
- Max retries: 5
- Retry interval: 60 seconds
- After 5 failures → moves to DLQ

---

## 📁 Files

```
services/
├── notification_router.py      # Routes messages to channels
├── email_service.py            # Email delivery service
├── push_service.py             # Push notification service
├── init_database.py            # Database setup script
├── check_email_logs.py         # View email analytics
├── db_schema.sql               # Database schema
├── Dockerfile.router           # Router container
├── Dockerfile.email            # Email service container
├── Dockerfile.push             # Push service container
├── deploy_to_aws.ps1           # AWS deployment script
├── requirements.txt            # Python dependencies
├── AWS_SERVICE_CONTROL.md      # Service management guide
├── EMAIL_SERVICE_DOCUMENTATION.md
├── PUSH_SERVICE_DOCUMENTATION.md
└── README.md                   # This file
```

---

## 📚 Documentation

- [Email Service Documentation](EMAIL_SERVICE_DOCUMENTATION.md) - Complete email service guide
- [Push Service Documentation](PUSH_SERVICE_DOCUMENTATION.md) - Complete push service guide
- [AWS Service Control](AWS_SERVICE_CONTROL.md) - Pause, start, scale services
- [AWS Deployment Guide](../AWS_DEPLOYMENT_COMPLETE.md) - Full deployment instructions
- [Windows Deployment](WINDOWS_DEPLOYMENT.md) - Windows-specific guide

---

## 🐛 Troubleshooting

### Services won't connect to RabbitMQ
```bash
# Check RabbitMQ is running
docker ps | grep rabbitmq

# Test connection
python -c "import pika; pika.BlockingConnection(pika.URLParameters('amqp://guest:guest@localhost:5672/'))"
```

### Emails not sending
```bash
# Check SendGrid API key
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('SENDGRID_API_KEY')[:20])"

# Verify sender email in SendGrid dashboard
# Check CloudWatch logs for detailed errors
```

### Database connection issues
```bash
# Test database connection
python init_database.py

# Check logs
python check_email_logs.py
```

---

## 💰 AWS Costs

**When Running (desired count = 1):**
- Notification Router: ~$31/month
- Email Service: ~$31/month
- Push Service: ~$31/month
- **Total: ~$93/month**

**When Paused (desired count = 0):**
- ECS Fargate: $0/month
- ECR Storage: ~$0.30/month
- CloudWatch Logs: ~$1/month
- **Total: ~$1.30/month**

**Optimization:**
- Pause services when not in use
- Use smaller task sizes if possible
- Set CloudWatch log retention policies
- Delete old ECR images

---

## 🔒 Security

- Secrets stored in AWS Secrets Manager
- IAM roles with least privilege
- SSL/TLS for all connections
- No credentials in code or logs
- Database connection pooling

---

**For questions or issues, see the main project README or open a GitHub issue.**
