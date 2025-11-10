import os
from typing import Optional, Any, Dict, Union
from upstash_redis import Redis
from dotenv import load_dotenv
import json

load_dotenv()

class RedisClient:
    _instance = None
    _client: Optional[Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialize_client()
        return cls._instance
    
    def _initialize_client(self):
        """Initialize Upstash Redis client."""
        redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        
        if not redis_url or not redis_token:
            raise ValueError("Redis configuration is missing in environment variables")
        
        # Initialize Upstash Redis client
        self._client = Redis(url=redis_url, token=redis_token)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis."""
        try:
            value = self._client.get(key)
            if value is not None:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            print(f"Redis get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiration."""
        try:
            serialized_value = json.dumps(value)
            if ex:
                self._client.setex(key, ex, serialized_value)
            else:
                self._client.set(key, serialized_value)
            return True
        except Exception as e:
            print(f"Redis set error: {e}")
            return False
    
    async def delete(self, *keys) -> int:
        """Delete one or more keys from Redis."""
        try:
            return self._client.delete(*keys)
        except Exception as e:
            print(f"Redis delete error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            print(f"Redis exists error: {e}")
            return False
    
    async def ping(self) -> bool:
        """Ping the Redis server."""
        try:
            return await self._client.ping()
        except Exception as e:
            print(f"Redis ping error: {e}")
            return False

# Singleton instance
redis_client = RedisClient()

# Helper function for dependency injection
def get_redis_client() -> RedisClient:
    return redis_client