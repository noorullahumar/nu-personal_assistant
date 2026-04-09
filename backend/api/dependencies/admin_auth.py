"""
Admin authentication class and utilities
Location: backend/api/dependencies/admin_auth.py
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.database.mongodb import (
    user_collection, 
    admin_session_collection, 
    admin_2fa_collection,
    activity_log_collection
)
from backend.core.security import verify_password, create_access_token, decode_token

# ========== CONFIGURATION ==========
ADMIN_SESSION_EXPIRE_HOURS = int(os.getenv("ADMIN_SESSION_EXPIRE_HOURS", "8"))


# ========== RATE LIMITER FOR ADMIN ==========
class AdminRateLimiter:
    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.max_attempts = max_attempts
        self.lockout_minutes = lockout_minutes
        self.failed_attempts = defaultdict(list)
    
    def can_attempt(self, key: str) -> bool:
        now = datetime.utcnow()
        attempts = self.failed_attempts.get(key, [])
        
        self.failed_attempts[key] = [
            t for t in attempts 
            if t > now - timedelta(minutes=self.lockout_minutes)
        ]
        
        return len(self.failed_attempts[key]) < self.max_attempts
    
    def record_failed_attempt(self, key: str):
        self.failed_attempts[key].append(datetime.utcnow())


admin_rate_limiter = AdminRateLimiter()


async def log_admin_activity(user_id: str, action: str, details: Dict[str, Any]):
    """Log admin activity"""
    try:
        user = await user_collection.find_one({"user_id": user_id}) if user_id != "unknown" else None
        username = user.get("username", "Unknown") if user else "Unknown"
        
        await activity_log_collection.insert_one({
            "log_id": str(uuid.uuid4()),
            "user_id": user_id,
            "username": username,
            "action": f"ADMIN_{action}",
            "details": details,
            "timestamp": datetime.utcnow(),
            "ip_address": details.get("ip"),
        })
        print(f"📝 Admin audit: {action}")
    except Exception as e:
        print(f"Failed to log: {e}")


# ========== ADMIN AUTH CLASS ==========
class AdminAuth:
    @staticmethod
    async def login_admin(email: str, password: str, ip_address: str, user_agent: str):
        """Admin login with security checks"""
        
        # Rate limiting
        key = f"{email}_{ip_address}"
        if not admin_rate_limiter.can_attempt(key):
            raise HTTPException(429, "Too many attempts. Try again later.")
        
        # Find admin user
        user = await user_collection.find_one({
            "email": email,
            "role": "admin",
            "is_active": True
        })
        
        if not user:
            admin_rate_limiter.record_failed_attempt(key)
            raise HTTPException(401, "Invalid credentials")
        
        # Verify password
        if not verify_password(password, user["hashed_password"]):
            admin_rate_limiter.record_failed_attempt(key)
            await log_admin_activity(user["user_id"], "LOGIN_FAILED", {"ip": ip_address})
            raise HTTPException(401, "Invalid credentials")
        
        # Create session
        session_id = str(uuid.uuid4())
        
        # Create token
        token = create_access_token(
            data={
                "sub": user["user_id"],
                "email": user["email"],
                "role": "admin",
                "session_id": session_id,
                "type": "admin"
            },
            expires_delta=timedelta(hours=ADMIN_SESSION_EXPIRE_HOURS)
        )
        
        await log_admin_activity(user["user_id"], "LOGIN_SUCCESS", {"ip": ip_address})
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ADMIN_SESSION_EXPIRE_HOURS * 3600,
            "user": {
                "user_id": user["user_id"],
                "email": user["email"],
                "username": user["username"],
                "role": user["role"]
            }
        }
    
    @staticmethod
    async def verify_2fa(user_id: str, code: str, temp_token: str, ip_address: str, user_agent: str):
        """Verify 2FA (simplified - returns error if 2FA not set up)"""
        # For now, just return error since 2FA is optional
        raise HTTPException(400, "2FA not configured for this account")


# ========== ADMIN SECURITY DEPENDENCY ==========
class AdminSecurity:
    async def __call__(self, request: Request, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
        """Admin authentication dependency"""
        
        if not credentials:
            raise HTTPException(401, "Not authenticated")
        
        token = credentials.credentials
        
        # Decode token
        payload = decode_token(token, "access")
        
        if not payload or payload.get("type") != "admin":
            raise HTTPException(401, "Invalid admin token")
        
        user_id = payload.get("sub")
        
        # Get user
        user = await user_collection.find_one({"user_id": user_id, "role": "admin"})
        if not user:
            raise HTTPException(401, "Admin user not found")
        
        return {
            "user_id": user_id,
            "email": user["email"],
            "username": user["username"],
            "role": "admin"
        }


# Singleton instance
get_current_admin = AdminSecurity()