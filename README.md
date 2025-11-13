# Notification System

A production-ready, distributed notification system with email delivery, template rendering, and comprehensive logging.

## 🏗️ Architecture

```
API Gateway (Leapcell) → RabbitMQ (Railway) → Notification Router (AWS ECS)
                                                      ↓
                                              ┌───────┴────────┐
                                              ↓                ↓
                                        Email Service    Push Service
                                        (AWS ECS)        (AWS ECS)
                                              ↓
                                        PostgreSQL (Neon)
```

## 🚀 Services

### 1. API Gateway (`api_gateway.py`) - Leapcell
**Main orchestration service** - Entry point for all notification requests

**Features:**
- Request validation and routing
- Circuit breaker pattern for fault tolerance
- Idempotency support
- RabbitMQ message publishing
- Service coordination (User + Template services)

**Endpoints:**
- `POST /v1/notifications` - Send notification
- `GET /v1/health` - Health check

### 2. User Service (`user_service.py`) - Leapcell
**User management and preferences**

**Features:**
- User profile management
- Notification preferences (email, push, quiet hours)
- Multi-language support
- PostgreSQL database integration
- Redis caching

**Endpoints:**
- `GET /v1/users/{user_id}` - Get user profile
- `POST /v1/users` - Create user
- `GET /v1/health` - Health check

### 3. Template Service (`template_service.py`) - Leapcell
**Template management and rendering**

**Features:**
- Template CRUD operations
- Dynamic content rendering with variables
- Template versioning
- Redis caching
- Support for subject, body, and HTML templates

**Endpoints:**
- `POST /v1/templates` - Create template
- `POST /v1/templates/render` - Render template with data
- `GET /v1/templates/{template_key}` - Get template
- `GET /v1/health` - Health check

### 4. Email Service (`services/email_service.py`) - AWS ECS
**Email delivery with SendGrid integration**

**Features:**
- SendGrid email delivery
- Automatic retry (up to 5 attempts)
- PostgreSQL logging for analytics
- Dead letter queue for permanent failures
- Consumes from `email.queue`

**Monitoring:**
- CloudWatch logs
- Database analytics
- Delivery tracking

### 5. Push Service (`services/push_service.py`) - AWS ECS
**Push notification delivery with Firebase**

**Features:**
- Firebase Cloud Messaging integration
- Automatic retry logic
- Dead letter queue support
- Consumes from `push.queue`
- Simulation mode (without Firebase credentials)

**Monitoring:**
- CloudWatch logs
- Delivery tracking

### Supporting Service
**Notification Router** (`services/notification_router.py`) - AWS ECS
- Routes messages from `notifications` queue to `email.queue` and `push.queue`
- Extracts rendered content from template service response
- Separates concerns for better tracking

## ✨ Features

- ✅ Multi-channel notifications (Email, Push)
- ✅ Dynamic template rendering
- ✅ Automatic retry (up to 5 attempts)
- ✅ Dead letter queue for failed messages
- ✅ Database logging for analytics
- ✅ Idempotency support
- ✅ Circuit breaker pattern
- ✅ Redis caching
- ✅ CloudWatch logging

## 📋 Prerequisites

- Python 3.11+
- Docker Desktop (for local testing)
- AWS Account (for production deployment)
- SendGrid Account
- Neon PostgreSQL Database
- RabbitMQ (Railway/CloudAMQP)

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd HNGstage4
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
# RabbitMQ
RABBITMQ_URL=amqp://user:pass@host:5672/

# SendGrid
SENDGRID_API_KEY=SG.your_key_here
FROM_EMAIL=noreply@yourdomain.com

# Database
NEON_DATABASE_URL=postgresql://user:pass@host/db?sslmode=require

# Redis
UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
UPSTASH_REDIS_REST_TOKEN=your_token

# Services
USER_SERVICE_URL=http://localhost:8002
TEMPLATE_SERVICE_URL=http://localhost:8001
```

### 3. Initialize Database

```bash
python services/init_database.py
```

### 4. Run Services Locally

```bash
# Terminal 1 - Start RabbitMQ
docker-compose up rabbitmq -d

# Terminal 2 - Notification Router
python services/notification_router.py

# Terminal 3 - Email Service
python services/email_service.py

# Terminal 4 - API Gateway (if testing locally)
uvicorn api_gateway:app --port 8000
```

## 📡 API Usage

### 1. Create a User

```bash
curl -X POST https://your-user-service.leapcell.dev/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "email_address": "user@example.com",
    "phone_number": "+1234567890",
    "preferred_language": "en-US",
    "preferences": {
      "email_enabled": true,
      "push_enabled": true,
      "quiet_hours_start": "22:00",
      "quiet_hours_end": "08:00"
    }
  }'
```

### 2. Create a Template

```bash
curl -X POST https://your-template-service.leapcell.dev/v1/templates \
  -H "Content-Type: application/json" \
  -d '{
    "template_key": "WEEKLY_DIGEST",
    "subject": "Your Weekly {app_name} Digest: {new_updates} new items!",
    "body": "Check out your latest activity. See summary: {digest_link}",
    "html_body": "<h3>Weekly Summary</h3><p>You have {new_updates} new items. <a href=\"{digest_link}\">View Digest</a></p>"
  }'
```

### 3. Send Notification

```bash
curl -X POST https://your-api-gateway.leapcell.dev/v1/notifications \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: unique-key-123" \
  -d '{
    "user_id": "user-uuid",
    "template_key": "WEEKLY_DIGEST",
    "message_data": {
      "app_name": "MyApp",
      "new_updates": "10",
      "digest_link": "https://example.com/digest"
    }
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "notification_id": "user-uuid",
    "request_id": "req-uuid",
    "idempotency_key": "unique-key-123"
  },
  "message": "Notification successfully queued for delivery."
}
```

### Complete Flow

1. **API Gateway** receives request → validates → fetches user data → renders template
2. **Publishes** to RabbitMQ `notifications` queue
3. **Notification Router** (AWS) routes to `email.queue` and `push.queue`
4. **Email Service** (AWS) sends via SendGrid → logs to database
5. **Push Service** (AWS) sends via Firebase
6. **User** receives notification!

## 🔧 Local Testing

See [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md) for detailed instructions.

Quick test:

```bash
# 1. Start RabbitMQ
docker-compose up rabbitmq -d

# 2. Run test script
python test_services_local.py

# 3. Start services and monitor logs
```

## ☁️ AWS Deployment

### Quick Deploy

```powershell
# 1. Navigate to services folder
cd services

# 2. Run deployment script
.\deploy_to_aws.ps1

# 3. Follow the prompts
```

### Manage Services

```powershell
# Pause services (stop charges)
aws ecs update-service --cluster notification-services --service email-service --desired-count 0 --region eu-north-1 --profile otito2

# Resume services
aws ecs update-service --cluster notification-services --service email-service --desired-count 1 --region eu-north-1 --profile otito2
```

See [AWS_SERVICE_CONTROL.md](services/AWS_SERVICE_CONTROL.md) for complete guide.

## 📊 Monitoring

### Check Email Logs

```bash
python services/check_email_logs.py
```

### CloudWatch Logs

```powershell
# Email service logs
aws logs tail /ecs/email-service --follow --region eu-north-1 --profile otito2

# Notification router logs
aws logs tail /ecs/notification-router --follow --region eu-north-1 --profile otito2
```

### Service Status

```powershell
aws ecs describe-services --cluster notification-services --services notification-router email-service --region eu-north-1 --profile otito2
```

## 📁 Project Structure

```
HNGstage4/
├── services/
│   ├── email_service.py           # Email delivery service
│   ├── push_service.py            # Push notification service
│   ├── notification_router.py     # Message routing service
│   ├── init_database.py           # Database setup
│   ├── check_email_logs.py        # View email logs
│   ├── Dockerfile.email           # Email service container
│   ├── Dockerfile.router          # Router container
│   ├── deploy_to_aws.ps1          # AWS deployment script
│   └── AWS_SERVICE_CONTROL.md     # Service management guide
├── api_gateway.py                 # Main API gateway
├── template_service.py            # Template management
├── user_service.py                # User management
├── .env                           # Environment variables
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## 📚 Documentation

- [Email Service Documentation](services/EMAIL_SERVICE_DOCUMENTATION.md)
- [Push Service Documentation](services/PUSH_SERVICE_DOCUMENTATION.md)
- [Template Documentation](TEMPLATES_DOCUMENTATION.md)
- [AWS Deployment Guide](AWS_DEPLOYMENT_COMPLETE.md)
- [AWS Service Control](services/AWS_SERVICE_CONTROL.md)
- [Local Testing Guide](LOCAL_TESTING_GUIDE.md)
- [Windows Deployment](services/WINDOWS_DEPLOYMENT.md)

## 💰 Cost Breakdown

### AWS ECS (Production)
- Notification Router: ~$31/month
- Email Service: ~$31/month
- **Total: ~$62/month** (when running)
- **$0/month** when paused (desired count = 0)

### Other Services
- Leapcell (API Gateway): Free tier
- RabbitMQ (Railway): Free tier / $5/month
- PostgreSQL (Neon): Free tier
- SendGrid: Free tier (100 emails/day)

## 🔒 Security

- API keys stored in AWS Secrets Manager
- Environment variables never committed
- IAM roles with least privilege
- SSL/TLS for all connections
- Idempotency keys for duplicate prevention

## 🧪 Testing

```bash
# Run all tests
pytest

# Test specific service
pytest test_user_service.py

# Test with coverage
pytest --cov=. --cov-report=html
```

## 🐛 Troubleshooting

### Services won't start
- Check Docker Desktop is running
- Verify RabbitMQ is accessible
- Check environment variables in `.env`

### Emails not sending
- Verify SendGrid API key
- Check sender email is verified
- Review CloudWatch logs for errors

### Database connection issues
- Verify Neon database URL
- Check SSL mode is set to `require`
- Test connection with `psql`

See [Troubleshooting Guide](services/AWS_SERVICE_CONTROL.md#troubleshooting) for more.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- FastAPI for the excellent web framework
- SendGrid for email delivery
- AWS for reliable infrastructure
- Neon for serverless PostgreSQL

---

**Built with ❤️ for reliable, scalable notifications**

For questions or issues, please open a GitHub issue.
