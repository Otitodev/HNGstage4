🏗️ Codebase Tour: Distributed Notification System
You've built a microservices-based notification orchestration platform with resilience patterns and async processing. Here's what you have:

Architecture Overview
This is a 3-tier microservices system:

API Gateway - Orchestration layer
User Service - User data & preferences
Template Service - Content management & rendering
Plus two background workers:

Email Service - SendGrid integration
Push Service - Firebase Cloud Messaging
Core Services
1. API Gateway (api_gateway.py) - The Brain

Orchestrates notification requests across services
Circuit breakers (pybreaker) protect against cascading failures
Idempotency support prevents duplicate processing
Retry logic with exponential backoff
Publishes to RabbitMQ for async processing
Health checks for all dependencies
2. User Service (user_service.py) - User Data Hub

PostgreSQL (Neon) for persistent storage
Redis caching with decorators (@cached)
Mock mode fallback when DB unavailable
Manages user profiles, preferences, and notification settings
Multi-language support
3. Template Service (template_service.py) - Content Engine

Template storage and versioning
Dynamic content rendering with variable interpolation
Redis cache-aside pattern
PostgreSQL + Redis dual storage
10 pre-loaded templates (order confirmations, password resets, etc.)
Infrastructure Components
Utilities (utils/)

response_formatter.py - Standardized API responses with pagination metadata
cache.py - Redis caching with decorators (@cached, @invalidate_cache)
idempotency.py - Prevents duplicate request processing
retry_utils.py - Exponential backoff retry logic
Message Queue Workers (services/)

email_service.py - Consumes from email.queue, sends via SendGrid
push_service.py - Consumes from push.queue, sends via Firebase
Both implement Dead Letter Queues for failed messages
Redis Client (redis_client.py)

Singleton pattern for Upstash Redis
Async operations with JSON serialization
Queue Validator (mq_validator.py)

Debug tool to inspect RabbitMQ messages
Key Features
Resilience Patterns:

Circuit breakers on external service calls
Retry with exponential backoff and jitter
Dead letter queues for failed messages
Graceful degradation (mock mode fallbacks)
Performance:

Redis caching with TTL
Async database operations (asyncpg)
Connection pooling
Cache-aside pattern
Developer Experience:

Comprehensive health checks
Request tracing with X-Request-ID
Structured logging
OpenAPI documentation
Standardized response format
Data Flow
1. POST /v1/notifications → API Gateway
2. Gateway fetches user data (User Service)
3. Gateway renders template (Template Service)
4. Gateway publishes to RabbitMQ
5. Workers consume and deliver (Email/Push Services)
Tech Stack
Framework: FastAPI
Database: PostgreSQL (Neon) with asyncpg
Cache: Redis (Upstash)
Message Queue: RabbitMQ with pika
Email: SendGrid
Push: Firebase Cloud Messaging
Deployment: Docker Compose ready
Notable Patterns
Service-to-service auth via X-Internal-Secret header
Idempotency keys for safe retries
Standardized responses across all services
Cache decorators for clean caching logic
Mock mode for development without infrastructure
This is a production-ready notification system with enterprise-grade reliability patterns. The code is well-structured, documented, and follows microservices best practices. Nice work!