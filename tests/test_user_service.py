"""
Simple test script for User Service API
"""
import requests
import json

BASE_URL = "http://localhost:8002"
HEADERS = {"X-Internal-Secret": "super-secret-dev-key"}

def test_health_check():
    """Test the health check endpoint"""
    print("\n1. Testing Health Check...")
    response = requests.get(f"{BASE_URL}/v1/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200

def test_get_user():
    """Test getting an existing user"""
    print("\n2. Testing Get User (user-123)...")
    response = requests.get(f"{BASE_URL}/v1/users/user-123", headers=HEADERS)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200

def test_get_nonexistent_user():
    """Test getting a non-existent user"""
    print("\n3. Testing Get Non-existent User...")
    response = requests.get(f"{BASE_URL}/v1/users/nonexistent", headers=HEADERS)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 404


def test_create_user():
    """Test creating a new user"""
    print("\n4. Testing Create User...")
    user_data = {
        "email_address": f"testuser_{hash('test')}@example.com",
        "phone_number": "+1234567890",
        "preferred_language": "en-US",
        "preferences": {
            "email_enabled": True,
            "push_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
    }
    response = requests.post(
        f"{BASE_URL}/v1/users",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=user_data
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 201

def test_unauthorized_access():
    """Test accessing without proper authentication"""
    print("\n5. Testing Unauthorized Access...")
    response = requests.get(f"{BASE_URL}/v1/users/user-123")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    # FastAPI returns 422 for missing required headers
    return response.status_code == 422

if __name__ == "__main__":
    print("=" * 60)
    print("USER SERVICE API TESTS")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health_check),
        ("Get Existing User", test_get_user),
        ("Get Non-existent User", test_get_nonexistent_user),
        ("Create New User", test_create_user),
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
