"""
Production configuration with strict validation
Location: backend/config.py
"""
import os
from typing import List, Optional
from dotenv import load_dotenv

# Load .env file if it exists (works locally, ignored in Docker if missing)
load_dotenv()

class Settings:
    """Application settings"""
    
    # ========== REQUIRED SECRETS ==========
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MONGO_URL: str = os.getenv("MONGO_URL", "")
    
    # ========== JWT CONFIGURATION ==========
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # ========== SECURITY ==========
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "12"))
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES: int = int(os.getenv("LOCKOUT_MINUTES", "15"))
    
    # ========== CORS ==========
    ALLOWED_ORIGINS_STR: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
    
    # ========== RATE LIMITING ==========
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    RATE_LIMIT_CHAT: str = os.getenv("RATE_LIMIT_CHAT", "30/minute")
    RATE_LIMIT_CHAT_DAILY: str = os.getenv("RATE_LIMIT_CHAT_DAILY", "500/day")
    
    # ========== EMAIL (Optional) ==========
    MAIL_SERVER: Optional[str] = os.getenv("MAIL_SERVER")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME: Optional[str] = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = os.getenv("MAIL_PASSWORD")
    MAIL_FROM: Optional[str] = os.getenv("MAIL_FROM")
    MAIL_USE_TLS: bool = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    
    # ========== FRONTEND ==========
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:8000")
    
    # ========== FILE UPLOADS ==========
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    ALLOWED_EXTENSIONS_STR: str = os.getenv("ALLOWED_EXTENSIONS", ".pdf,.txt,.doc,.docx")
    
    # ========== ENVIRONMENT ==========
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # ========== DATABASE ==========
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "nu_ai_db")
    
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Convert comma-separated string to list"""
        if not self.ALLOWED_ORIGINS_STR:
            return ["http://localhost:8000", "http://127.0.0.1:8000"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
    
    @property
    def ALLOWED_EXTENSIONS(self) -> List[str]:
        """Convert comma-separated extensions to list"""
        if not self.ALLOWED_EXTENSIONS_STR:
            return [".pdf", ".txt", ".doc", ".docx"]
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS_STR.split(",") if ext.strip()]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT.lower() == "development"


# Create global settings instance
try:
    settings = Settings()
    # Validate required fields
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY is required")
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required")
    if not settings.MONGO_URL:
        raise ValueError("MONGO_URL is required")
    
    print(f"✅ Configuration loaded - Environment: {settings.ENVIRONMENT}")
    print(f"✅ Allowed origins: {settings.ALLOWED_ORIGINS}")
    print(f"✅ Frontend URL: {settings.FRONTEND_URL}")
except Exception as e:
    print(f"❌ CONFIGURATION ERROR: {e}")
    print("Please check your .env file and ensure all required variables are set")
    raise


# ========== HELPER FUNCTIONS ==========
def get_secret(secret: str) -> str:
    """
    Helper function to get secret values safely.
    In production, this could integrate with a secret manager.
    """
    return secret


# ========== EXPORT COMMONLY USED SETTINGS ==========
SECRET_KEY = settings.SECRET_KEY
OPENAI_API_KEY = settings.OPENAI_API_KEY
MONGO_URL = settings.MONGO_URL
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES