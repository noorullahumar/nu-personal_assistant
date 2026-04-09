"""
Rate limiting core functionality
Location: backend/core/rate_limiter.py

Provides rate limiting for API endpoints with:
- In-memory rate limiting (single instance)
- Admin-specific rate limiting with lockout
- Redis-based rate limiting for distributed deployments
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
from fastapi import Request, HTTPException, status


class RateLimiter:
    """
    In-memory rate limiter for API endpoints.
    Suitable for single-instance deployments.
    
    Usage:
        limiter = RateLimiter(limit=5, window_seconds=60)
        if limiter.check("client_ip"):
            # Allow request
        else:
            # Rate limit exceeded
    """
    
    def __init__(self, limit: int = 5, window_seconds: int = 60):
        """
        Initialize rate limiter
        
        Args:
            limit: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
        """
        self.default_limit = limit
        self.default_window = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, limit: Optional[int] = None, window_seconds: Optional[int] = None) -> bool:
        """
        Check if request is allowed for given key
        
        Args:
            key: Unique identifier (client IP, user ID, endpoint name, etc.)
            limit: Maximum requests allowed (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Returns:
            True if allowed, False if rate limit exceeded
        """
        now = time.time()
        limit = limit or self.default_limit
        window = window_seconds or self.default_window
        
        with self._lock:
            # Get request history for this key
            history = self.requests[key]
            
            # Remove old requests outside the window
            while history and history[0] < now - window:
                history.pop(0)
            
            # Check if limit exceeded
            if len(history) >= limit:
                return False
            
            # Add current request
            history.append(now)
            return True
    
    def get_remaining(self, key: str, limit: Optional[int] = None, window_seconds: Optional[int] = None) -> int:
        """
        Get remaining requests allowed for key
        
        Args:
            key: Unique identifier
            limit: Maximum requests allowed (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Returns:
            Number of remaining requests allowed
        """
        now = time.time()
        limit = limit or self.default_limit
        window = window_seconds or self.default_window
        
        with self._lock:
            history = self.requests[key]
            while history and history[0] < now - window:
                history.pop(0)
            
            return max(0, limit - len(history))
    
    def reset(self, key: str) -> None:
        """
        Reset rate limit for key
        
        Args:
            key: Unique identifier to reset
        """
        with self._lock:
            if key in self.requests:
                del self.requests[key]
    
    async def __call__(self, request: Request, limit: Optional[int] = None, window_seconds: Optional[int] = None):
        """
        FastAPI middleware compatible method
        
        Args:
            request: FastAPI request object
            limit: Maximum requests allowed (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        client_id = request.client.host if request.client else "unknown"
        
        if not self.check(client_id, limit, window_seconds):
            window = window_seconds or self.default_window
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(window)}
            )
        return True


class AdminRateLimiter:
    """
    Specialized rate limiter for admin authentication with account lockout.
    Tracks failed login attempts and implements lockout periods.
    
    Usage:
        limiter = AdminRateLimiter(max_attempts=5, lockout_minutes=15)
        if limiter.can_attempt(f"{email}_{ip}"):
            # Process login attempt
        else:
            # Too many attempts, account locked
    """
    
    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15):
        """
        Initialize admin rate limiter
        
        Args:
            max_attempts: Maximum failed attempts before lockout
            lockout_minutes: Minutes to lock account after max attempts
        """
        self.max_attempts = max_attempts
        self.lockout_minutes = lockout_minutes
        self.failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def can_attempt(self, key: str) -> bool:
        """
        Check if another login attempt is allowed for this key
        
        Args:
            key: Unique identifier (usually email + IP combination)
            
        Returns:
            True if attempt allowed, False if account is locked
        """
        now = datetime.utcnow()
        
        with self._lock:
            attempts = self.failed_attempts.get(key, [])
            
            # Clean old attempts outside lockout window
            self.failed_attempts[key] = [
                t for t in attempts 
                if t > now - timedelta(minutes=self.lockout_minutes)
            ]
            
            return len(self.failed_attempts[key]) < self.max_attempts
    
    def record_failed_attempt(self, key: str) -> None:
        """
        Record a failed login attempt
        
        Args:
            key: Unique identifier for the failed attempt
        """
        with self._lock:
            self.failed_attempts[key].append(datetime.utcnow())
    
    def reset_attempts(self, key: str) -> None:
        """
        Reset failed attempts for a key (called on successful login)
        
        Args:
            key: Unique identifier to reset
        """
        with self._lock:
            if key in self.failed_attempts:
                del self.failed_attempts[key]
    
    def get_remaining_attempts(self, key: str) -> int:
        """
        Get remaining attempts before lockout
        
        Args:
            key: Unique identifier
            
        Returns:
            Number of remaining attempts allowed
        """
        now = datetime.utcnow()
        
        with self._lock:
            attempts = self.failed_attempts.get(key, [])
            
            # Clean old attempts
            valid_attempts = [
                t for t in attempts 
                if t > now - timedelta(minutes=self.lockout_minutes)
            ]
            
            return max(0, self.max_attempts - len(valid_attempts))
    
    def get_lockout_remaining_seconds(self, key: str) -> int:
        """
        Get remaining lockout time in seconds
        
        Args:
            key: Unique identifier
            
        Returns:
            Seconds remaining in lockout, or 0 if not locked
        """
        now = datetime.utcnow()
        
        with self._lock:
            attempts = self.failed_attempts.get(key, [])
            
            if len(attempts) < self.max_attempts:
                return 0
            
            oldest_attempt = min(attempts)
            lockout_until = oldest_attempt + timedelta(minutes=self.lockout_minutes)
            
            if now >= lockout_until:
                return 0
            
            return int((lockout_until - now).total_seconds())


class RedisRateLimiter:
    """
    Redis-based rate limiter for distributed deployments.
    Requires redis-py package.
    
    Usage:
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        limiter = RedisRateLimiter(redis_client, limit=100, window_seconds=60)
        
        if limiter.check("client_ip"):
            # Allow request
        else:
            # Rate limit exceeded
    """
    
    def __init__(self, redis_client, limit: int = 5, window_seconds: int = 60):
        """
        Initialize Redis rate limiter
        
        Args:
            redis_client: Redis client instance
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        self.redis = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
    
    def check(self, client_id: str, limit: Optional[int] = None, window_seconds: Optional[int] = None) -> bool:
        """
        Check rate limit using Redis with sliding window
        
        Args:
            client_id: Unique identifier for client
            limit: Maximum requests allowed (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Returns:
            True if allowed, False if rate limit exceeded
        """
        key = f"rate_limit:{client_id}"
        now = time.time()
        limit = limit or self.limit
        window = window_seconds or self.window_seconds
        window_start = now - window
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request
        pipe.zadd(key, {str(now): now})
        # Set expiry
        pipe.expire(key, window)
        # Get count
        pipe.zcard(key)
        
        results = pipe.execute()
        count = results[-1]
        
        return count <= limit
    
    def get_remaining(self, client_id: str, limit: Optional[int] = None, window_seconds: Optional[int] = None) -> int:
        """
        Get remaining requests allowed for client
        
        Args:
            client_id: Unique identifier for client
            limit: Maximum requests allowed (uses default if None)
            window_seconds: Time window in seconds (uses default if None)
            
        Returns:
            Number of remaining requests allowed
        """
        key = f"rate_limit:{client_id}"
        now = time.time()
        limit = limit or self.limit
        window = window_seconds or self.window_seconds
        window_start = now - window
        
        # Clean old entries and get count
        self.redis.zremrangebyscore(key, 0, window_start)
        count = self.redis.zcard(key)
        
        return max(0, limit - count)
    
    def reset(self, client_id: str) -> None:
        """
        Reset rate limit for client
        
        Args:
            client_id: Unique identifier for client
        """
        key = f"rate_limit:{client_id}"
        self.redis.delete(key)


# ========== GLOBAL INSTANCES ==========
# Create global instances for use across the application

# Default rate limiter for general endpoints
default_rate_limiter = RateLimiter(limit=30, window_seconds=60)

# Strict rate limiter for authentication endpoints
auth_rate_limiter = RateLimiter(limit=5, window_seconds=60)

# Admin rate limiter for login attempts
admin_rate_limiter = AdminRateLimiter(max_attempts=5, lockout_minutes=15)