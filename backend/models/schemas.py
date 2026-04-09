from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re

# Enums
class UserRole(str, Enum):
    """User role types"""
    ADMIN = "admin"
    USER = "user"

class DocumentStatus(str, Enum):
    """Document processing status"""
    ACTIVE = "active"
    PROCESSING = "processing"
    FAILED = "failed"
    DELETED = "deleted"

# Request/Response Models
class UserCreate(BaseModel):
    """User registration request model with validation"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = "user"
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username format"""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores, and hyphens')
        return v

class UserLogin(BaseModel):
    """User login request model"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """User information response model"""
    user_id: str
    username: str
    email: EmailStr
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TokenResponse(BaseModel):
    """Authentication token response model"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes in seconds
    user: UserResponse

class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str

class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    """Chat response model"""
    reply: str
    conversation_id: str
    message_id: str
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None

class ConversationSummary(BaseModel):
    """Conversation summary model"""
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    preview: str

# Admin Models
class DocumentInfo(BaseModel):
    """Document information model"""
    document_id: str
    filename: str
    file_type: str
    size: int
    upload_date: datetime
    status: DocumentStatus
    chunk_count: int
    uploaded_by: str

class DocumentUploadResponse(BaseModel):
    """Document upload response model"""
    document_id: str
    filename: str
    message: str
    chunk_count: int

class DocumentDeleteResponse(BaseModel):
    """Document delete response model"""
    message: str
    document_id: str
    deleted_chunks: int

class SystemStats(BaseModel):
    """System statistics model"""
    total_documents: int
    total_chunks: int
    total_users: int
    total_conversations: int
    total_messages: int
    vector_store_size: Optional[str] = None
    database_size: Optional[str] = None

class ActivityLog(BaseModel):
    """Activity log model"""
    log_id: str
    user_id: str
    username: str
    action: str
    details: Dict[str, Any]
    timestamp: datetime
    ip_address: Optional[str] = None

# Database Models (for internal use)
class UserInDB(BaseModel):
    """User database model"""
    user_id: str
    username: str
    email: str
    hashed_password: str
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    is_verified: bool = False
    failed_login_attempts: int = 0

class ChangePasswordRequest(BaseModel):
    """Change password request model"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    @validator('new_password')
    def validate_new_password(cls, v):
        """Validate new password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        return v

class ForgotPasswordRequest(BaseModel):
    """Forgot password request model"""
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    """Reset password request model"""
    token: str
    new_password: str = Field(..., min_length=8)
    
    @validator('new_password')
    def validate_new_password(cls, v):
        """Validate new password strength"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        return v

class PasswordResetResponse(BaseModel):
    """Password reset response model"""
    message: str
    success: bool

class AdminLoginRequest(BaseModel):
    email: str
    password: str

class Admin2FAVerifyRequest(BaseModel):
    user_id: str
    code: str
    temp_token: str
