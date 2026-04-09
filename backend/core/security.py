import os
import hashlib
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List  # Add List to imports
from jose import jwt
import bcrypt
from passlib.context import CryptContext
from backend.config import settings, get_secret
from dotenv import load_dotenv
import logging


logger = logging.getLogger(__name__)
# Password hashing context with bcrypt (industry standard)
# Password hashing - Use bcrypt with proper settings
try:
    # Create password context with bcrypt and fallback
    pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=12,  # Reasonable default
    )
    # Test the context
    pwd_context.hash("test")
    logger.info("bcrypt initialized successfully")
except Exception as e:
    logger.warning(f"bcrypt init error: {e}, falling back to sha256_crypt")
    # Fallback to sha256_crypt if bcrypt fails
    pwd_context = CryptContext(
        schemes=["sha256_crypt"],
        deprecated="auto",
    )


load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_HOURS", "1"))


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt (industry standard)
    
    Args:
        password: Plain text password
        
    Returns:
        bcrypt hash string
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against bcrypt hash
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored bcrypt hash
        
    Returns:
        True if password matches, False otherwise
    """
    if not plain_password or not hashed_password:
        return False
    
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength with comprehensive requirements
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    # Check for common weak patterns
    weak_patterns = [
        r'password', r'123456', r'qwerty', r'admin', r'letmein',
        r'welcome', r'monkey', r'dragon', r'master', r'login',
        r'abc123', r'football', r'whatever', r'supersecure'
    ]
    password_lower = password.lower()
    for pattern in weak_patterns:
        if pattern in password_lower:
            return False, f"Password contains common weak pattern: '{pattern}'"
    
    return True, None


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token with expiration and unique ID
    
    Args:
        data: Payload data to encode
        expires_delta: Custom expiration time (optional)
        
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": secrets.token_urlsafe(32)  # Unique token ID for revocation
    })
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create refresh token with longer expiration
    
    Args:
        data: Payload data to encode
        
    Returns:
        Refresh token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)
    })
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Decoded payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True}
        )
        
        # Verify token type
        if payload.get("type") != token_type:
            return None
        
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def sanitize_input(text: str, max_length: int = 2000) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Trim to max length
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove script tags and dangerous protocols
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'vbscript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    text = re.sub(r'data:text/html', '', text, flags=re.IGNORECASE)
    
    # Escape HTML entities
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
        ">": "&gt;",
        "<": "&lt;",
    }
    text = "".join(html_escape_table.get(c, c) for c in text)
    
    return text.strip()


def sanitize_output(text: str) -> str:
    """
    Sanitize LLM output before sending to client
    
    Args:
        text: Output text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Escape HTML to prevent XSS from LLM responses
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
        ">": "&gt;",
        "<": "&lt;",
    }
    return "".join(html_escape_table.get(c, c) for c in text)

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and directory traversal attacks.
    
    This function:
    - Removes path traversal patterns (../, ..\\)
    - Removes dangerous characters
    - Ensures filename is safe for filesystem operations
    - Generates a safe fallback name if needed
    
    Args:
        filename: Original filename from user upload
        
    Returns:
        Sanitized, safe filename for filesystem storage
        
    Examples:
        >>> sanitize_filename("../../etc/passwd")
        'etc_passwd'
        >>> sanitize_filename("file<script>.pdf")
        'file.pdf'
        >>> sanitize_filename("my document.txt")
        'my_document.txt'
    """
    if not filename:
        return f"file_{secrets.token_hex(8)}"
    
    # Remove path traversal attempts
    # Replace Windows and Unix path separators
    filename = filename.replace('../', '')
    filename = filename.replace('..\\', '')
    filename = filename.replace('./', '')
    filename = filename.replace('.\\', '')
    
    # Remove any remaining path separators
    filename = filename.replace('/', '_')
    filename = filename.replace('\\', '_')
    
    # Remove null bytes and control characters
    filename = filename.replace('\x00', '')
    filename = ''.join(char for char in filename if ord(char) >= 32 or char == '.')
    
    # Remove potentially dangerous characters
    # Keep only alphanumeric, dots, underscores, hyphens, and spaces
    filename = re.sub(r'[^a-zA-Z0-9._\-\s]', '', filename)
    
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    
    # Remove multiple consecutive dots
    filename = re.sub(r'\.{2,}', '.', filename)
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Limit length (max 255 characters for most filesystems)
    if len(filename) > 255:
        name_part, ext_part = os.path.splitext(filename)
        filename = name_part[:250] + ext_part
    
    # If filename is empty after sanitization, generate a safe one
    if not filename or filename == '.':
        filename = f"file_{secrets.token_hex(8)}"
    
    return filename


def sanitize_filename_advanced(filename: str, allowed_extensions: Optional[List[str]] = None) -> Tuple[str, str]:
    """
    Advanced filename sanitization with extension validation.
    
    This function:
    - Validates file extension against allowed list
    - Generates a secure random name for storage
    - Preserves original filename for display
    
    Args:
        filename: Original filename from user upload
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.txt'])
        
    Returns:
        Tuple of (safe_storage_name, original_display_name)
        
    Example:
        >>> sanitize_filename_advanced("my report.pdf", ['.pdf', '.txt'])
        ('a1b2c3d4e5f6.pdf', 'my_report.pdf')
    """
    if not filename:
        raise ValueError("Filename cannot be empty")
    
    # Extract extension
    ext = os.path.splitext(filename)[1].lower()
    
    # Validate extension if allowed list provided
    if allowed_extensions and ext not in allowed_extensions:
        raise ValueError(f"File extension '{ext}' not allowed. Allowed: {', '.join(allowed_extensions)}")
    
    # Sanitize display name (for UI)
    display_name = sanitize_filename(filename)
    
    # Generate secure random storage name
    random_name = secrets.token_hex(16)
    storage_name = f"{random_name}{ext}"
    
    return storage_name, display_name


def validate_file_content(content: bytes, max_size_mb: int = 10) -> Tuple[bool, Optional[str]]:
    """
    Validate file content for security threats.
    
    Checks:
    - File size limits
    - Magic bytes/headers
    - Suspicious patterns (PHP, JS, etc.)
    
    Args:
        content: File content as bytes
        max_size_mb: Maximum allowed file size in MB
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # Check file size
    if len(content) > max_size_bytes:
        return False, f"File too large. Maximum {max_size_mb}MB"
    
    # Check for null bytes (potential injection)
    if b'\x00' in content[:1024]:
        return False, "File contains null bytes - possible injection attempt"
    
    # Check for suspicious patterns in first 4KB
    suspicious_patterns = [
        b'<?php',
        b'<script',
        b'exec(',
        b'system(',
        b'eval(',
        b'base64_decode',
        b'passthru(',
        b'shell_exec',
        b'javascript:',
        b'vbscript:',
        b'onload=',
        b'onerror=',
        b'<iframe',
        b'<object',
        b'<embed',
        b'data:text/html',
    ]
    
    content_sample = content[:4096]  # Check first 4KB
    for pattern in suspicious_patterns:
        if pattern in content_sample:
            return False, f"File contains suspicious pattern: {pattern.decode('utf-8', errors='ignore')}"
    
    return True, None


def is_allowed_file_type(filename: str, allowed_extensions: List[str]) -> bool:
    """
    Check if file extension is in allowed list.
    
    Args:
        filename: Original filename
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.txt'])
        
    Returns:
        True if extension is allowed, False otherwise
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions


def get_file_size_mb(content: bytes) -> float:
    """
    Get file size in megabytes.
    
    Args:
        content: File content as bytes
        
    Returns:
        File size in MB
    """
    return len(content) / (1024 * 1024)

def generate_reset_token(email: str) -> str:
    """
    Generate password reset token
    
    Args:
        email: User email address
        
    Returns:
        Secure reset token
    """
    from itsdangerous import URLSafeTimedSerializer
    
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps(email, salt="password-reset-salt")


def verify_reset_token(token: str, expiration: int = 3600) -> Optional[str]:
    """
    Verify password reset token
    
    Args:
        token: Reset token
        expiration: Token expiration in seconds (default 1 hour)
        
    Returns:
        Email if valid, None otherwise
    """
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
    
    try:
        serializer = URLSafeTimedSerializer(SECRET_KEY)
        email = serializer.loads(token, salt="password-reset-salt", max_age=expiration)
        return email
    except (BadSignature, SignatureExpired):
        return None

def generate_password_reset_token(email: str) -> str:
    """
    Generate a password reset token for the given email
    
    Args:
        email: User's email address
    
    Returns:
        JWT token string
    """
    expire = datetime.utcnow() + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
    to_encode = {
        "sub": email,
        "exp": expire,
        "type": "password_reset"
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """
    Verify password reset token and return the email if valid
    
    Args:
        token: JWT token to verify
    
    Returns:
        Email address if token is valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check if it's a password reset token
        if payload.get("type") != "password_reset":
            return None
        
        email = payload.get("sub")
        if email is None:
            return None
            
        return email
        
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_password_hash(password: str) -> str:
    """Hash a password - THIS FUNCTION WAS MISSING"""
    return pwd_context.hash(password)
