"""
Rate limiter configuration for Nyaya Legal Assistant.
Supports SlowAPI with an autonomous in-memory sliding-window fallback
to guarantee 100% operational reliability in any container or standalone environment.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Dict, List, Callable
from fastapi import Request, HTTPException, status

try:
    from slowapi import Limiter as SlowapiLimiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler

    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False
    RateLimitExceeded = HTTPException
    _rate_limit_exceeded_handler = None


class FallbackLimiter:
    """In-memory sliding window rate limiter fallback."""

    def __init__(self, default_limit: int = 120, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.request_history: Dict[str, List[float]] = defaultdict(list)

    def limit(self, limit_str: str):
        """
        Decorator enforcing rate limit (e.g. '20/minute').
        """
        parts = limit_str.split("/")
        max_requests = int(parts[0])
        window = 60 if len(parts) > 1 and "min" in parts[1] else 1

        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract client IP from kwargs request object
                request: Request = kwargs.get("request")
                client_ip = "127.0.0.1"
                if request and request.client:
                    client_ip = request.client.host
                elif request and "x-forwarded-for" in request.headers:
                    client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()

                now = time.time()
                history = self.request_history[client_ip]
                # Filter out timestamps older than window
                history = [t for t in history if now - t < window]
                self.request_history[client_ip] = history

                if len(history) >= max_requests:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded: {limit_str}. Please retry shortly.",
                    )

                history.append(now)
                return await func(*args, **kwargs)

            return wrapper

        return decorator


if HAS_SLOWAPI:
    limiter = SlowapiLimiter(
        key_func=get_remote_address, default_limits=["120/minute"], headers_enabled=True
    )
else:
    limiter = FallbackLimiter(default_limit=120, window_seconds=60)
