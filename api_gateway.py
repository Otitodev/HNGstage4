import os
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

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

# --- Circuit Breaker Setup (NEW) ---

# Breaker for the User Service: Fails after 5 consecutive connection errors. Resets after 60s.
user_breaker = pybreaker.CircuitBreaker(
    fail_max=5, 
    reset_timeout=60, 
    # Do NOT trip the breaker for expected HTTP errors (like 404), only network/connection failures
    exclude=[requests.exceptions.HTTPError]
)

# Breaker for the Template Service
template_breaker = pybreaker.CircuitBreaker(
    fail_max=5, 
    reset_timeout=60, 
    exclude=[requests.exceptions.HTTPError]
)

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
app = FastAPI(title="API Gateway (Notification Orchestrator)")


# --- Main Orchestration Endpoint (UPDATED) ---

# Helper function to encapsulate User Service call under the breaker
@user_breaker
def call_user_service(user_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Protected call to the User Service."""
    user_url = f"{USER_SERVICE_URL}/v1/users/{user_id}"
    user_response = requests.get(user_url, headers=headers, timeout=5)
    user_response.raise_for_status() # Raises HTTPError for 4xx/5xx
    return user_response.json()

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
    summary="Request a Notification to be Sent"
)
def send_notification(request: NotificationRequest):
    
    headers = {"X-Internal-Secret": INTERNAL_API_SECRET}
    user_data = None
    rendered_content = None

    # --- Step 1: Fetch User Profile and Preferences (Protected) ---
    try:
        user_data = call_user_service(request.user_id, headers)
        
    except pybreaker.CircuitBreakerError:
        logger.error("User Service Circuit Breaker is OPEN. Failing fast.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User Service is temporarily unavailable (Circuit Breaker OPEN). Try again later."
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID '{request.user_id}' not found."
            )
        logger.error(f"User Service failed (Status: {e.response.status_code}): {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User Service returned an unexpected error."
        )
    except requests.exceptions.ConnectionError:
        # Connection failures automatically trip the breaker
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User Service is unreachable."
        )

    # --- Step 2: Render Template Content (Protected) ---
    template_payload = {
        "template_key": request.template_key,
        "message_data": request.message_data
    }
    
    try:
        rendered_content = call_template_service(template_payload, headers)
        
    except pybreaker.CircuitBreakerError:
        logger.error("Template Service Circuit Breaker is OPEN. Failing fast.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Template Service is temporarily unavailable (Circuit Breaker OPEN). Try again later."
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code in (404, 400):
            raise HTTPException(
                status_code=e.response.status_code,
                detail=e.response.json().get("detail", "Template rendering failed due to bad input.")
            )
        logger.error(f"Template Service failed (Status: {e.response.status_code}): {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Template Service returned an unexpected error."
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Template Service is unreachable."
        )

    # --- Step 3 & 4: Orchestrate Final Payload and Publish ---
    final_payload = {
        "user_id": user_data["user_id"],
        "delivery_targets": {"email": user_data["email_address"], "phone": user_data["phone_number"]},
        "user_preferences": user_data["preferences"],
        "rendered_content": rendered_content,
        "metadata": {"template_key": request.template_key, "preferred_language": user_data["preferred_language"]}
    }
    
    publish_to_queue(final_payload, queue_name="notifications")

    return {"message": "Notification successfully queued for delivery."}

# --- How to run (Local Development) ---
# 1. Install dependencies: pip install fastapi uvicorn pydantic requests pika python-dotenv
# 2. Set environment variables (e.g., in .env file) for: 
#    - USER_SERVICE_URL (e.g., http://localhost:8001)
#    - TEMPLATE_SERVICE_URL (e.g., http://localhost:8002)
#    - RABBITMQ_URL (e.g., amqp://guest:guest@localhost:5672/)
#    - INTERNAL_API_SECRET
# 3. Run: uvicorn api_gateway:app --port 8000 --reload