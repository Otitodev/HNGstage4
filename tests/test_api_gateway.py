"""
Simple test script for API Gateway
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test the health check endpoint"""
    print("\n1. Testing Health Check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code in [200, 503]  # Accept both healthy and degraded

def test_root_endpoint():
    """Test the root endpoint"""
    print("\n2. Testing Root Endpoint...")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200

def test_send_notification():
    """Test sending a notification"""
    print("\n3. Testing Send Notification...")
    notification_data = {
        "user_id": "user-123",
        "template_key": "ORDER_CONFIRMATION",
        "message_data": {
            "customer_name": "Alice",
            "order_id": "ORD-98765",
            "tracking_link": "https://example.com/track/98765"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/notifications",
        headers={"Content-Type": "application/json"},
        json=notification_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 202

def test_send_notification_with_idempotency():
    """Test sending a notification with idempotency key"""
    print("\n4. Testing Send Notification with Idempotency...")
    idempotency_key = f"test-key-{int(time.time())}"
    notification_data = {
        "user_id": "user-456",
        "template_key": "PASSWORD_RESET",
        "message_data": {
            "customer_name": "Bob",
            "app_name": "TestApp",
            "reset_link": "https://example.com/reset/token123"
        }
    }
    
    # Send first request
    response1 = requests.post(
        f"{BASE_URL}/v1/notifications",
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key
        },
        json=notification_data
    )
    print(f"First Request Status: {response1.status_code}")
    print(f"First Response: {json.dumps(response1.json(), indent=2)}")
    
    # Send duplicate request with same idempotency key
    time.sleep(1)
    response2 = requests.post(
        f"{BASE_URL}/v1/notifications",
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key
        },
        json=notification_data
    )
    print(f"\nSecond Request Status: {response2.status_code}")
    print(f"Second Response: {json.dumps(response2.json(), indent=2)}")
    
    # Both should succeed and return same response
    return response1.status_code == 202 and response2.status_code == 202

def test_nonexistent_user():
    """Test sending notification to non-existent user"""
    print("\n5. Testing Non-existent User...")
    notification_data = {
        "user_id": "nonexistent-user",
        "template_key": "ORDER_CONFIRMATION",
        "message_data": {
            "customer_name": "Test",
            "order_id": "ORD-00000",
            "tracking_link": "https://example.com/track/00000"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/notifications",
        headers={"Content-Type": "application/json"},
        json=notification_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 404

def test_nonexistent_template():
    """Test sending notification with non-existent template"""
    print("\n6. Testing Non-existent Template...")
    notification_data = {
        "user_id": "user-123",
        "template_key": "NONEXISTENT_TEMPLATE",
        "message_data": {
            "test": "data"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/notifications",
        headers={"Content-Type": "application/json"},
        json=notification_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 404

if __name__ == "__main__":
    print("=" * 60)
    print("API GATEWAY TESTS")
    print("=" * 60)
    print("\nMake sure the following services are running:")
    print("- User Service on port 8002")
    print("- Template Service on port 8001")
    print("- RabbitMQ on configured URL")
    print("- Redis on configured URL")
    
    tests = [
        ("Health Check", test_health_check),
        ("Root Endpoint", test_root_endpoint),
        ("Send Notification", test_send_notification),
        ("Idempotency", test_send_notification_with_idempotency),
        ("Non-existent User", test_nonexistent_user),
        ("Non-existent Template", test_nonexistent_template),
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
