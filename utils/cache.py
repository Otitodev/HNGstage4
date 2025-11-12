import json
import logging
import os
from typing import Any, Optional
from functools import wraps
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_redis_client() -> Optional[Redis]:
    """Get a Redis client instance using Upstash."""
    try:
        redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        
        if not redis_url or not redis_token:
            logger.warning("Redis configuration is missing in environment variables")
            return None
        
        return Redis(url=redis_url, token=redis_token)
    except Exception as e:
        logger.error(f"Failed to create Redis client: {str(e)}")
        return None


class CacheManager:
    """
    A Redis-based caching utility with TTL and automatic serialization.
    Uses Upstash Redis for serverless-friendly caching.
    """
    
    def __init__(self, redis_client: Optional[Redis] = None, key_prefix: str = "cache:"):
        """
        Initialize the cache manager.
        
        Args:
            redis_client: Optional Redis client instance. If not provided, a new one will be created.
            key_prefix: Prefix for all cache keys
        """
        self.redis = redis_client if redis_client is not None else get_redis_client()
        self.key_prefix = key_prefix
    
    def _get_key(self, key: str) -> str:
        """Get the full cache key with prefix."""
        return f"{self.key_prefix}{key}"
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from cache (synchronous).
        
        Args:
            key: Cache key
            default: Default value if key doesn't exist
            
        Returns:
            The cached value or default if not found
        """
        if not self.redis:
            return default
            
        try:
            full_key = self._get_key(key)
            value = self.redis.get(full_key)
            
            if value is None:
                return default
                
            # Try to deserialize JSON
            try:
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                return json.loads(value)
            except (json.JSONDecodeError, AttributeError):
                return value
                
        except Exception as e:
            logger.error(f"Cache get failed for key {key}: {str(e)}")
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a value in cache (synchronous).
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time to live in seconds (None for no expiration)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False
            
        try:
            full_key = self._get_key(key)
            
            # Serialize to JSON
            try:
                serialized = json.dumps(value)
            except (TypeError, OverflowError) as e:
                logger.error(f"Failed to serialize value for key {key}: {str(e)}")
                return False
            
            if ttl is not None:
                self.redis.setex(full_key, ttl, serialized)
            else:
                self.redis.set(full_key, serialized)
            
            return True
                
        except Exception as e:
            logger.error(f"Cache set failed for key {key}: {str(e)}")
            return False
    
    def delete(self, *keys: str) -> int:
        """
        Delete one or more keys from cache (synchronous).
        
        Args:
            *keys: Keys to delete (without prefix)
            
        Returns:
            Number of keys deleted
        """
        if not self.redis:
            return 0
            
        try:
            full_keys = [self._get_key(key) for key in keys]
            if not full_keys:
                return 0
                
            # Delete keys one by one
            deleted = 0
            for key in full_keys:
                try:
                    self.redis.delete(key)
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {str(e)}")
            return deleted
            
        except Exception as e:
            logger.error(f"Cache delete failed for keys {keys}: {str(e)}")
            return 0
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.redis:
            return False
            
        try:
            full_key = self._get_key(key)
            return bool(self.redis.exists(full_key))
        except Exception as e:
            logger.error(f"Cache exists check failed for key {key}: {str(e)}")
            return False



def cached(key_func=None, ttl=300):
    """
    Simple decorator to cache function results.
    Works with both sync and async functions.
    
    Args:
        key_func: Function to generate cache key from arguments.
                 If None, uses function name and str(args).
        ttl: Time to live in seconds.
    
    Example:
        @cached(key_func=lambda user_id: f"user:{user_id}", ttl=3600)
        async def get_user(user_id: str):
            # ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            # Check if cache is available
            if not hasattr(self, 'cache') or self.cache is None:
                return await func(self, *args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_value
            
            # Call the function
            result = await func(self, *args, **kwargs)
            
            # Cache the result
            if result is not None:
                self.cache.set(cache_key, result, ttl=ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            # Check if cache is available
            if not hasattr(self, 'cache') or self.cache is None:
                return func(self, *args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_value
            
            # Call the function
            result = func(self, *args, **kwargs)
            
            # Cache the result
            if result is not None:
                self.cache.set(cache_key, result, ttl=ttl)
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator



def invalidate_cache(key_pattern: str):
    """
    Decorator to invalidate cache entries after function execution.
    
    Args:
        key_pattern: Pattern to match cache keys for invalidation.
                    Can include placeholders like {arg_name}.
    
    Example:
        @invalidate_cache("user:{user_id}")
        async def update_user(self, user_id: str, data: dict):
            # ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            # Call the function first
            result = await func(self, *args, **kwargs)
            
            # Invalidate cache if available
            if hasattr(self, 'cache') and self.cache is not None:
                try:
                    # Try to format the key pattern with kwargs
                    cache_key = key_pattern.format(**kwargs)
                    self.cache.delete(cache_key)
                    logger.debug(f"Invalidated cache key: {cache_key}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not format cache key pattern '{key_pattern}': {str(e)}")
            
            return result
        
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            # Call the function first
            result = func(self, *args, **kwargs)
            
            # Invalidate cache if available
            if hasattr(self, 'cache') and self.cache is not None:
                try:
                    # Try to format the key pattern with kwargs
                    cache_key = key_pattern.format(**kwargs)
                    self.cache.delete(cache_key)
                    logger.debug(f"Invalidated cache key: {cache_key}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not format cache key pattern '{key_pattern}': {str(e)}")
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
