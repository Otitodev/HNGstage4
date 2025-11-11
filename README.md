# Notification System Microservices

A distributed notification system designed for resilience and scalability, built with FastAPI, Redis, and RabbitMQ. This system is composed of three core microservices that handle orchestration, user data, and dynamic content rendering.

## 🚀 Features

- **Resilient Architecture**: Circuit breakers, retries, and dead-letter queues
- **High Performance**: Redis caching and async database operations
- **Scalable**: Microservices architecture with message queuing
- **Developer Friendly**: Well-documented REST APIs with OpenAPI documentation
- **Observable**: Comprehensive logging and health checks

## 📦 Services Overview

### 1. API Gateway (`api_gateway.py`)

The main entry point that orchestrates the notification flow, handling request validation, service coordination, and message queuing.

**Key Features:**
- Request validation and routing
- Circuit breaker pattern for fault tolerance
- Message queue integration (RabbitMQ)
- Service discovery and load balancing
- Synchronous and asynchronous processing

### 2. User Service (`user_service.py`)

Manages user data and notification preferences with PostgreSQL database integration.

**Key Features:**
- User profile management
- Notification preferences
- Multi-language support
- Database connection pooling
- Health monitoring

### 3. Template Service (`template_service.py`)

Handles template storage, versioning, and dynamic content rendering.

**Key Features:**
- Template management (CRUD)
- Dynamic content rendering
- Redis caching
- Template versioning
- Health monitoring

## 📚 API Endpoints

### API Gateway
- `POST /notify` - Send a notification
  ```json
  {
    "user_id": "uuid-here",
    "template_key": "WELCOME_EMAIL",
    "message_data": {"name": "John", "verification_link": "https://..."}
  }
  ```

### User Service
- `GET /users/{user_id}` - Get user profile
- `POST /users` - Create new user
  ```json
  {
    "email_address": "user@example.com",
    "phone_number": "+1234567890",
    "preferred_language": "en-US",
    "preferences": {
      "email_enabled": true,
      "push_enabled": true,
      "quiet_hours_start": "22:00",
      "quiet_hours_end": "08:00"
    }
  }
  ```

### Template Service
- `POST /templates` - Create new template
  ```json
  {
    "template_key": "WELCOME_EMAIL",
    "subject": "Welcome, {name}!",
    "body": "Hello {name}, welcome to our service!",
    "html_body": "<h1>Welcome, {name}!</h1><p>Thank you for joining us!</p>"
  }
  ```
- `POST /templates/render` - Render template with data
  ```json
  {
    "template_key": "WELCOME_EMAIL",
    "message_data": {"name": "John"}
  }
  ```

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.8+
- RabbitMQ
- Redis
- PostgreSQL (Neon)

### Environment Variables
Create a `.env` file with the following variables:
```
# API Gateway
INTERNAL_API_SECRET=your-secret-key
USER_SERVICE_URL=http://localhost:8001
TEMPLATE_SERVICE_URL=http://localhost:8002
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# User Service
NEON_DATABASE_URL=postgresql://user:pass@host/db

# Template Service
REDIS_URL=redis://localhost:6379/0
```

### Installation
1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the services:
   ```bash
   # Terminal 1 - User Service
   uvicorn user_service:app --port 8001
   
   # Terminal 2 - Template Service
   uvicorn template_service:app --port 8002
   
   # Terminal 3 - API Gateway
   uvicorn api_gateway:app --port 8000
   ```

## 🚦 Testing

Run the test suite:
```bash
pytest test_*.py
```

## 📊 Monitoring

Each service provides health check endpoints:
- `GET /health` - Service health status
- `GET /health/db` - Database connection status
- `GET /health/redis` - Redis connection status

## 📝 Message Queue

The system uses RabbitMQ for asynchronous processing. The following queues are set up:
- `notifications.email` - For email notifications
- `notifications.push` - For push notifications
- `failed.queue` - Dead letter queue for failed messages

## 🔧 Troubleshooting

1. **Message not delivered**
   - Check RabbitMQ management console
   - Verify queue consumers are running
   - Check service logs for errors

2. **Template rendering issues**
   - Verify template exists in the template service
   - Check that all required variables are provided
   - Check Redis cache status

3. **Database connection problems**
   - Verify database URL in .env
   - Check if the database is accessible
   - Review connection pool settings

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting pull requests.

🚀 Prerequisites (Local Development)

Python 3.8+

Redis Server (e.g., via Upstash or local Docker)

RabbitMQ Server (e.g., via Render or local Docker)

PostgreSQL (e.g., via Neon or local Docker)

pip (Python package manager)

🔧 Installation

Clone the repository:

git clone <repository-url>
cd HNGstage4


Create and activate a virtual environment:

python -m venv venv
# On Unix or MacOS:
source venv/bin/activate


Install dependencies:

pip install -r requirements.txt


Set up environment variables:
Create a .env file in the root directory. Note the use of separate REDIS_HOST and REDIS_PORT.

# API Gateway Security
INTERNAL_API_SECRET=your-super-secret-key-change-this

# Redis (Upstash) Configuration
REDIS_HOST=localhost 
REDIS_PORT=6379 

# RabbitMQ (Render) Configuration
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Service Discovery URLs (Change to Leapcell/Render internal domains in production)
USER_SERVICE_URL=http://localhost:8001
TEMPLATE_SERVICE_URL=http://localhost:8002

# Database (Neon) Configuration - Used by User and Template Services
NEON_DATABASE_URL=postgresql://user:password@localhost:5432/yourdb


🏃‍♂️ Running the Services (Local)

1. Start External Dependencies

Start your local PostgreSQL, Redis, and RabbitMQ containers/servers.

2. Start the Services

API Gateway (Port 8000)

uvicorn api_gateway:app --port 8000 --reload


User Service (Port 8001)

uvicorn USER.user_service:app --port 8001 --reload


Template Service (Port 8002)

uvicorn TEMPLATE.template_service:app --port 8002 --reload


🌐 API Endpoints & Standards

System-Wide API Standard

All synchronous API responses across the Gateway, User, and Template services adhere to this uniform structure to ensure consistency and facilitate automated consumption.

{
  "success": boolean,
  "data"?: T,
  "error"?: string,
  "message": string,
  "meta": {
    "total": number,
    "limit": number,
    "page": number,
    "total_pages": number,
    "has_next": boolean,
    "has_previous": boolean
  }
}


API Gateway Endpoints

POST /v1/notifications - Send a notification request, which is queued for async processing.

GET /v1/health - Health check (confirms dependencies are running).

User Service Endpoints

GET /v1/users/{user_id} - Get user profile and preferences.

GET /v1/health - Enhanced health check (DB/Redis status).

Template Service Endpoints

POST /v1/templates/render - Render a template with dynamic data.

POST /v1/templates - Create a new template.

GET /v1/health - Enhanced health check (DB/Redis status).

🔄 Dependencies

FastAPI - High-performance web framework

Pydantic - Data validation

pybreaker - Circuit breaker implementation (Crucial for API Gateway resilience)

pika - RabbitMQ client for publishing messages

redis - Redis client (Used for caching and Idempotency checks)

asyncpg - Async PostgreSQL client (Database connection to Neon)

python-dotenv - Environment variable management

requests - Synchronous HTTP client (API Gateway for internal communication)

🧪 Testing

Run the test suite:

pytest


📝 License

This project is licensed under the MIT License - see the LICENSE file for details.