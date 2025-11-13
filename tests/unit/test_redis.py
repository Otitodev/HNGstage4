import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from utils.redis_client import get_redis_client

async def test_redis_connection():
    redis = get_redis_client()
    
    # Test set and get
    test_key = "test_key"
    test_value = {"hello": "world"}
    
    # Set a value
    await redis.set(test_key, test_value)
    print(f"Set value: {test_value}")
    
    # Get the value back
    result = await redis.get(test_key)
    print(f"Got value: {result}")
    
    # Test delete
    await redis.delete(test_key)
    print(f"Deleted key: {test_key}")
    
    # Verify deletion
    exists = await redis.exists(test_key)
    print(f"Key exists after deletion: {exists}")

if __name__ == "__main__":
    asyncio.run(test_redis_connection())
