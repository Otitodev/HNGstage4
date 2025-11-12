import json
import hashlib
import time
from typing import Any, Callable, Optional, TypeVar, Type, Union
from functools import wraps
import logging
from fastapi import HTTPException, status
from redis import Redis, RedisError

T = TypeVar('T')
logger = logging.getLogger(__name__)

class IdempotencyError(Exception):
    """Raised when an idempotency check fails."""
    pass

class IdempotencyKeyMissing(IdempotencyError):
    """Raised when idempotency key is missing."""
    pass

def generate_request_id(*args: Any, **kwargs: Any) -> str:
    """Generate a unique request ID from the given arguments."""
    # Combine args and kwargs for hashing, excluding certain keys
    excluded_keys = {'redis', 'request', 'x_idempotency_key', 'request_obj'}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k not in excluded_keys}
    combined = str((args, filtered_kwargs))
    return hashlib.sha256(combined.encode()).hexdigest()

class IdempotencyManager:
    """Manages idempotency using Redis as a backend."""
    
    def __init__(self, redis_client: Redis, key_prefix: str = "idempotency:", ttl: int = 86400):
        """
        Initialize the idempotency manager.
        
        Args:
            redis_client: Redis client instance
            key_prefix: Prefix for Redis keys
            ttl: Time-to-live in seconds for idempotency keys
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl = ttl
    
    def get_key(self, idempotency_key: str) -> str:
        """Get the full Redis key for an idempotency key."""
        return f"{self.key_prefix}{idempotency_key}"
    
    def store_response(self, idempotency_key: str, response: Any) -> None:
        """Store a successful response for an idempotency key."""
        try:
            if not idempotency_key:
                raise ValueError("Idempotency key cannot be empty")
                
            key = self.get_key(idempotency_key)
            self.redis.setex(
                name=key,
                time=self.ttl,
                value=json.dumps({
                    'status': 'completed',
                    'response': response,
                    'timestamp': time.time()
                })
            )
        except (RedisError, ValueError) as e:
            logger.error(f"Failed to store idempotency key {idempotency_key}: {str(e)}")
            # Don't fail the request if we can't store the idempotency key
            pass
    
    def check_duplicate(self, idempotency_key: str) -> Optional[Any]:
        """
        Check for a duplicate request.
        
        Returns:
            Cached response if this is a duplicate request, None otherwise
        """
        if not idempotency_key:
            return None
            
        try:
            key = self.get_key(idempotency_key)
            cached = self.redis.get(key)
            
            if cached:
                data = json.loads(cached)
                if data.get('status') == 'completed':
                    return data.get('response')
            
            return None
            
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error checking idempotency key {idempotency_key}: {str(e)}")
            # If there's an error checking for duplicates, we'll let the request proceed
            return None

def idempotent(
    key_param: Optional[str] = None,
    header: str = 'X-Idempotency-Key',
    ttl: int = 86400,
    ignore_errors: bool = True
):
    """
    Decorator to make a function idempotent using an idempotency key.
    
    Args:
        key_param: Name of the parameter containing the idempotency key.
                  If None, the key will be generated from all arguments.
        header: HTTP header containing the idempotency key (if key_param is None).
        ttl: Time-to-live in seconds for idempotency keys.
        ignore_errors: If True, errors with Redis will be logged but won't fail the request.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(
            *args: Any,
            redis: Redis,
            request: Optional[Any] = None,
            **kwargs: Any
        ) -> T:
            # Get the idempotency key
            idempotency_key = None
            
            # Try to get key from key_param if specified
            if key_param and key_param in kwargs:
                idempotency_key = str(kwargs[key_param])
            # Otherwise try to get from request headers
            elif request and hasattr(request, 'headers'):
                idempotency_key = request.headers.get(header)
            
            # If no key found and not generating one, raise an error
            if not idempotency_key and key_param is None:
                if ignore_errors:
                    logger.warning("No idempotency key provided")
                else:
                    raise IdempotencyKeyMissing(
                        f"Idempotency key is required (header: {header})"
                    )
            
            # Generate a key if needed
            if not idempotency_key:
                idempotency_key = generate_request_id(*args, **kwargs)
            
            # Check for duplicate request
            manager = IdempotencyManager(redis, ttl=ttl)
            cached_response = manager.check_duplicate(idempotency_key)
            
            if cached_response is not None:
                logger.info(f"Idempotent request detected with key: {idempotency_key}")
                return cached_response
            
            # Process the request
            try:
                result = await func(*args, **kwargs)
                
                # Store the successful response
                if result is not None:
                    manager.store_response(idempotency_key, result)
                
                return result
                
            except Exception as e:
                # Don't store failed responses to allow retries
                logger.error(f"Request failed: {str(e)}")
                raise
                
        return wrapper
    return decorator
