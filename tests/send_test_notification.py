"""
Send a test notification to verify the complete flow
"""
import requests
import json

# Your API Gateway URL
API_URL = "https://otitodrichukwu8668-4qj3sovv.leapcell.dev/v1/notifications"

# Test notification
payload = {
    "user_id": "b9a46664-0942-4475-b4fb-bb803655bb01",
    "template_key": "WEEKLY_DIGEST",
    "message_data": {
        "app_name": "MyTestApp",
        "new_updates": "25",
        "digest_link": "https://example.com/digest/week-46"
    }
}

headers = {
    "Content-Type": "application/json",
    "X-Idempotency-Key": "test-local-011"
}

print("Sending test notification...")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

response = requests.post(API_URL, json=payload, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

if response.status_code == 202:
    print("\n✓ Notification queued successfully!")
    print("\nWatch your service logs to see:")
    print("1. Notification Router - routing the message")
    print("2. Email Service - sending the email")
    print("3. Push Service - sending the push notification")
else:
    print("\n✗ Failed to queue notification")
