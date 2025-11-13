import asyncio
import nest_asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any, Dict

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.template_service import (
    app as original_app,
    initialize_db,
    shutdown_event,
    DB_POOL,
    IS_MOCK_MODE,
    MOCK_TEMPLATES
)
from utils.redis_client import get_redis_client

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Test data
def get_test_template():
    """Return a test template with a unique key"""
    timestamp = int(time.time())
    return {
        "template_key": f"TEST_TEMPLATE_{timestamp}",
        "subject": "Test {name}",
        "body": "Hello {name}, this is a test.",
        "html_body": "<h1>Hello {name}</h1><p>This is a test.</p>"
    }

TEST_RENDER_DATA = {"name": "Tester"}
TEST_HEADERS = {"X-Internal-Secret": "super-secret-dev-key"}

# Create a test app with overridden settings
@pytest.fixture(scope="module")
def app() -> FastAPI:
    # Override environment variables for testing
    os.environ["INTERNAL_API_SECRET"] = "super-secret-dev-key"
    os.environ["NEON_DATABASE_URL"] = "postgresql://user:pass@localhost/test_db"
    return original_app

# Test client with database setup
@pytest.fixture(scope="module")
def client(app: FastAPI) -> TestClient:
    # Create a test client
    test_client = TestClient(app)
    
    # Initialize the database before tests run
    async def setup():
        # Clear any existing mock data
        if IS_MOCK_MODE:
            MOCK_TEMPLATES.clear()
        await initialize_db()
    
    # Run the async setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup())
    
    yield test_client
    
    # Cleanup after tests
    async def teardown():
        await shutdown_event()
    
    loop.run_until_complete(teardown())
    loop.close()

# Test cases
def test_create_template(client: TestClient):
    # Get a unique test template
    test_template = get_test_template()
    
    # Clear any existing test data
    if IS_MOCK_MODE:
        MOCK_TEMPLATES.clear()
    
    # Clear Redis cache for this template
    redis = get_redis_client()
    cache_key = f"template:{test_template['template_key']}"
    asyncio.get_event_loop().run_until_complete(redis.delete(cache_key))
    
    response = client.post(
        "/v1/templates",
        json=test_template,
        headers=TEST_HEADERS
    )
    
    if IS_MOCK_MODE:
        # In mock mode, the template should be in MOCK_TEMPLATES
        assert test_template["template_key"] in MOCK_TEMPLATES
    
    assert response.status_code == 201, f"Expected status 201, got {response.status_code}: {response.text}"
    assert response.json()["message"] == f"Template '{test_template['template_key']}' created successfully."

def test_render_template(client: TestClient):
    # Get a unique test template
    test_template = get_test_template()

    # Clear any existing test data
    if IS_MOCK_MODE:
        MOCK_TEMPLATES.clear()
        # Add test template directly to mock storage
        MOCK_TEMPLATES[test_template["template_key"]] = {
            "subject": test_template["subject"],
            "body": test_template["body"],
            "html_body": test_template["html_body"]
        }
    else:
        # In non-mock mode, first check if template exists
        check_response = client.get(
            f"/v1/templates/{test_template['template_key']}",
            headers=TEST_HEADERS
        )

        # Only create if it doesn't exist
        if check_response.status_code == 404:
            create_response = client.post(
                "/v1/templates",
                json=test_template,
                headers=TEST_HEADERS
            )
            assert create_response.status_code == 201, f"Failed to create test template: {create_response.text}"

    # Clear Redis cache before test if Redis is available
    try:
        redis = get_redis_client()
        cache_key = f"template:{test_template['template_key']}"
        asyncio.get_event_loop().run_until_complete(redis.delete(cache_key))
    except Exception as e:
        print(f"Warning: Could not clear Redis cache: {e}")

    # Test rendering
    response = client.post(
        "/v1/templates/render",
        json={
            "template_key": test_template["template_key"],
            "message_data": TEST_RENDER_DATA
        },
        headers=TEST_HEADERS
    )

    assert response.status_code == 200, f"Expected status 200, got {response.status_code}: {response.text}"
    data = response.json()
    
    # Check the response structure
    assert "data" in data, f"Expected 'data' key in response, got: {data}"
    assert "subject" in data["data"], f"Expected 'subject' in data, got: {data}"
    assert data["data"]["subject"] == f"Test {TEST_RENDER_DATA['name']}"
    assert TEST_RENDER_DATA['name'] in data["data"]["body"]
    assert TEST_RENDER_DATA['name'] in data["data"]["html_body"]

def test_health_check(client: TestClient):
    """Test the health check endpoint"""
    response = client.get("/v1/health")
    
    # Check if the response is successful (200) or service unavailable (503)
    if response.status_code == 200:
        data = response.json()
        
        # Check the response structure for successful health check
        assert "data" in data, "Health check response missing 'data' field"
        assert "status" in data["data"], "Health check response missing 'status' in 'data' field"
        assert data["data"]["status"] in ["healthy", "degraded"], f"Unexpected status value: {data['data']['status']}"
        
        # Check required fields in the response
        assert "version" in data["data"], "Missing version in health check response"
        assert "services" in data["data"], "Missing services in health check response"
        
        # Check service statuses
        services = data["data"]["services"]
        assert "postgresql" in services, "Missing postgresql service status"
        assert "redis" in services, "Missing redis service status"
        
    elif response.status_code == 503:
        # For service unavailable, check error structure
        data = response.json()
        assert "error" in data, "Error response missing 'error' field"
        assert data.get("message") == "Service unavailable", "Unexpected error message"
    else:
        # For any other status code, fail the test
        assert False, f"Unexpected status code: {response.status_code}. Response: {response.text}"

def test_missing_template(client: TestClient):
    # This test should work in both mock and real mode
    # First ensure the template doesn't exist
    non_existent_key = "NON_EXISTENT_TEMPLATE_" + str(hash("test"))
    
    response = client.post(
        "/v1/templates/render",
        json={
            "template_key": non_existent_key,
            "message_data": {}
        },
        headers=TEST_HEADERS
    )
    assert response.status_code == 404, f"Expected 404 for non-existent template, got {response.status_code}: {response.text}"

if __name__ == "__main__":
    pytest.main(["-v"])
