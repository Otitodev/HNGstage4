import json
import logging
import inspect
import os
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union, Type, cast
from datetime import timedelta
import pickle
from upstash_redis import Redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_redis_client() -> Redis:
    """Get a Redis client instance."""
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    
    if not redis_url or not redis_token:
        raise ValueError("Redis configuration is missing in environment variables")
    
    return Redis(url=redis_url, token=redis_token)

T = TypeVar('T')
logger = logging.getLogger(__name__)

class CacheManager:
    """
    A Redis-based caching utility with TTL and automatic serialization.
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
    
    async def get(self, key: str, default: Any = None, ttl: Optional[int] = None) -> Any:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
            default: Default value if key doesn't exist
            ttl: Optional TTL in seconds (if you want to refresh the TTL on get)
            
        Returns:
            The cached value or default if not found
        """
        try:
            full_key = self._get_key(key)
            value = await self.redis.get(full_key)
            
            if value is None:
                return default
                
            # Refresh TTL if specified
            if ttl is not None:
                self.redis.expire(full_key, ttl)
                
            # Try to deserialize JSON first, fall back to pickle
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return pickle.loads(value)
                
        except (Exception, pickle.PickleError) as e:
            logger.error(f"Cache get failed for key {key}: {str(e)}")
            return default
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable or picklable)
            ttl: Time to live in seconds (None for no expiration)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            full_key = self._get_key(key)
            
            # Try JSON serialization first, fall back to pickle
            try:
                serialized = json.dumps(value)
            except (TypeError, OverflowError):
                serialized = pickle.dumps(value)
            
            if ttl is not None:
                return await self.redis.setex(full_key, ttl, serialized)
            else:
                return await self.redis.set(full_key, serialized)
                
        except (Exception, pickle.PicklingError) as e:
            logger.error(f"Cache set failed for key {key}: {str(e)}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys from cache.
        
        Args:
            *keys: Keys to delete (without prefix)
            
        Returns:
            Number of keys deleted
        """
        try:
            full_keys = [self._get_key(key) for key in keys]
            if not full_keys:
                return 0
                
            # Delete keys one by one since Upstash Redis doesn't support multiple deletes in one call
            deleted = 0
            for key in full_keys:
                try:
                    await self.redis.delete(key)
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {str(e)}")
            return deleted
            
        except Exception as e:
            logger.error(f"Cache delete failed for keys {keys}: {str(e)}")
            return 0
    
    async def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., 'user:123:*')
            
        Returns:
            Number of keys deleted
        """
        try:
            full_pattern = self._get_key(pattern)
            # Get all keys matching the pattern
            keys = await self.redis.keys(full_pattern)
            if not keys:
                return 0
                
            # Delete keys one by one
            deleted = 0
            for key in keys:
                try:
                    await self.redis.delete(key)
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {str(e)}")
            return deleted
            
        except Exception as e:
            logger.error(f"Cache invalidation failed for pattern {pattern}: {str(e)}")
            return 0
    
    async def clear_all(self) -> bool:
        """Clear all keys with the configured prefix."""
        try:
            # Get all keys with the prefix
            keys = await self.redis.keys(f"{self.key_prefix}*")
            if not keys:
                return True
                
            # Delete keys one by one
            for key in keys:
                try:
                    await self.redis.delete(key)
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {str(e)}")
                    return False
            return True
            
        except Exception as e:
            logger.error(f"Cache clear failed: {str(e)}")
            return False

def cached(
    key_func: Optional[Callable[..., str]] = None,
    ttl: Union[int, Callable[..., int]] = 300,
    cache_none: bool = False
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to cache function results.
    
    Args:
        key_func: Function to generate cache key from function arguments.
                 If None, uses function name and all arguments.
        ttl: Time to live in seconds, or a function that returns TTL.
        cache_none: Whether to cache None return values.
    
    Example:
        @cached(
            key_func=lambda user_id: f"user:{user_id}:prefs",
            ttl=3600
        )
        async def get_user_preferences(user_id: str) -> Dict:
            # ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(self, *args: Any, **kwargs: Any) -> T:
                # Skip caching if Redis is not available
                if not hasattr(self, 'cache') or not isinstance(self.cache, CacheManager):
                    return await func(self, *args, **kwargs)
                    
                # Generate cache key
                if key_func is not None:
                    key = key_func(*args, **kwargs)
                else:
                    key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
                
                # Try to get from cache
                try:
                    cached_value = await self.cache.get(key)
                    if cached_value is not None:
                        return cast(T, cached_value)
                except Exception as e:
                    logger.warning(f"Cache get failed: {str(e)}")
                
                # Get the TTL value (can be a callable or a static value)
                ttl_value = ttl(*args, **kwargs) if callable(ttl) else ttl
                
                # Call the async function
                result = await func(self, *args, **kwargs)
                
                # Cache the result if needed
                if result is not None or cache_none:
                    try:
                        await self.cache.set(key, result, ttl=ttl_value)
                    except Exception as e:
                        logger.warning(f"Failed to cache result for key {key}: {str(e)}")
                
                return result
                
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(self, *args: Any, **kwargs: Any) -> T:
                # Skip caching if Redis is not available
                if not hasattr(self, 'cache') or not isinstance(self.cache, CacheManager):
                    return func(self, *args, **kwargs)
                    
                # Generate cache key
                if key_func is not None:
                    key = key_func(*args, **kwargs)
                else:
                    key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
                
                # Call the sync function
                result = func(self, *args, **kwargs)
                
                # Cache the result if needed
                if result is not None or cache_none:
                    ttl_value = ttl(*args, **kwargs) if callable(ttl) else ttl
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        loop.run_until_complete(self.cache.set(key, result, ttl=ttl_value))
                    except Exception as e:
                        logger.warning(f"Failed to cache result for key {key}: {str(e)}")
                
                return result
                
            return sync_wrapper
    return decorator

def invalidate_cache(key_pattern: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to invalidate cache entries after function execution.
    
    Args:
        key_pattern: Pattern to match cache keys for invalidation.
                    Can include placeholders like {arg_name} that will be
                    replaced with actual argument values.
    
    Example:
        @invalidate_cache("user:{user_id}:prefs")
        async def update_user_preferences(user_id: str, prefs: Dict) -> bool:
            # ...
            
        class MyClass:
            @invalidate_cache("user:{user_id}:prefs")
            async def update_prefs(self, user_id: str, prefs: Dict) -> bool:
                # ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                # Call the original async function
                result = await func(*args, **kwargs)
                await _invalidate_cache_async(func, key_pattern, *args, **kwargs)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                # Call the original sync function
                result = func(*args, **kwargs)
                _invalidate_cache_sync(func, key_pattern, *args, **kwargs)
                return result
            return sync_wrapper
    return decorator


def _get_cache_manager(func: Callable[..., Any], args: tuple[Any, ...]) -> Optional[CacheManager]:
    """Helper to get the cache manager from either instance or function."""
    # Check if this is a method call (has 'self')
    if args and hasattr(args[0], 'cache') and isinstance(getattr(args[0], 'cache'), CacheManager):
        # Method call - get cache from self
        return args[0].cache
    elif hasattr(func, 'cache') and isinstance(getattr(func, 'cache'), CacheManager):
        # Function with cache attached
        return func.cache
    return None


def _get_bound_arguments(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Optional[inspect.BoundArguments]:
    """Helper to bind function arguments to parameters."""
    try:
        sig = inspect.signature(func)
        # For methods, skip the 'self' parameter
        if args and hasattr(args[0], '__class__') and func.__name__ in dir(args[0].__class__):
            bound_args = sig.bind(*args[1:], **kwargs)
        else:
            bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        return bound_args
    except Exception as e:
        logger.warning(f"Could not bind arguments for {func.__name__}: {str(e)}")
        return None


async def _invalidate_cache_async(func: Callable[..., Any], key_pattern: str, *args: Any, **kwargs: Any) -> None:
    """Async cache invalidation logic."""
    cache = _get_cache_manager(func, args)
    if not cache:
        return

    try:
        bound_args = _get_bound_arguments(func, args, kwargs)
        if not bound_args:
            return
            
        # Format the key pattern with the bound arguments
        formatted_pattern = key_pattern.format(**bound_args.arguments)
        
        # Invalidate matching keys
        cache.invalidate_by_pattern(formatted_pattern)
        
    except (TypeError, KeyError) as e:
        logger.warning(f"Could not format cache key pattern '{key_pattern}': {str(e)}")
    except Exception as e:
        logger.error(f"Cache invalidation failed: {str(e)}")


def _invalidate_cache_sync(func: Callable[..., Any], key_pattern: str, *args: Any, **kwargs: Any) -> None:
    """Sync cache invalidation logic."""
    cache = _get_cache_manager(func, args)
    if not cache:
        return

    try:
        bound_args = _get_bound_arguments(func, args, kwargs)
        if not bound_args:
            return
            
        # Format the key pattern with the bound arguments
        formatted_pattern = key_pattern.format(**bound_args.arguments)
        
        # Invalidate matching keys
        cache.invalidate_by_pattern(formatted_pattern)
        
    except (TypeError, KeyError) as e:
        logger.warning(f"Could not format cache key pattern '{key_pattern}': {str(e)}")
    except Exception as e:
        logger.error(f"Cache invalidation failed: {str(e)}")
    return decorator
