"""
Security middleware for HTTP headers and response hardening
Location: backend/core/middleware/security.py

This middleware adds security headers to all HTTP responses to protect against:
- XSS (Cross-Site Scripting)
- Clickjacking (X-Frame-Options)
- MIME type sniffing
- SSL stripping (HSTS)
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses for protection against common web vulnerabilities.
    
    Headers added:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-Frame-Options: DENY - Prevents clickjacking
    - X-XSS-Protection: 1; mode=block - Enables browser XSS filtering
    - Strict-Transport-Security: HSTS - Enforces HTTPS
    - Referrer-Policy: Controls referrer information
    - Content-Security-Policy: Restricts resources that can be loaded
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers to response"""
        response = await call_next(request)
        
        # ========== SECURITY HEADERS ==========
        # Prevent MIME type sniffing (IE security feature)
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        
        # Enable browser XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HTTP Strict Transport Security - Force HTTPS for 1 year
        # Include subdomains to secure all subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Control referrer information sent with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # Content Security Policy - Restrict resources
        # Adjust based on your frontend requirements
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Remove Server header to hide version information
        if "Server" in response.headers:
            del response.headers["Server"]
        
        # Remove Python version header if present
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        
        return response


class RateLimitExceededHandler:
    """
    Custom handler for rate limit exceeded responses.
    Returns a standardized 429 response with retry information.
    """
    
    async def __call__(self, request: Request, exc: Exception):
        """Handle rate limit exceeded exception"""
        from starlette.responses import JSONResponse
        
        return JSONResponse(
            status_code=429,
            content={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
                "retry_after": 60,  # seconds to wait
                "timestamp": __import__('datetime').datetime.utcnow().isoformat()
            },
            headers={"Retry-After": "60"}
        )