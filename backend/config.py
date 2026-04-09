"""
Production configuration with strict validation
Location: backend/config.py
"""
import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings with validation"""
    
    # ========== REQUIRED SECRETS ==========
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    MONGO_URL: str = Field(..., env="MONGO_URL")
    
    # ========== JWT CONFIGURATION ==========
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # ========== SECURITY ==========
    BCRYPT_ROUNDS: int = Field(12, env="BCRYPT_ROUNDS")
    MAX_LOGIN_ATTEMPTS: int = Field(5, env="MAX_LOGIN_ATTEMPTS")
    LOCKOUT_MINUTES: int = Field(15, env="LOCKOUT_MINUTES")
    
    # ========== CORS ==========
    ALLOWED_ORIGINS_STR: str = Field(
        default="http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000, http://127.0.0.1:8000"  ,    
        env="ALLOWED_ORIGINS"
    )
    
    # ========== RATE LIMITING ==========
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_LOGIN: str = Field("5/minute", env="RATE_LIMIT_LOGIN")
    RATE_LIMIT_CHAT: str = Field("30/minute", env="RATE_LIMIT_CHAT")
    RATE_LIMIT_CHAT_DAILY: str = Field("500/day", env="RATE_LIMIT_CHAT_DAILY")
    
    # ========== EMAIL (Optional) ==========
    MAIL_SERVER: Optional[str] = Field(None, env="MAIL_SERVER")
    MAIL_PORT: int = Field(587, env="MAIL_PORT")
    MAIL_USERNAME: Optional[str] = Field(None, env="MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = Field(None, env="MAIL_PASSWORD")
    MAIL_FROM: Optional[str] = Field(None, env="MAIL_FROM")
    MAIL_USE_TLS: bool = Field(True, env="MAIL_USE_TLS")
    
    # ========== FRONTEND ==========
    FRONTEND_URL: str = Field("http://localhost:5500", env="FRONTEND_URL")
    
    # ========== FILE UPLOADS ==========
    MAX_UPLOAD_SIZE_MB: int = Field(10, env="MAX_UPLOAD_SIZE_MB")
    ALLOWED_EXTENSIONS_STR: str = Field(".pdf,.txt,.doc,.docx", env="ALLOWED_EXTENSIONS")
    
    # ========== ENVIRONMENT ==========
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    DEBUG: bool = Field(True, env="DEBUG")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    
    # ========== DATABASE ==========
    DATABASE_NAME: str = Field("nu_ai_db", env="DATABASE_NAME")

    @field_validator('ENVIRONMENT')
    @classmethod
    def validate_environment(cls, v):
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v
    
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Convert comma-separated string to list"""
        if not self.ALLOWED_ORIGINS_STR:
            return ["http://localhost:5500", "http://127.0.0.1:5500"]
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Create global settings instance
try:
    settings = Settings()
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
    In production, this could integrate with a secret manager like AWS Secrets Manager or HashiCorp Vault.
    """
    return secret


# ========== EXPORT COMMONLY USED SETTINGS ==========
SECRET_KEY = settings.SECRET_KEY
OPENAI_API_KEY = settings.OPENAI_API_KEY
MONGO_URL = settings.MONGO_URL
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES