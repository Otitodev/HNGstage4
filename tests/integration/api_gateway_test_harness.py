import json
import logging
import os
import sys
from typing import Dict, Any, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, status, Header, Request
from pydantic import BaseModel, Field

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("API_GATEWAY_TEST")


# --- CONFIGURATION (Common for all services) ---
# NOTE: We use hardcoded ports and secrets for this single-file test setup
INTERNAL_API_SECRET = "super-secret-test-key"

USER_SERVICE_URL = "http://127.0.0.1:8001"
TEMPLATE_SERVICE_URL = "http://127.0.0.1:8002"
GATEWAY_PORT = 8000


# =====================================================================
#                          MOCK RabbitMQ Publisher
# =====================================================================

# Mock function to replace the actual pika publishing
def publish_to_queue(payload: Dict[str, Any], queue_name: str = "notifications"):
    """Mocks publishing the final payload to a queue."""
    logger.info("--- MOCK RABBITMQ PUBLISHER ---")
    logger.info(f"Successfully QUEUED message to '{queue_name}' for user {payload.get('user_id')}.")
    logger.info("FINAL PAYLOAD DATA:")
    print(json.dumps(payload, indent=4))
    logger.info("-------------------------------")
    return True

# =====================================================================
#                          MOCK USER SERVICE (Port 8001)
# =====================================================================

app_user = FastAPI(title="Mock User Service")

MOCK_USERS: Dict[str, Dict[str, Any]] = {
    "user-123": {
        "user_id": "user-123",
        "email_address": "alice@example.com",
        "phone_number": "+14155550001",
        "preferred_language": "en-US",
        "preferences": {
            "email_enabled": True,
            "push_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
    },
    "user-999": { # Invalid user data for error testing
        "user_id": "user-999",
        "email_address": "error@example.com",
        "phone_number": "+11111111111",
        "preferred_language": "es-ES",
        "preferences": {}
    }
}

@app_user.get("/v1/users/{user_id}")
def get_user_profile_mock(
    user_id: str,
    x_internal_secret: str = Header(..., alias="X-Internal-Secret")
):
    if x_internal_secret != INTERNAL_API_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret.")

    user_data = MOCK_USERS.get(user_id)
    
    if user_id == "user-error":
        # Simulate an internal DB failure
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Mock DB Failure")

    if user_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")
    
    return user_data

logger.info(f"Mock User Service running at: {USER_SERVICE_URL}")


# =====================================================================
#                          MOCK TEMPLATE SERVICE (Port 8002)
# =====================================================================

app_template = FastAPI(title="Mock Template Service")

MOCK_TEMPLATES: Dict[str, Dict[str, str]] = {
    "ORDER_CONFIRMATION": {
        "subject": "Your Order {order_id} is Confirmed!",
        "body": "Hi {customer_name},\n\nThanks for your purchase. Order {order_id} is confirmed.",
        "html_body": "<html><body><h1>Order Confirmed!</h1><p>Hi <b>{customer_name}</b>, order <code>{order_id}</code> is confirmed.</p></body></html>"
    },
    "MISSING_KEY": {
        "subject": "Requires {non_existent_key}",
        "body": "Requires {non_existent_key}",
        "html_body": "Requires {non_existent_key}"
    }
}

class RenderRequest(BaseModel):
    template_key: str
    message_data: Dict[str, Any]

def render_content(template: str, data: Dict[str, Any]) -> str:
    try:
        return template.format(**data)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing data key {e} required.")

@app_template.post("/v1/templates/render")
def render_template_mock(
    request: RenderRequest,
    x_internal_secret: str = Header(..., alias="X-Internal-Secret")
):
    if x_internal_secret != INTERNAL_API_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret.")
    
    template_data = MOCK_TEMPLATES.get(request.template_key)
    
    if template_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{request.template_key}' not found.")

    final_content = {
        "subject": render_content(template_data["subject"], request.message_data),
        "body": render_content(template_data["body"], request.message_data),
        "html_body": render_content(template_data["html_body"], request.message_data)
    }

    return final_content

logger.info(f"Mock Template Service running at: {TEMPLATE_SERVICE_URL}")


# =====================================================================
#                          API GATEWAY (Port 8001)
# =====================================================================

app_gateway = FastAPI(title="API Gateway Orchestrator")

class NotificationRequest(BaseModel):
    user_id: str = Field(..., description="The ID of the target user.")
    template_key: str = Field(..., description="The unique key of the template to use.")
    message_data: Dict[str, Any] = Field(..., description="Data for template interpolation.")


@app_gateway.post(
    "/v1/notifications", 
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a Notification to be Sent"
)
def send_notification(request: NotificationRequest):
    """
    Receives a notification request, fetches user data and preferences, 
    renders the template content, and places the final payload onto the 
    asynchronous notification queue for delivery.
    """
    
    headers = {"X-Internal-Secret": INTERNAL_API_SECRET}
    
    # --- Step 1: Fetch User Profile and Preferences (USER_SERVICE) ---
    try:
        user_url = f"{USER_SERVICE_URL}/v1/users/{request.user_id}"
        logger.info(f"Gateway: Calling User Service for {request.user_id}")
        
        user_response = requests.get(user_url, headers=headers, timeout=5)
        user_response.raise_for_status() 
        user_data = user_response.json()
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID '{request.user_id}' not found."
            )
        # Catch 5xx errors from the downstream service
        if 500 <= e.response.status_code < 600:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"User Service reported an internal error (Status: {e.response.status_code})."
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"User Service error: {e.response.json().get('detail', 'Unknown error.')}"
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User Service is unreachable."
        )
    except Exception as e:
        logger.error(f"Unexpected error during User Service call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during user profile retrieval."
        )

    # --- Step 2: Render Template Content (TEMPLATE_SERVICE) ---
    try:
        template_url = f"{TEMPLATE_SERVICE_URL}/v1/templates/render"
        template_payload = {
            "template_key": request.template_key,
            "message_data": request.message_data
        }
        logger.info(f"Gateway: Calling Template Service for {request.template_key}")
        
        template_response = requests.post(template_url, headers=headers, json=template_payload, timeout=5)
        template_response.raise_for_status()
        rendered_content = template_response.json()
        
    except requests.exceptions.HTTPError as e:
        # Template Service returns 404 (not found) or 400 (missing data key)
        if e.response.status_code in (404, 400):
            raise HTTPException(
                status_code=e.response.status_code,
                detail=e.response.json().get("detail", "Template rendering failed.")
            )
        # Catch 5xx errors from the downstream service
        if 500 <= e.response.status_code < 600:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Template Service reported an internal error (Status: {e.response.status_code})."
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Template Service error: {e.response.json().get('detail', 'Unknown error.')}"
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Template Service is unreachable."
        )
    except Exception as e:
        logger.error(f"Unexpected error during Template Service call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during template rendering."
        )

    # --- Step 3 & 4: Orchestrate Final Payload and Publish (Mocked MQ) ---
    final_payload = {
        "user_id": user_data["user_id"],
        "delivery_targets": {
            "email": user_data["email_address"],
            "phone": user_data["phone_number"]
        },
        "user_preferences": user_data["preferences"],
        "rendered_content": rendered_content,
        "metadata": {
            "template_key": request.template_key,
            "preferred_language": user_data["preferred_language"]
        }
    }
    
    # Use the mock publisher
    publish_to_queue(final_payload, queue_name="notifications")

    # Return 202 Accepted, indicating the job is queued
    return {"message": "Notification successfully queued for asynchronous delivery."}


# =====================================================================
#                          APPLICATION LIFECYCLE
# =====================================================================

def run_test_harness():
    """Starts all three services using Uvicorn's Server class."""
    logger.info("Starting API Gateway Test Harness...")
    
    config_gateway = uvicorn.Config(app_gateway, host="127.0.0.1", port=GATEWAY_PORT, log_level="info")
    server_gateway = uvicorn.Server(config_gateway)
    
    config_user = uvicorn.Config(app_user, host="127.0.0.1", port=8001, log_level="warning")
    server_user = uvicorn.Server(config_user)
    
    config_template = uvicorn.Config(app_template, host="127.0.0.1", port=8002, log_level="warning")
    server_template = uvicorn.Server(config_template)
    
    import threading
    
    def start_server(server, name):
        logger.info(f"Starting {name} on {server.config.host}:{server.config.port}")
        server.run()

    # Start mock services in separate threads
    threading.Thread(target=start_server, args=(server_user, "Mock User Service"), daemon=True).start()
    threading.Thread(target=start_server, args=(server_template, "Mock Template Service"), daemon=True).start()

    # Wait a moment for mock services to spin up
    import time
    time.sleep(1)

    # Start the API Gateway in the main thread
    logger.info(f"Starting API Gateway on {config_gateway.host}:{config_gateway.port}")
    logger.info("Access the interactive documentation at: http://127.0.0.1:8000/docs")
    server_gateway.run()

# Uncomment the line below and run the file to start the harness:
if __name__ == "__main__":
    run_test_harness()

# --- Example of a successful test request you would run in a separate script/terminal ---
# 
# import requests
# API_URL = "http://127.0.0.1:8000/v1/notifications"
# 
# SUCCESS_PAYLOAD = {
#     "user_id": "user-123",
#     "template_key": "ORDER_CONFIRMATION",
#     "message_data": {
#         "order_id": "ODR-745",
#         "customer_name": "Alice"
#     }
# }
# 
# # Example of a successful request:
# # response = requests.post(API_URL, json=SUCCESS_PAYLOAD)
# # print(f"Status: {response.status_code}\nBody: {response.json()}")
# 
# # Example of failure (User Not Found):
# # FAIL_USER_PAYLOAD = SUCCESS_PAYLOAD.copy()
# # FAIL_USER_PAYLOAD['user_id'] = 'user-not-real'
# # response = requests.post(API_URL, json=FAIL_USER_PAYLOAD)
# # print(f"Status: {response.status_code}\nBody: {response.json()}")
# 
# # Example of failure (Missing Template Data):
# # FAIL_TEMPLATE_PAYLOAD = SUCCESS_PAYLOAD.copy()
# # FAIL_TEMPLATE_PAYLOAD['template_key'] = 'MISSING_KEY'
# # response = requests.post(API_URL, json=FAIL_TEMPLATE_PAYLOAD)
# # print(f"Status: {response.status_code}\nBody: {response.json()}")