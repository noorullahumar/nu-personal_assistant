"""
Authentication dependencies for FastAPI routes
Location: backend/api/dependencies/auth_deps.py

This file contains dependency functions for:
- get_current_user: Regular user authentication
- get_current_admin: Admin user authentication
- get_current_user_optional: Optional authentication (returns None if not authenticated)
"""

from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from typing import Optional, Dict, Any
import logging

from backend.core.security import decode_token
from backend.database.mongodb import user_collection

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Get current authenticated user from token.
    
    This dependency validates the JWT token and returns user information.
    Used for endpoints that require authentication.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token credentials from Authorization header
        
    Returns:
        Dictionary with user_id, email, role, and token_id
        
    Raises:
        HTTPException: 401 if not authenticated or token invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Decode and validate token
    payload = decode_token(token, "access")
    
    if not payload:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Verify user still exists and is active
    user = await user_collection.find_one({"user_id": user_id, "is_active": True})
    if not user:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "token_id": payload.get("jti"),
        "username": user.get("username", email.split('@')[0])
    }


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current authenticated admin user.
    
    This dependency extends get_current_user and adds admin role validation.
    Used for admin-only endpoints.
    
    Args:
        current_user: User info from get_current_user dependency
        
    Returns:
        Current user dictionary if admin
        
    Raises:
        HTTPException: 403 if user is not an admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[Dict[str, Any]]:
    """
    Get current user if authenticated, return None otherwise.
    
    This is useful for endpoints that work for both authenticated and unauthenticated users.
    
    Args:
        request: FastAPI request object
        credentials: Bearer token credentials (optional)
        
    Returns:
        User information dictionary or None if not authenticated
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


async def get_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[Dict[str, Any]]:
    """
    Get decoded token payload without user verification.
    
    This is useful for debugging or for endpoints that only need token validation.
    
    Args:
        credentials: Bearer token credentials
        
    Returns:
        Decoded token payload or None if invalid
    """
    if not credentials:
        return None
    
    return decode_token(credentials.credentials, "access")