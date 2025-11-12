# Template Service Documentation

## Overview
The Template Service is a microservice responsible for managing and serving notification templates. It provides a RESTful API for template management and rendering with dynamic data. The service supports both PostgreSQL and Redis for data persistence and caching, with a fallback to in-memory storage when needed.

## Features

- **Template Management**: Create and retrieve templates
- **Template Rendering**: Render templates with dynamic data
- **Multi-format Support**: Support for both HTML and plain text content
- **Variable Interpolation**: Dynamic content rendering with template variables
- **Caching**: Built-in Redis caching for improved performance
- **Health Monitoring**: Health check endpoint for service monitoring
- **Mock Mode**: Fallback to in-memory storage when database is not available

## API Endpoints

### 1. Health Check

```http
GET /v1/health
```

**Headers:**
- `X-Internal-Secret`: (Required) Internal API secret for service-to-service authentication

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Service is running and all dependencies are accessible",
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "services": {
      "postgresql": "connected",
      "redis": "connected"
    }
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "error",
  "message": "Service unavailable",
  "error": "One or more dependencies are unavailable"
}
```

### 2. Create Template

```http
POST /v1/templates
```

**Headers:**
- `X-Internal-Secret`: (Required) Internal API secret for service-to-service authentication

**Request Body:**
```json
{
  "template_key": "WELCOME_EMAIL",
  "subject": "Welcome to {{app_name}}!",
  "body": "Hello {{user.name}}, welcome to {{app_name}}!",
  "html_body": "<h1>Welcome, {{user.name}}!</h1><p>Thank you for joining {{app_name}}.</p>"
}
```

**Response (201 Created):**
```json
{
  "status": "success",
  "message": "Template 'WELCOME_EMAIL' created successfully.",
  "data": {
    "template_key": "WELCOME_EMAIL"
  }
}
```

**Response (409 Conflict):**
```json
{
  "status": "error",
  "message": "Template already exists",
  "error": "Template with key 'WELCOME_EMAIL' already exists."
}
```

**Response (401 Unauthorized):**
```json
{
  "status": "error",
  "message": "Unauthorized",
  "error": "Invalid or missing internal API secret"
}
```

### 3. Render Template

```http
POST /v1/templates/render
```

**Headers:**
- `X-Internal-Secret`: (Required) Internal API secret for service-to-service authentication

**Request Body:**
```json
{
  "template_key": "WELCOME_EMAIL",
  "message_data": {
    "user": {
      "name": "John Doe"
    },
    "app_name": "My Awesome App"
  }
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Template rendered successfully",
  "data": {
    "subject": "Welcome to My Awesome App!",
    "body": "Hello John Doe, welcome to My Awesome App!",
    "html_body": "<h1>Welcome, John Doe!</h1><p>Thank you for joining My Awesome App.</p>"
  }
}
```

**Response (404 Not Found):**
```json
{
  "status": "error",
  "message": "Template not found",
  "error": "Template with key 'NON_EXISTENT_TEMPLATE' not found"
}
```

## Authentication

All endpoints require service-to-service authentication using the `X-Internal-Secret` header. The secret must match the `INTERNAL_API_SECRET` environment variable.

## Error Handling

### Standard Error Response

All error responses follow this format:

```json
{
  "status": "error",
  "message": "Human-readable error message",
  "error": "Detailed error information"
}
```

### Common Error Status Codes

- `400 Bad Request`: Invalid request data or missing required fields
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Requested resource not found
- `409 Conflict`: Resource already exists
- `500 Internal Server Error`: Unexpected server error
- `503 Service Unavailable`: One or more dependencies are unavailable

## Template Variables

Templates use Python's string formatting syntax with curly braces for variable interpolation. For example:

```
Hello {user.name}, welcome to {app_name}!
```

Variables can be nested using dot notation, and the service will safely handle missing variables by leaving them as-is in the output.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEON_DATABASE_URL` | No | `postgresql://user:pass@host/db` | PostgreSQL connection string |
| `INTERNAL_API_SECRET` | Yes | - | Secret key for service-to-service authentication |
| `REDIS_URL` | No | - | Redis connection URL (if not provided, in-memory storage is used) |

## Development

### Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   export INTERNAL_API_SECRET=your-secret-key
   export NEON_DATABASE_URL=your-database-url
   export REDIS_URL=your-redis-url
   ```

3. Run the service:
   ```bash
   uvicorn template_service:app --reload
   ```

### Testing

Run the test suite:

```bash
pytest test_template_service.py -v
```

## Changelog

### v1.0.0
- Initial release
- Template creation and rendering
- Redis caching
- Health check endpoint
