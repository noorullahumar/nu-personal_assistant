"""
Authentication routes - Merged with conversation support
Location: backend/api/routes/auth.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from datetime import datetime, timedelta
import uuid
import logging
import secrets

from backend.config import settings
from backend.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, validate_password_strength, sanitize_input,
    generate_reset_token, verify_reset_token, generate_password_reset_token, verify_password_reset_token,get_password_hash# At the top of auth.py, add the import
)
from backend.database.repositories.user_repo import UserRepository
from backend.utils.email import send_password_reset_email, send_password_changed_email
from backend.api.dependencies.auth_deps import get_current_user
from backend.models.schemas import (
    UserCreate, UserLogin, TokenResponse, UserResponse,
    ChangePasswordRequest, ForgotPasswordRequest,
    ResetPasswordRequest, PasswordResetResponse, RefreshTokenRequest
)
from backend.core.rate_limiter import RateLimiter
# Direct database imports (for conversation routes - will be migrated later)
from backend.database.mongodb import (
    user_collection, conversation_collection, 
    activity_log_collection
)

from backend.core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ========== INITIALIZE LIMITERS ==========
rate_limiter_instance = RateLimiter(limit=5, window_seconds=60)
register_limiter = RateLimiter(limit=3, window_seconds=60)

# ========== AUTHENTICATION ROUTES ==========


@router.post("/register")
async def register(request: Request, user_data: UserCreate):
    client_ip = request.client.host
    if not register_limiter.check(client_ip):
        raise HTTPException(429, "Too many registration attempts")
    try:
        logger.info(f"Registration attempt for email: {user_data.email}")
        
        # Validate password strength
        if len(user_data.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
        if not any(c.isupper() for c in user_data.password):
            raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
        
        if not any(c.isdigit() for c in user_data.password):
            raise HTTPException(status_code=400, detail="Password must contain at least one number")
        
        # Check if database is initialized
        if user_collection is None:
            logger.error("Database not initialized - user_collection is None")
            raise HTTPException(status_code=500, detail="Database not initialized")
        
        # Check for existing user
        existing = await user_collection.find_one({"email": user_data.email})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(user_data.password)
        
        # Handle role
        role = getattr(user_data, 'role', 'user')
        if hasattr(role, 'value'):
            role = role.value
        
        user = {
            "user_id": user_id,
            "username": user_data.username,
            "email": user_data.email,
            "hashed_password": hashed_password,
            "role": role,
            "created_at": datetime.utcnow(),
            "is_active": True,
            "is_verified": False,
            "failed_login_attempts": 0,
            "last_login_ip": client_ip
        }
        
        # Insert user
        try:
            result = await user_collection.insert_one(user)
            logger.info(f"User inserted with ID: {result.inserted_id}")
        except Exception as db_error:
            logger.error(f"Database insert error: {str(db_error)}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
        # Generate tokens
        access_token = create_access_token(
            data={
                "sub": user_id,
                "email": user_data.email,
                "role": role,
                "jti": str(uuid.uuid4())
            }
        )
        
        refresh_token = create_refresh_token(
            data={
                "sub": user_id,
                "email": user_data.email,
                "role": role,
                "jti": str(uuid.uuid4())
            }
        )
        
        # Log activity
        if activity_log_collection is not None:
            await activity_log_collection.insert_one({
                "log_id": str(uuid.uuid4()),
                "user_id": user_id,
                "username": user_data.username,
                "action": "USER_REGISTERED",
                "details": {"ip_address": client_ip},
                "timestamp": datetime.utcnow()
            })
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                user_id=user_id,
                username=user_data.username,
                email=user_data.email,
                role=role,
                created_at=user["created_at"]
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, login_data: UserLogin):
    """Login with rate limiting and account lockout"""
    client_ip = request.client.host
    
    # Rate limiting
    if not rate_limiter_instance.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    
    try:
        logger.info(f"Login attempt for email: {login_data.email}")
        
        user = await user_collection.find_one({"email": login_data.email})
        
        if not user:
            # Add artificial delay to prevent user enumeration
            import asyncio
            await asyncio.sleep(1)
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Check account lockout
        if user.get("failed_login_attempts", 0) >= 5:
            last_attempt = user.get("last_failed_login")
            if last_attempt and (datetime.utcnow() - last_attempt).seconds < 900:  # 15 minutes
                raise HTTPException(status_code=401, detail="Account locked. Try again later.")
            else:
                # Reset attempts after lockout period
                await user_collection.update_one(
                    {"email": login_data.email},
                    {"$set": {"failed_login_attempts": 0}}
                )
        
        if not verify_password(login_data.password, user["hashed_password"]):
            # Increment failed attempts
            await user_collection.update_one(
                {"email": login_data.email},
                {
                    "$inc": {"failed_login_attempts": 1},
                    "$set": {"last_failed_login": datetime.utcnow()}
                }
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Reset failed attempts on successful login
        await user_collection.update_one(
            {"user_id": user["user_id"]},
            {
                "$set": {
                    "last_login": datetime.utcnow(),
                    "last_login_ip": client_ip,
                    "failed_login_attempts": 0
                }
            }
        )
        
        # Generate tokens
        access_token = create_access_token(
            data={
                "sub": user["user_id"],
                "email": user["email"],
                "role": user["role"],
                "jti": str(uuid.uuid4())
            }
        )
        
        refresh_token = create_refresh_token(
            data={
                "sub": user["user_id"],
                "email": user["email"],
                "role": user["role"],
                "jti": str(uuid.uuid4())
            }
        )
        
        logger.info(f"User logged in successfully: {user['email']}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                user_id=user["user_id"],
                username=user["username"],
                email=user["email"],
                role=user["role"],
                created_at=user["created_at"],
                last_login=user.get("last_login")
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh")
async def refresh_token(refresh_token_request: RefreshTokenRequest):
    """Refresh access token using refresh token"""
    payload = decode_token(refresh_token_request.refresh_token, "refresh")
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")
    
    # Verify user still exists and is active
    user = await user_collection.find_one({"user_id": user_id, "is_active": True})
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    new_access_token = create_access_token(
        data={
            "sub": user_id,
            "email": email,
            "role": role,
            "jti": str(uuid.uuid4())
        }
    )
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    user = await user_collection.find_one({"user_id": current_user["user_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        user_id=user["user_id"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        created_at=user["created_at"],
        last_login=user.get("last_login")
    )


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout - invalidate token"""
    return {"message": "Logged out successfully"}

@router.post("/change-password", response_model=PasswordResetResponse)
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        logger.info(f"Password change request for user: {current_user['email']}")
        
        # 1. FETCH USER
        user = await user_collection.find_one({"user_id": current_user["user_id"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 2. VERIFY CURRENT PASSWORD
        if not verify_password(password_data.current_password, user["hashed_password"]):
            logger.warning(f"Password change failed: incorrect current password for {current_user['email']}")
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # 3. HASH NEW PASSWORD
        new_hashed_password = hash_password(password_data.new_password)
        
        # 4. ATOMIC UPDATE: SET NEW PASSWORD & INCREMENT TOKEN VERSION
        # This ensures all old JWTs become invalid immediately
        await user_collection.update_one(
            {"user_id": current_user["user_id"]},
            {
                "$inc": {"token_version": 1},
                "$set": {
                    "hashed_password": new_hashed_password,
                    "password_changed_at": datetime.utcnow()
                }
            }
        )
        
        # 5. POST-UPDATE ACTIONS (Email & Logs)
        client_ip = request.client.host if request.client else "Unknown"
        
        try:
            await send_password_changed_email(
                email=user["email"],
                username=user["username"],
                ip_address=client_ip
            )
        except Exception as e:
            logger.warning(f"Failed to send password change email: {e}")
        
        if activity_log_collection is not None:
            await activity_log_collection.insert_one({
                "log_id": str(uuid.uuid4()),
                "user_id": current_user["user_id"],
                "username": user["username"],
                "action": "PASSWORD_CHANGED",
                "details": {
                    "ip_address": client_ip,
                    "forced_logout": True  # Metadata indicating tokens were rotated
                },
                "timestamp": datetime.utcnow()
            })
        
        logger.info(f"Password changed and tokens invalidated for: {current_user['email']}")
        
        return PasswordResetResponse(
            message="Password changed successfully. Please log in again.",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to change password")

@router.post("/forgot-password")
async def forgot_password(
    forgot_data: ForgotPasswordRequest,
    request: Request
):
    """
    Send password reset email to user
    """
    try:
        # Find user by email
        user = await user_collection.find_one({"email": forgot_data.email})
        
        if not user:
            # For security, don't reveal that user doesn't exist
            return {
                "success": True,
                "message": "If your email is registered, you will receive a password reset link"
            }
        
        # Generate reset token
        token = generate_password_reset_token(forgot_data.email)
        
        # Store token in database with expiration
        await user_collection.update_one(
            {"email": forgot_data.email},
            {
                "$set": {
                    "reset_token": token,
                    "reset_token_expires": datetime.utcnow() + timedelta(hours=1)
                }
            }
        )
        
        # Send email - FIXED PARAMETER NAMES
        email_sent = await send_password_reset_email(
            to_email=forgot_data.email,      # Changed from 'email' to 'to_email'
            user_name=user["username"],       # Changed from 'username' to 'user_name'
            reset_token=token                 # Changed from 'token' to 'reset_token'
        )
        
        if email_sent:
            logger.info(f"Password reset email sent to {forgot_data.email}")
        else:
            logger.warning(f"Failed to send password reset email to {forgot_data.email}")
        
        return {
            "success": True,
            "message": "If your email is registered, you will receive a password reset link"
        }
        
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process request")

@router.post("/reset-password")
async def reset_password(
    reset_data: ResetPasswordRequest
):
    """
    Reset password using token
    """
    try:
        # Verify token
        email = verify_password_reset_token(reset_data.token)
        
        if not email:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        
        # Find user
        user = await user_collection.find_one({"email": email})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if token matches and not expired
        if user.get("reset_token") != reset_data.token:
            raise HTTPException(status_code=400, detail="Invalid token")
            
        if user.get("reset_token_expires") < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Token expired")
        
        # Hash new password - Now using imported function
        hashed_password = get_password_hash(reset_data.new_password)
        
        # Update password and clear reset token
        await user_collection.update_one(
            {"email": email},
            {
                "$set": {"hashed_password": hashed_password},
                "$unset": {"reset_token": "", "reset_token_expires": ""}
            }
        )
        
        # Send confirmation email
        from backend.utils.email import send_password_changed_email
        
        email_sent = await send_password_changed_email(
            to_email=email,
            user_name=user.get("username", "User")
        )
        
        return {"success": True, "message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reset password")
@router.get("/verify-reset-token/{token}")
async def verify_reset_token_endpoint(token: str):
    try:
        user = await user_collection.find_one({"reset_token": token})
        if user:
            return {"valid": True, "email": user["email"]}
        return {"valid": False}
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return {"valid": False}

@router.post("/admin/create-first", response_model=UserResponse)
async def create_first_admin(
    admin_data: UserCreate,
    request: Request
):
    """
    Create the first admin user (only works if no admin exists)
    This is useful for initial setup after deployment
    """
    try:
        # Check if any admin exists
        existing_admin = await user_collection.find_one({"role": "admin"})
        
        if existing_admin:
            raise HTTPException(
                status_code=403, 
                detail="Admin already exists. Use regular admin creation process."
            )
        
        # Check if user exists
        existing_user = await user_collection.find_one({"email": admin_data.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create admin user
        user_id = secrets.token_urlsafe(16)
        hashed_password = get_password_hash(admin_data.password)
        
        admin_user = {
            "user_id": user_id,
            "username": admin_data.username,
            "email": admin_data.email,
            "hashed_password": hashed_password,
            "role": "admin",
            "created_at": datetime.utcnow(),
            "is_active": True,
            "is_verified": True,
            "failed_login_attempts": 0
        }
        
        await user_collection.insert_one(admin_user)
        
        # Create access token
        access_token = create_access_token(data={"sub": admin_data.email})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "user_id": user_id,
                "username": admin_data.username,
                "email": admin_data.email,
                "role": "admin"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create first admin error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create admin")