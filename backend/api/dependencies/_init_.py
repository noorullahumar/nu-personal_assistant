"""
Dependencies package for FastAPI routes
Location: backend/api/dependencies/__init__.py
"""

from backend.api.dependencies.auth_deps import (
    get_current_user,
    get_current_admin,
    get_current_user_optional,
    get_token_payload
)

from backend.api.dependencies.admin_auth import (
    AdminAuth,
    get_current_admin as get_admin_auth,
    admin_rate_limiter,
    log_admin_activity
)

from backend.api.dependencies.rate_limit_deps import RateLimitDeps

__all__ = [
    "get_current_user",
    "get_current_admin", 
    "get_current_user_optional",
    "get_token_payload",
    "AdminAuth",
    "get_admin_auth",
    "admin_rate_limiter",
    "log_admin_activity",
    "RateLimitDeps"
]