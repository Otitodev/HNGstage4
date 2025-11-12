from functools import wraps
import random
import time
from typing import Callable, TypeVar, Any, Optional, Type, List, Union
from requests.exceptions import RequestException
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)

class MaxRetriesExceededError(Exception):
    """Raised when maximum number of retries is exceeded."""
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        self.last_exception = last_exception
        super().__init__(message)

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 5.0,
    factor: float = 2.0,
    jitter: bool = True,
    exceptions: Union[Type[Exception], tuple[Type[Exception], ...]] = RequestException,
):
    """
    Retry decorator with exponential backoff and jitter.
    
    Args:
        max_retries: Maximum number of retries before giving up
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        factor: Multiplier for the delay between retries
        jitter: If True, adds random jitter to the delay
        exceptions: Exception(s) to catch and retry on
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                        
                    # Calculate next delay with exponential backoff
                    delay = min(delay * (factor ** attempt), max_delay)
                    
                    # Add jitter (up to 25% of the delay)
                    if jitter:
                        delay = random.uniform(0.75 * delay, 1.25 * delay)
                    
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {str(e)}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    time.sleep(delay)
            
            # If we get here, all retries failed
            error_msg = (
                f"Failed after {max_retries} retries. "
                f"Last error: {str(last_exception)}"
            )
            logger.error(error_msg)
            raise MaxRetriesExceededError(error_msg, last_exception)
        return wrapper
    return decorator
