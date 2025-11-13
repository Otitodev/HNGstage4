"""
Simple quick test for API Gateway
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("Testing API Gateway...")
print("=" * 60)

# Test 1: Root endpoint
print("\n1. Root Endpoint")
response = requests.get(f"{BASE_URL}/")
print(f"Status: {response.status_code} - {'✓ PASS' if response.status_code == 200 else '✗ FAIL'}")

# Test 2: Health check
print("\n2. Health Check")
response = requests.get(f"{BASE_URL}/health")
print(f"Status: {response.status_code} - {'✓ PASS' if response.status_code in [200, 503] else '✗ FAIL'}")

# Test 3: Send notification
print("\n3. Send Notification")
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
    json=notification_data,
    timeout=10
)
print(f"Status: {response.status_code} - {'✓ PASS' if response.status_code == 202 else '✗ FAIL'}")
if response.status_code == 202:
    print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 4: Non-existent user
print("\n4. Non-existent User")
notification_data = {
    "user_id": "nonexistent-user",
    "template_key": "ORDER_CONFIRMATION",
    "message_data": {"customer_name": "Test", "order_id": "123", "tracking_link": "http://test"}
}
response = requests.post(
    f"{BASE_URL}/v1/notifications",
    headers={"Content-Type": "application/json"},
    json=notification_data,
    timeout=10
)
print(f"Status: {response.status_code} - {'✓ PASS' if response.status_code == 404 else '✗ FAIL'}")

print("\n" + "=" * 60)
print("Tests completed!")
