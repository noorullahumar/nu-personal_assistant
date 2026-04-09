"""
Rate limiting dependencies for FastAPI routes
Location: backend/api/dependencies/rate_limit_deps.py

Provides dependency injection for rate limiting across different endpoints.
"""

from fastapi import Request, HTTPException, status
from typing import Optional
import logging

from backend.core.rate_limiter import default_rate_limiter, auth_rate_limiter

logger = logging.getLogger(__name__)


class RateLimitDeps:
    """
    Rate limiting dependency for FastAPI routes.
    
    Usage:
        @router.post("/endpoint")
        async def endpoint(rate_limiter: RateLimitDeps = Depends(RateLimitDeps("endpoint_name", "30/minute"))):
            await rate_limiter.check(request)
            # ... endpoint logic
    """
    
    def __init__(self, endpoint_name: str, limit_str: str = "30/minute"):
        """
        Initialize rate limiter for an endpoint
        
        Args:
            endpoint_name: Unique name for this endpoint (used for rate limit key)
            limit_str: Rate limit string (e.g., "5/minute", "100/hour", "1000/day")
        """
        self.endpoint_name = endpoint_name
        
        # Parse limit string
        parts = limit_str.split('/')
        if len(parts) != 2:
            self.limit = 30
            self.window_seconds = 60
        else:
            self.limit = int(parts[0])
            window_str = parts[1].lower()
            
            if window_str == "minute":
                self.window_seconds = 60
            elif window_str == "hour":
                self.window_seconds = 3600
            elif window_str == "day":
                self.window_seconds = 86400
            else:
                self.window_seconds = 60
    
    async def check(self, request: Request, client_id: Optional[str] = None) -> bool:
        """
        Check if request is within rate limits
        
        Args:
            request: FastAPI request object
            client_id: Optional custom client ID (defaults to IP address)
            
        Returns:
            True if allowed
            
        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        if client_id is None:
            client_id = request.client.host if request.client else "unknown"
        
        key = f"{self.endpoint_name}:{client_id}"
        
        if not default_rate_limiter.check(key, self.limit, self.window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests to {self.endpoint_name}. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)}
            )
        return True
    
    async def check_token(self, token: str) -> bool:
        """
        Check rate limit by token (for token-based rate limiting)
        
        Args:
            token: Token to use as key
            
        Returns:
            True if allowed
            
        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        key = f"{self.endpoint_name}:token:{token[:32]}"
        
        if not default_rate_limiter.check(key, self.limit, self.window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)}
            )
        return True
    
    def get_remaining(self, request: Request) -> int:
        """
        Get remaining requests allowed for this client
        
        Args:
            request: FastAPI request object
            
        Returns:
            Number of remaining requests allowed
        """
        client_id = request.client.host if request.client else "unknown"
        key = f"{self.endpoint_name}:{client_id}"
        
        return default_rate_limiter.get_remaining(key, self.limit, self.window_seconds)


class AuthRateLimitDeps:
    """
    Specialized rate limiter for authentication endpoints (stricter limits)
    """
    
    async def check(self, request: Request) -> bool:
        """Check rate limit for auth endpoints"""
        client_id = request.client.host if request.client else "unknown"
        
        if not auth_rate_limiter.check(client_id, 5, 60):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please try again later.",
                headers={"Retry-After": "60"}
            )
        return True


# Create singleton instances for easy import
rate_limit_deps = RateLimitDeps
auth_rate_limit_deps = AuthRateLimitDeps