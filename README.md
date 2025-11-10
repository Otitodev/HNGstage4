Notification System Microservices

A distributed notification system designed for resilience and scalability, built with FastAPI, Redis, and RabbitMQ.

This system is composed of three core microservices that handle orchestration, user data, and dynamic content rendering.

📦 Services Overview

1. API Gateway (api_gateway.py)

The main entry point that orchestrates the entire notification flow, making synchronous calls to downstream services and handling asynchronous queuing.

Key Features:

Request validation and routing

Circuit breaker pattern for fault tolerance against service failure

Message queue integration (RabbitMQ)

Service discovery and load balancing

2. User Service (USER/user_service.py)

Manages user data and notification preferences, utilizing a dedicated PostgreSQL database.

Key Features:

User profile and preference management

Enhanced multi-language support

Database integration with connection pooling (Neon)

Enhanced /health checks for database and Redis status

3. Template Service (TEMPLATE/template_service.py)

Handles template storage, versioning, and dynamic content rendering using data provided by the API Gateway.

Key Features:

Template storage and versioning

Dynamic content rendering (Jinja2/string interpolation)

Caching template content with Redis for performance

Enhanced /health checks for database and Redis status

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