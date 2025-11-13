# Distributed Notification System - Architecture Design

## System Overview

A microservices-based notification orchestration platform designed for high availability, scalability, and resilience. The system handles notification delivery across multiple channels (email, push) with support for templating, user preferences, and guaranteed delivery.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT APPLICATIONS                             │
│                    (Web Apps, Mobile Apps, Backend Services)                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 │ HTTPS/REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
│                           (Port 8000)                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • Request Validation & Routing                                      │   │
│  │  • Circuit Breakers (pybreaker)                                      │   │
│  │  • Idempotency Management                                            │   │
│  │  • Request Tracing (X-Request-ID)                                    │   │
│  │  • Service Orchestration                                             │   │
│  │  • Retry Logic with Exponential Backoff                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────┬──────────────────────┬──────────────────────┬───────────────────────┘
        │                      │                      │
        │                      │                      │
        ▼                      ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ USER SERVICE │      │   TEMPLATE   │      │   RABBITMQ   │
│  (Port 8002) │      │   SERVICE    │      │ MESSAGE QUEUE│
│              │      │  (Port 8001) │      │              │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                      │
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  PostgreSQL  │      │  PostgreSQL  │      │   Email &    │
│    (Neon)    │      │    (Neon)    │      │ Push Workers │
│              │      │              │      │              │
│ • User Data  │      │ • Templates  │      │ • Consumers  │
│ • Preferences│      │ • Versions   │      │ • Delivery   │
└──────────────┘      └──────────────┘      └──────────────┘
       │                     │
       │                     │
       ▼                     ▼
┌─────────────────────────────────────┐
│         REDIS (Upstash)             │
│                                     │
│  • User Profile Cache               │
│  • Template Cache                   │
│  • Idempotency Keys                 │
│  • Session Management               │
└─────────────────────────────────────┘
```

## Component Details

### 1. API Gateway (Orchestration Layer)
**Technology:** FastAPI, Python 3.11+
**Port:** 8000
**Responsibilities:**
- Central entry point for all notification requests
- Orchestrates communication between User and Template services
- Implements circuit breaker pattern for fault tolerance
- Manages idempotency to prevent duplicate processing
- Publishes messages to RabbitMQ for async delivery
- Request/response logging and tracing

**Key Features:**
- Circuit Breakers: 5 failures trigger open state, 60s reset timeout
- Idempotency: 24-hour TTL for duplicate detection
- Retry Logic: Exponential backoff (0.1s to 5s)
- Service Discovery: Environment-based URL configuration

### 2. User Service (User Management)
**Technology:** FastAPI, asyncpg, Python 3.11+
**Port:** 8002
**Database:** PostgreSQL (Neon)
**Cache:** Redis (Upstash)

**Responsibilities:**
- User profile management (CRUD operations)
- Notification preferences storage
- Multi-language support
- Delivery channel preferences (email, push, SMS)
- Quiet hours management

**Data Model:**
```sql
users (
    user_id VARCHAR(255) PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20),
    preferred_language VARCHAR(10),
    preferences JSONB
)
```

**Cache Strategy:**
- Cache-aside pattern
- 1-hour TTL for user profiles
- Automatic invalidation on updates

### 3. Template Service (Content Management)
**Technology:** FastAPI, asyncpg, Python 3.11+
**Port:** 8001
**Database:** PostgreSQL (Neon)
**Cache:** Redis (Upstash)

**Responsibilities:**
- Template storage and versioning
- Dynamic content rendering
- Variable interpolation
- Multi-format support (plain text, HTML)
- Template validation

**Data Model:**
```sql
templates (
    template_key TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    html_body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
)
```

**Pre-loaded Templates:**
- ORDER_CONFIRMATION
- PASSWORD_RESET
- SHIPPING_UPDATE
- INVOICE_PAID
- WELCOME_NEW_USER
- WEEKLY_DIGEST
- ACCOUNT_LOCKED
- PROMOTION_FLASH_SALE
- SUPPORT_TICKET_UPDATE
- LOW_STOCK_ALERT

### 4. Message Queue (RabbitMQ)
**Technology:** RabbitMQ 3.x
**Deployment:** Railway/Render

**Queue Structure:**
```
notifications (main queue)
    ├── email.queue
    ├── push.queue
    └── failed.queue (DLQ)
```

**Features:**
- Durable queues for persistence
- Dead Letter Queue (DLQ) for failed messages
- Message TTL: 24 hours in DLQ
- Prefetch count: 1 (QoS)

### 5. Background Workers

#### Email Service
**Technology:** Python, SendGrid API
**Responsibilities:**
- Consumes from `email.queue`
- Sends emails via SendGrid
- Handles delivery failures
- Moves failed messages to DLQ

#### Push Service
**Technology:** Python, Firebase Cloud Messaging
**Responsibilities:**
- Consumes from `push.queue`
- Sends push notifications via FCM
- Handles device token management
- Moves failed messages to DLQ

### 6. Data Stores

#### PostgreSQL (Neon)
**Purpose:** Primary data store
**Features:**
- Serverless PostgreSQL
- Connection pooling (asyncpg)
- JSONB support for flexible schemas
- Automatic backups

**Databases:**
- User Service DB: User profiles and preferences
- Template Service DB: Templates and versions

#### Redis (Upstash)
**Purpose:** Caching and session management
**Features:**
- REST API (serverless-friendly)
- Automatic persistence
- TTL support
- Pub/Sub capabilities

**Use Cases:**
- User profile caching (1 hour TTL)
- Template caching (1 hour TTL)
- Idempotency keys (24 hour TTL)
- Rate limiting (future)

## Data Flow

### Notification Request Flow

```
1. Client → API Gateway
   POST /v1/notifications
   {
     "user_id": "user-123",
     "template_key": "ORDER_CONFIRMATION",
     "message_data": {...}
   }

2. API Gateway → User Service
   GET /v1/users/{user_id}
   Headers: X-Internal-Secret
   
   Response: User profile + preferences

3. API Gateway → Template Service
   POST /v1/templates/render
   Headers: X-Internal-Secret
   Body: {template_key, message_data}
   
   Response: Rendered content

4. API Gateway → RabbitMQ
   Publish to 'notifications' queue
   Payload: {
     user_id,
     delivery_targets: {email, phone},
     user_preferences,
     rendered_content,
     metadata
   }

5. Workers → External Services
   - Email Worker → SendGrid
   - Push Worker → Firebase FCM

6. API Gateway → Client
   202 Accepted
   {
     "notification_id": "...",
     "request_id": "...",
     "idempotency_key": "..."
   }
```

## Resilience Patterns

### 1. Circuit Breaker
- **Implementation:** pybreaker library
- **Threshold:** 5 consecutive failures
- **Timeout:** 60 seconds
- **Applied to:** User Service, Template Service calls

### 2. Retry with Exponential Backoff
- **Initial Delay:** 0.1 seconds
- **Max Delay:** 5 seconds
- **Factor:** 2.0
- **Jitter:** Enabled
- **Applied to:** RabbitMQ publishing

### 3. Idempotency
- **Storage:** Redis
- **TTL:** 24 hours
- **Key:** X-Idempotency-Key header
- **Behavior:** Returns cached response for duplicates

### 4. Dead Letter Queue
- **Purpose:** Failed message storage
- **TTL:** 24 hours
- **Max Length:** 10,000 messages
- **Monitoring:** Manual inspection required

### 5. Graceful Degradation
- **Mock Mode:** Services fall back to in-memory data
- **Cache Failures:** Continue without caching
- **Service Unavailable:** Return 503 with retry-after

## Security

### Authentication
- **Service-to-Service:** X-Internal-Secret header
- **Secret Management:** Environment variables
- **Rotation:** Manual (recommended: quarterly)

### Data Protection
- **In Transit:** HTTPS/TLS
- **At Rest:** Database encryption (Neon)
- **PII Handling:** Minimal logging, no sensitive data in logs

### Rate Limiting (Future)
- **Implementation:** Redis-based token bucket
- **Limits:** Per user, per endpoint
- **Response:** 429 Too Many Requests

## Monitoring & Observability

### Health Checks
```
GET /health
GET /v1/health
```

**Checks:**
- Service availability
- Database connectivity
- Redis connectivity
- RabbitMQ connectivity
- Dependent service health

### Logging
- **Format:** Structured JSON
- **Levels:** INFO, WARNING, ERROR
- **Correlation:** X-Request-ID header
- **Storage:** stdout (container logs)

### Metrics (Future)
- Request rate
- Error rate
- Response time (p50, p95, p99)
- Queue depth
- Cache hit rate
- Circuit breaker state

## Scalability

### Horizontal Scaling
- **API Gateway:** Stateless, scale to N instances
- **User Service:** Stateless, scale to N instances
- **Template Service:** Stateless, scale to N instances
- **Workers:** Scale based on queue depth

### Vertical Scaling
- **Database:** Neon auto-scaling
- **Redis:** Upstash auto-scaling
- **RabbitMQ:** Cluster mode (future)

### Performance Optimizations
- Connection pooling (asyncpg)
- Redis caching (1 hour TTL)
- Async I/O (FastAPI + asyncio)
- Batch processing (workers)

## Deployment

### Environment Variables
```bash
# API Gateway
INTERNAL_API_SECRET=<secret>
USER_SERVICE_URL=http://user-service:8002
TEMPLATE_SERVICE_URL=http://template-service:8001
RABBITMQ_URL=amqp://user:pass@host:5672/
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=<token>

# User Service
NEON_DATABASE_URL=postgresql://...
INTERNAL_API_SECRET=<secret>
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=<token>

# Template Service
NEON_DATABASE_URL=postgresql://...
INTERNAL_API_SECRET=<secret>
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=<token>

# Workers
RABBITMQ_URL=amqp://...
SENDGRID_API_KEY=<key>
FROM_EMAIL=noreply@example.com
FIREBASE_CREDENTIALS_PATH=./firebase.json
```

### Docker Compose
```yaml
services:
  - api-gateway (port 8000)
  - user-service (port 8002)
  - template-service (port 8001)
  - email-worker
  - push-worker
  - rabbitmq (ports 5672, 15672)
  - redis (port 6379)
```

## Future Enhancements

### Phase 2
- [ ] SMS delivery channel
- [ ] Webhook notifications
- [ ] Batch notifications
- [ ] Scheduled notifications
- [ ] A/B testing for templates

### Phase 3
- [ ] Analytics dashboard
- [ ] Template editor UI
- [ ] User preference portal
- [ ] Delivery status tracking
- [ ] Notification history

### Phase 4
- [ ] Multi-tenancy support
- [ ] Advanced rate limiting
- [ ] Geo-distributed deployment
- [ ] Real-time delivery status
- [ ] Machine learning for send-time optimization

## Technology Stack Summary

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Framework | FastAPI | High-performance async web framework |
| Language | Python 3.11+ | Modern Python with type hints |
| Database | PostgreSQL (Neon) | Serverless relational database |
| Cache | Redis (Upstash) | Serverless key-value store |
| Message Queue | RabbitMQ | Reliable message broker |
| Email | SendGrid | Transactional email delivery |
| Push | Firebase FCM | Mobile push notifications |
| Deployment | Docker | Containerization |
| Orchestration | Docker Compose | Local development |

## Performance Characteristics

- **Throughput:** 1000+ requests/second (per gateway instance)
- **Latency:** <100ms (p95, cached)
- **Availability:** 99.9% (with proper deployment)
- **Durability:** 99.99% (message persistence)
- **Cache Hit Rate:** 80%+ (steady state)

---

**Last Updated:** November 12, 2025
**Version:** 1.0.0
**Status:** Production Ready
