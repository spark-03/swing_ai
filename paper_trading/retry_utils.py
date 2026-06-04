import time
from typing import Callable, TypeVar

T = TypeVar("T")

def retry_call(
    operation: Callable[[], T],
    attempts: int = 3,
    initial_delay: float = 0.5,
    backoff: float = 2.0
) -> T:
    """Executes a function block with bounded exponential recovery delays."""
    delay = initial_delay
    last_error = None
    
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(delay)
            delay *= backoff
            
    if last_error:
        raise last_error
    raise RuntimeError("Retry operation tracking failed unexpectedly.")
