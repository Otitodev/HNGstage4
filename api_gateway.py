import os
import json
import logging
import sys
import uuid
import time
import asyncio
import httpx
import pika
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Header, Request, Depends
from pydantic import BaseModel, Field
import redis
from redis import Redis

# Import utilities
from utils.response_formatter import success_response, error_response
from utils.retry_utils import retry_with_backoff, MaxRetriesExceededError
from utils.idempotency import IdempotencyManager, IdempotencyError, IdempotencyKeyMissing, idempotent

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Load environment variables
try:
    load_dotenv()
except ImportError:
    pass

import requests
import pybreaker
from fastapi import FastAPI, HTTPException, status, Header
from pydantic import BaseModel, Field

# Conditional import for RabbitMQ client
try:
    import pika
    HAS_MQ_DRIVER = True
except ImportError:
    HAS_MQ_DRIVER = False

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Configuration (Service Discovery & Secrets) ---

INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "super-secret-dev-key")
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:8001")
TEMPLATE_SERVICE_URL = os.environ.get("TEMPLATE_SERVICE_URL", "http://localhost:8002")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# --- Circuit Breaker Setup ---

# Breaker for the User Service: Fails after 5 consecutive connection errors. Resets after 60s.
user_breaker = pybreaker.CircuitBreaker(
    fail_max=5, 
    reset_timeout=60,
    exclude=[requests.exceptions.HTTPError]
)

# Breaker for the Template Service
template_breaker = pybreaker.CircuitBreaker(
    fail_max=5, 
    reset_timeout=60,
    exclude=[requests.exceptions.HTTPError]
)

# --- Redis Client Setup ---

# --- Redis Client Setup ---
def get_redis() -> Redis:
    """Get Redis client instance."""
    try:
        from upstash_redis import Redis as UpstashRedis
        rest_url = os.getenv('UPSTASH_REDIS_REST_URL')
        token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        if rest_url and token:
            return UpstashRedis(url=rest_url, token=token)
        
        # Fallback to local Redis if Upstash config is not complete
        import redis
        return redis.Redis.from_url(
            'redis://localhost:6379/0',
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

async def health_check(redis: Redis = Depends(get_redis)):
    """Health check endpoint that verifies all dependencies."""
    # Check Redis
    redis_status = "healthy"
    try:
        # Check if the Redis client is from upstash_redis (which is synchronous)
        if hasattr(redis, '_client'):
            # Upstash Redis (synchronous)
            result = redis.ping()
            if result != "PONG":
                raise ValueError(f"Unexpected ping response: {result}")
        else:
            # Standard redis-py with async support
            result = await redis.ping()
            if not result:
                raise ValueError("Redis ping failed")
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    
    # Rest of your health check code remains the same...
    rabbitmq_status = "healthy"
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        connection.close()
    except Exception as e:
        rabbitmq_status = f"unhealthy: {str(e)}"
    
    # Check dependent services
    services_to_check = [
        (USER_SERVICE_URL, "user-service"),
        (TEMPLATE_SERVICE_URL, "template-service")
    ]
    
    service_statuses = await asyncio.gather(
        *[check_service_health(url, name) for url, name in services_to_check],
        return_exceptions=True
    )
    
    # Process service statuses...
    service_statuses = [
        {
            "service": name,
            "status": "unreachable",
            "error": str(status) if isinstance(status, Exception) else "Unknown error",
            "response_time_ms": None
        } if isinstance(status, Exception) else status
        for status, (_, name) in zip(service_statuses, services_to_check)
    ]
    
    all_healthy = all(
        s.get("status") == "healthy" 
        for s in service_statuses
    ) and redis_status == "healthy" and rabbitmq_status == "healthy"
    
    return success_response(
        data={
            "status": "healthy" if all_healthy else "degraded",
            "dependencies": {
                "redis": redis_status,
                "rabbitmq": rabbitmq_status,
                "services": service_statuses
            }
        },
        message="Service status" if all_healthy else "One or more services are unavailable",
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )

# Initialize idempotency manager
idempotency_manager = None
try:
    redis_client = get_redis()
    idempotency_manager = IdempotencyManager(redis_client)
    logger.info("Idempotency manager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize idempotency manager: {str(e)}")
    idempotency_manager = None

# --- Define External API Contract ---

class NotificationRequest(BaseModel):
    user_id: str = Field(..., description="The ID of the target user.")
    template_key: str = Field(..., description="The unique key of the template to use.")
    message_data: Dict[str, Any] = Field(..., description="Data for template interpolation.")

# --- RabbitMQ Publisher (Synchronous) ---
# (Unchanged from previous version, omitted for brevity but present in the file)
def publish_to_queue(payload: Dict[str, Any], queue_name: str = "notifications"):
    if not HAS_MQ_DRIVER:
        logger.warning(f"MQ Driver missing. Mocking publish of payload: {payload.get('user_id')}")
        return
    
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(payload).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
        connection.close()
        logger.info(f"Successfully published notification for user {payload.get('user_id')}.")

    except Exception as e:
        logger.error(f"Failed to connect or publish to RabbitMQ. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message Queue service is unavailable. Cannot enqueue notification."
        )


# --- FastAPI Application Setup ---
app = FastAPI(
    title="API Gateway (Notification Orchestrator)",
    version="1.0.0",
    description="Orchestrates notification delivery with retry and idempotency support"
)

# Add middleware for request/response logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    
    # Log request
    logger.info(f"Request: {request.method} {request.url} - RequestID: {request_id}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    logger.info(f"Response: {request.method} {request.url} - Status: {response.status_code} - RequestID: {request_id}")
    
    # Ensure request ID is in response headers
    response.headers["X-Request-ID"] = request_id
    return response

# Update the check_service_health function in api_gateway.py
async def check_service_health(url: str, service_name: str) -> Dict[str, Any]:
    """Check the health of a dependent service."""
    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/v1/health")
            response.raise_for_status()
            data = response.json()
            
            # Handle different response formats
            if service_name == "user-service":
                service_data = data.get("data", {})
                status_value = service_data.get("status", "unknown")
                details = service_data.get("dependencies", {})
            else:  # template-service
                service_data = data.get("data", {})
                status_value = service_data.get("status", "unknown")
                details = service_data.get("services", {})
            
            return {
                "service": service_name,
                "status": status_value,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "details": details
            }
    except Exception as e:
        return {
            "service": service_name,
            "status": "unreachable",
            "error": str(e),
            "response_time_ms": None
        }

# --- Root Endpoint ---
@app.get("/", include_in_schema=True)
async def root():
    """Root endpoint to verify the service is running."""
    return success_response(
        data={"service": "API Gateway"},
        message="API Gateway is running"
    )

@app.get("/health", status_code=200, include_in_schema=True)
async def health_check_endpoint(redis: Redis = Depends(get_redis)):
    """Health check endpoint that verifies all dependencies."""
    # Check Redis
    redis_status = "healthy"
    try:
        # Check if the Redis client is from upstash_redis (which is synchronous)
        if hasattr(redis, '_client'):
            # Upstash Redis (synchronous)
            result = redis.ping()
            if result != "PONG":
                raise ValueError(f"Unexpected ping response: {result}")
        else:
            # Standard redis-py with async support
            result = await redis.ping()
            if not result:
                raise ValueError("Redis ping failed")
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    
    # Check RabbitMQ
    rabbitmq_status = "healthy"
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        connection.close()
    except Exception as e:
        rabbitmq_status = f"unhealthy: {str(e)}"
    
    # Check dependent services
    services_to_check = [
        (USER_SERVICE_URL, "user-service"),
        (TEMPLATE_SERVICE_URL, "template-service")
    ]
    
    service_statuses = await asyncio.gather(
        *[check_service_health(url, name) for url, name in services_to_check],
        return_exceptions=True
    )
    
    # Convert any exceptions to error responses
    service_statuses = [
        {
            "service": name,
            "status": "unreachable",
            "error": str(status) if isinstance(status, Exception) else "Unknown error",
            "response_time_ms": None
        } if isinstance(status, Exception) else status
        for status, (_, name) in zip(service_statuses, services_to_check)
    ]
    
    all_healthy = all(
        s.get("status") == "healthy" 
        for s in service_statuses
    ) and redis_status == "healthy" and rabbitmq_status == "healthy"
    
    return success_response(
        data={
            "status": "healthy" if all_healthy else "degraded",
            "dependencies": {
                "redis": redis_status,
                "rabbitmq": rabbitmq_status,
                "services": service_statuses
            }
        },
        message="Service status" if all_healthy else "One or more services are unavailable",
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )

# --- Main Orchestration Endpoint (UPDATED) ---

# Helper function to encapsulate User Service call under the breaker
@user_breaker
def call_user_service(user_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Protected call to the User Service."""
    user_url = f"{USER_SERVICE_URL}/v1/users/{user_id}"
    user_response = requests.get(user_url, headers=headers, timeout=5)
    user_response.raise_for_status()  # Raises HTTPError for 4xx/5xx
    
    # Parse the response
    response_data = user_response.json()
    
    # If the response is already in our standard format, return it as-is
    if isinstance(response_data, dict) and 'data' in response_data:
        return response_data
        
    # Otherwise, wrap it in the standard format
    return {
        "success": True,
        "data": response_data,
        "message": "User data retrieved successfully"
    }

# Helper function to create a new user in the User Service
@user_breaker
def create_user_in_user_service(user_data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Create a new user by calling the User Service.
    
    Args:
        user_data: Dictionary containing user data to create
        headers: Headers to include in the request (must include X-Internal-Secret)
        
    Returns:
        Dictionary containing the created user data or error information
    """
    create_user_url = f"{USER_SERVICE_URL}/v1/users"
    
    try:
        response = requests.post(
            create_user_url,
            json=user_data,
            headers=headers,
            timeout=10
        )
        
        # If successful, return the response data
        if response.status_code == status.HTTP_201_CREATED:
            return {
                "success": True,
                "data": response.json(),
                "status_code": response.status_code
            }
            
        # For error responses, include the error details
        error_data = response.json()
        return {
            "success": False,
            "error": error_data.get("error", "Unknown error"),
            "message": error_data.get("message", "Failed to create user"),
            "status_code": response.status_code
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create user in user service: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to connect to User Service",
            "status_code": status.HTTP_503_SERVICE_UNAVAILABLE
        }

# Helper function to encapsulate Template Service call under the breaker
@template_breaker
def call_template_service(payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Protected call to the Template Service."""
    template_url = f"{TEMPLATE_SERVICE_URL}/v1/templates/render"
    template_response = requests.post(template_url, headers=headers, json=payload, timeout=5)
    template_response.raise_for_status()
    return template_response.json()


@app.post(
    "/v1/notifications", 
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a Notification to be Sent",
    response_model=Dict[str, Any]
)
async def send_notification(
    request: NotificationRequest,
    x_idempotency_key: Optional[str] = Header(None, alias='X-Idempotency-Key')
):
    
    headers = {
        "X-Internal-Secret": INTERNAL_API_SECRET,
        "X-Request-ID": str(uuid.uuid4()),  # Add request ID for tracing
        "X-Idempotency-Key": x_idempotency_key or str(uuid.uuid4())
    }
    user_data = None
    rendered_content = None
    
    # Log the incoming request with request ID
    request_id = headers["X-Request-ID"]
    logger.info(f"Processing notification request {request_id} for user {request.user_id}")
    
    # Handle idempotency manually
    if x_idempotency_key and idempotency_manager:
        cached_response = idempotency_manager.check_duplicate(x_idempotency_key)
        if cached_response:
            logger.info(f"Returning cached response for idempotency key: {x_idempotency_key}")
            return cached_response

    # --- Step 1: Fetch User Profile and Preferences (Protected) ---
    try:
        response = call_user_service(request.user_id, headers)
        
        # Check if the response has the expected structure
        if not isinstance(response, dict):
            raise ValueError("Invalid response format from User Service")
            
        # Handle the standardized response format
        if not response.get("success", False):
            return error_response(
                message=response.get("message", "User Service returned an error"),
                error=response.get("error", "Unknown error"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
            
        # Extract user data from the response
        user_data = response.get("data", {})
        if not user_data:
            raise ValueError("No user data found in response")
        
    except pybreaker.CircuitBreakerError:
        error_msg = "User Service is temporarily unavailable (Circuit Breaker OPEN). Try again later."
        logger.error(error_msg)
        return error_response(
            message=error_msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return error_response(
                message=f"User with ID '{request.user_id}' not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )
        logger.error(f"User Service failed (Status: {e.response.status_code}): {e.response.text}")
        return error_response(
            message="User Service returned an unexpected error.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except requests.exceptions.ConnectionError:
        # Connection failures automatically trip the breaker
        error_msg = "User Service is unreachable."
        logger.error(error_msg)
        return error_response(
            message=error_msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except (ValueError, KeyError) as e:
        logger.error(f"Error processing User Service response: {str(e)}")
        return error_response(
            message="Failed to process user data",
            error=str(e),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # --- Step 2: Render Template Content (Protected) ---
    template_payload = {
        "template_key": request.template_key,
        "message_data": request.message_data
    }
    
    try:
        rendered_content = call_template_service(template_payload, headers)
        
    except pybreaker.CircuitBreakerError:
        error_msg = "Template Service is temporarily unavailable (Circuit Breaker OPEN). Try again later."
        logger.error(error_msg)
        return error_response(
            message=error_msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code in (404, 400):
            return error_response(
                message=e.response.json().get("detail", "Template rendering failed due to bad input."),
                status_code=e.response.status_code
            )
        logger.error(f"Template Service failed (Status: {e.response.status_code}): {e.response.text}")
        return error_response(
            message="Template Service returned an unexpected error.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except requests.exceptions.ConnectionError:
        error_msg = "Template Service is unreachable."
        logger.error(error_msg)
        return error_response(
            message=error_msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # --- Step 3 & 4: Orchestrate Final Payload and Publish ---
    try:
        final_payload = {
            "user_id": user_data.get("user_id") or user_data.get("id"),
            "delivery_targets": {
                "email": user_data.get("email") or user_data.get("email_address"),
                "phone": user_data.get("phone") or user_data.get("phone_number", "")
            },
            "user_preferences": user_data.get("preferences", {}),
            "rendered_content": rendered_content,
            "metadata": {
                "template_key": request.template_key,
                "preferred_language": user_data.get("preferred_language", "en")
            }
        }
        
        # Validate required fields
        if not final_payload["user_id"]:
            raise ValueError("User ID is missing in the response")
            
        if not final_payload["delivery_targets"]["email"] and not final_payload["delivery_targets"]["phone"]:
            logger.warning(f"No valid delivery targets found for user {final_payload['user_id']}")
            
    except KeyError as e:
        logger.error(f"Missing required user data field: {str(e)}")
        return error_response(
            message="Incomplete user data received",
            error=f"Missing required field: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    try:
        # Add retry logic with exponential backoff for publishing to queue
        @retry_with_backoff(
            max_retries=3,
            initial_delay=0.1,
            max_delay=5.0,
            factor=2.0,
            jitter=True
        )
        def _publish_with_retry():
            publish_to_queue(final_payload, queue_name="notifications")
            
        _publish_with_retry()
        
        response_data = {
            "notification_id": final_payload.get("user_id"),
            "request_id": request_id,
            "idempotency_key": x_idempotency_key or "auto-generated"
        }
        
        # Store response for idempotency
        if x_idempotency_key and idempotency_manager:
            try:
                idempotency_manager.store_response(x_idempotency_key, response_data)
            except Exception as e:
                logger.warning(f"Failed to store idempotency response: {str(e)}")
        
        logger.info(f"Successfully queued notification {request_id}")
        return success_response(
            data=response_data,
            message="Notification successfully queued for delivery.",
            status_code=status.HTTP_202_ACCEPTED
        )
        
    except MaxRetriesExceededError as e:
        error_msg = f"Failed to publish to queue after multiple retries: {str(e)}"
        logger.error(f"{error_msg}. Request ID: {request_id}")
        return error_response(
            message="Service temporarily unavailable",
            error=error_msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e:
        error_msg = f"Failed to queue notification: {str(e)}"
        logger.error(f"{error_msg}. Request ID: {request_id}")
        return error_response(
            message="Failed to process notification",
            error=error_msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- How to run (Local Development) ---
# 1. Install dependencies: pip install fastapi uvicorn pydantic requests pika python-dotenv
# 2. Set environment variables (e.g., in .env file) for: 
#    - USER_SERVICE_URL (e.g., http://localhost:8001)
#    - TEMPLATE_SERVICE_URL (e.g., http://localhost:8002)
#    - RABBITMQ_URL (e.g., amqp://guest:guest@localhost:5672/)
#    - INTERNAL_API_SECRET
# 3. Run: uvicorn api_gateway:app --port 8000 --reload