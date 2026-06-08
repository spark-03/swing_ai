from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Core exceptions tuple construction
DEFAULT_EXCEPTIONS: list[type[BaseException]] = [Exception]

try:
    # Capture explicit Supabase/PostgREST network errors if SDK is available
    from postgrest.exceptions import PostgrestAPIError
    DEFAULT_EXCEPTIONS.append(PostgrestAPIError)
except ImportError:
    pass

try:
    # Capture standard HTTP library network drop exception types
    from httpx import HTTPError
    DEFAULT_EXCEPTIONS.append(HTTPError)
except ImportError:
    pass


def retry_call(
    operation: Callable[[], T],
    attempts: int = 3,
    initial_delay: float = 0.5,
    backoff: float = 2.0,
    retry_exceptions: tuple[type[BaseException], ...] | None = None,
) -> T:
    """
    Executes a function block with bounded exponential recovery delays.
    
    Automatically handles network drops and database spiking hiccups when targeting 
    Supabase endpoints if a custom exception tuple isn't explicitly supplied.
    """
    # If no custom list is passed, use the robust cloud default tuple
    exceptions_to_catch = retry_exceptions if retry_exceptions is not None else tuple(DEFAULT_EXCEPTIONS)
    
    delay = initial_delay
    last_error = None
    
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except exceptions_to_catch as exc:
            last_error = exc
            if attempt == attempts:
                break
            
            time.sleep(delay)
            delay *= backoff
            
    if last_error:
        raise last_error
    raise RuntimeError("Retry operation tracking failed unexpectedly.")
