"""
Request/Response logging middleware for monitoring and debugging
Location: backend/core/middleware/logging.py

Provides structured logging for all HTTP requests including:
- Request ID tracking
- Response timing
- Error logging with stack traces
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import uuid
import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all requests with timing information and unique request IDs.
    
    Features:
    - Generates unique request ID for each request
    - Logs request start with method, path, client IP
    - Logs response completion with status code and duration
    - Adds X-Request-ID header to response for client-side tracking
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request with logging and timing"""
        
        # Generate unique request ID for tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Get client information
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For", client_ip)
        
        # Start timing the request
        start_time = time.time()
        
        # Log request start with structured data
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": client_ip,
                "forwarded_for": forwarded_for,
                "user_agent": request.headers.get("User-Agent", "unknown")
            }
        )
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate request duration
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)
            
            # Log successful response
            logger.info(
                f"Request completed: {request.method} {request.url.path} - Status: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "duration_seconds": round(duration, 3)
                }
            )
            
            # Add request ID to response headers for client-side correlation
            response.headers["X-Request-ID"] = request_id
            
            # Add response time header (optional)
            response.headers["X-Response-Time-Ms"] = str(duration_ms)
            
            return response
            
        except Exception as e:
            # Calculate duration even for failed requests
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)
            
            # Log error with full exception details
            logger.error(
                f"Request failed: {request.method} {request.url.path} - Error: {str(e)}",
                exc_info=True,  # Include full stack trace
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            # Re-raise the exception to be handled by FastAPI
            raise


class ResponseCompressionMiddleware(BaseHTTPMiddleware):
    """
    Add compression headers for better performance.
    
    Note: Actual compression is typically handled by:
    - Nginx reverse proxy (recommended for production)
    - Uvicorn with --gzip flag
    - CDN (CloudFlare, CloudFront)
    
    This middleware only adds the necessary headers.
    """
    
    async def dispatch(self, request: Request, call_next):
        """Add compression headers to response"""
        response = await call_next(request)
        
        # Check if client supports gzip compression
        accept_encoding = request.headers.get("Accept-Encoding", "")
        
        # Only compress successful responses
        if "gzip" in accept_encoding and 200 <= response.status_code < 300:
            # Add compression headers
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Vary"] = "Accept-Encoding"
            
            # Note: Actual compression should be handled by:
            # 1. Nginx: gzip on;
            # 2. Uvicorn: --gzip flag
            # 3. Or implement actual compression here with gzip library
        
        return response


class APIKeyValidationMiddleware(BaseHTTPMiddleware):
    """
    Optional API key validation for external service endpoints.
    
    This is separate from JWT authentication and is used for:
    - Third-party integrations
    - Internal service-to-service communication
    - Rate-limited public APIs
    
    Enable by setting API_KEYS_ENABLED=true in environment.
    """
    
    # Public endpoints that don't require API key
    PUBLIC_PATHS = [
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/metrics"  # Prometheus metrics endpoint
    ]
    
    async def dispatch(self, request: Request, call_next):
        """Validate API key for protected endpoints"""
        
        # Skip validation for public paths
        if any(request.url.path.startswith(path) for path in self.PUBLIC_PATHS):
            return await call_next(request)
        
        # Check if API key validation is enabled
        import os
        if os.getenv("API_KEYS_ENABLED", "false").lower() != "true":
            # Skip validation if not enabled
            return await call_next(request)
        
        # Get API key from header
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            # Missing API key
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={
                    "error": "API_KEY_REQUIRED",
                    "message": "X-API-Key header is required"
                }
            )
        
        # Validate API key (implement your validation logic)
        # Example: Check against database or environment variable
        valid_keys = os.getenv("VALID_API_KEYS", "").split(",")
        
        if api_key not in valid_keys:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={
                    "error": "INVALID_API_KEY",
                    "message": "Invalid or expired API key"
                }
            )
        
        # Add API key info to request state for downstream use
        request.state.api_key = api_key
        
        return await call_next(request)
    
# logging.py - Don't log sensitive data
def sanitize_log_data(data: dict) -> dict:
    sensitive_fields = ['password', 'token', 'authorization', 'api_key']
    for field in sensitive_fields:
        if field in data:
            data[field] = '[REDACTED]'
    return data