"""
Simple test script for Template Service API
"""
import requests
import json

BASE_URL = "http://localhost:8001"
HEADERS = {"X-Internal-Secret": "super-secret-dev-key"}

def test_health_check():
    """Test the health check endpoint"""
    print("\n1. Testing Health Check...")
    response = requests.get(f"{BASE_URL}/v1/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200

def test_create_template():
    """Test creating a new template"""
    print("\n2. Testing Create Template...")
    import time
    template_key = f"TEST_WELCOME_{int(time.time())}"
    template_data = {
        "template_key": template_key,
        "subject": "Welcome to {app_name}, {user_name}!",
        "body": "Hello {user_name}, welcome to {app_name}. We're glad to have you!",
        "html_body": "<h1>Welcome, {user_name}!</h1><p>Thank you for joining {app_name}.</p>"
    }
    response = requests.post(
        f"{BASE_URL}/v1/templates",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=template_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 201

def test_render_template():
    """Test rendering a template with data"""
    print("\n3. Testing Render Template...")
    render_data = {
        "template_key": "ORDER_CONFIRMATION",
        "message_data": {
            "customer_name": "John Doe",
            "order_id": "ORD-12345",
            "tracking_link": "https://example.com/track/12345"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/templates/render",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=render_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_render_nonexistent_template():
    """Test rendering a non-existent template"""
    print("\n4. Testing Render Non-existent Template...")
    render_data = {
        "template_key": "NONEXISTENT_TEMPLATE",
        "message_data": {
            "name": "Test"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/templates/render",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=render_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 404

def test_unauthorized_access():
    """Test accessing without proper authentication"""
    print("\n5. Testing Unauthorized Access...")
    response = requests.post(
        f"{BASE_URL}/v1/templates/render",
        headers={"Content-Type": "application/json"},
        json={"template_key": "TEST", "message_data": {}}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    # FastAPI returns 422 for missing required headers
    return response.status_code == 422

if __name__ == "__main__":
    print("=" * 60)
    print("TEMPLATE SERVICE API TESTS")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health_check),
        ("Create Template", test_create_template),
        ("Render Template", test_render_template),
        ("Render Non-existent Template", test_render_nonexistent_template),
        ("Unauthorized Access", test_unauthorized_access),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, "✓ PASSED" if passed else "✗ FAILED"))
        except Exception as e:
            print(f"ERROR: {str(e)}")
            results.append((name, f"✗ ERROR: {str(e)}"))
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    for name, result in results:
        print(f"{name}: {result}")
    print("=" * 60)
