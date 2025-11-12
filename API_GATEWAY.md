I'll update the API_GATEWAY.md file with the correct response format based on the response_formatter implementation. Here's the complete updated content:

```markdown
# API Gateway Documentation

## Overview
The [api_gateway.py](cci:7://file:///c:/Users/USER/Documents/HNGstage4/api_gateway.py:0:0-0:0) implements a robust API Gateway service that orchestrates notification delivery with idempotency, circuit breaking, and retry mechanisms. It acts as a central coordinator between user services, template services, and message queues.

## Key Features

### 1. Core Functionality
- **Notification Orchestration**: Coordinates between user services, template services, and message queues
- **Idempotency Support**: Prevents duplicate processing of the same request
- **Circuit Breaking**: Implements circuit breakers for dependent services
- **Request Tracing**: Includes request IDs for end-to-end tracing
- **Retry Logic**: Implements exponential backoff for queue publishing

### 2. Technical Stack
- **Framework**: FastAPI
- **Message Queue**: RabbitMQ (with fallback to mock when unavailable)
- **Caching/State**: Redis (for idempotency)
- **External Services**: User Service, Template Service

## API Endpoints

### `POST /v1/notifications`
Main endpoint for sending notifications.

**Request Headers:**
- `X-Idempotency-Key`: (Optional) Ensures idempotent operations
- `X-Request-ID`: (Auto-generated if not provided) For request tracing

**Request Body:**
```json
{
    "user_id": "string",
    "template_key": "string",
    "message_data": {
        "key1": "value1",
        "key2": "value2"
    }
}
```

## Response Format

### Success Response (200/202)
```json
{
    "success": true,
    "data": {
        "notification_id": "user-123",
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "idempotency_key": "unique-key-here"
    },
    "message": "Notification successfully queued for delivery.",
    "meta": {
        "total": 1,
        "page": 1,
        "limit": 10,
        "total_pages": 1,
        "has_next": false,
        "has_previous": false
    }
}
```

### Error Response (4xx/5xx)
```json
{
    "success": false,
    "message": "Error description",
    "error": "Detailed error message",
    "meta": {
        "page": 1,
        "limit": 10
    }
}
```

### Response Fields
- `success`: Boolean indicating if the request was successful
- `data`: Main response payload (only present on success)
- `message`: Human-readable message
- `error`: Detailed error message (only present on error)
- `meta`: Pagination metadata (when applicable)
  - `total`: Total number of items
  - `page`: Current page number
  - `limit`: Items per page
  - `total_pages`: Total number of pages
  - `has_next`: Boolean indicating if there's a next page
  - `has_previous`: Boolean indicating if there's a previous page

### Common Status Codes
- `200 OK`: Request successful
- `202 Accepted`: Request accepted for processing
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable (circuit breaker open)

## Configuration

### Environment Variables
```env
# Required
INTERNAL_API_SECRET="your-secret-key"
USER_SERVICE_URL="http://user-service:8001"
TEMPLATE_SERVICE_URL="http://template-service:8002"
RABBITMQ_URL="amqp://guest:guest@rabbitmq:5672/"

# Optional
REDIS_URL="redis://redis:6379/0"  # For idempotency
```

## Circuit Breakers
- **User Service**: Trips after 5 consecutive failures, resets after 60 seconds
- **Template Service**: Trips after 5 consecutive failures, resets after 60 seconds

## Idempotency
- Uses Redis to store idempotency keys
- 24-hour TTL for idempotency keys
- Returns the same response for duplicate requests with the same idempotency key

## Local Development
1. Install dependencies:
   ```bash
   pip install fastapi uvicorn pydantic requests pika python-dotenv redis pybreaker
   ```

2. Set up environment variables in `.env` file

3. Run the service:
   ```bash
   uvicorn api_gateway:app --port 8000 --reload
   ```

## Dependencies
- FastAPI
- Pydantic
- Requests
- Pika (RabbitMQ client)
- Redis
- Pybreaker
- Python-dotenv

## Logging
- Logs include request/response details
- Structured logging with timestamps and log levels
- Request IDs for correlation

## Security
- Internal API key validation
- Secure handling of sensitive data
- No sensitive data in logs

## Monitoring
- Request/response logging
- Error tracking
- Circuit breaker state monitoring

This documentation reflects the current implementation in the codebase and should be updated if the implementation changes.
```

