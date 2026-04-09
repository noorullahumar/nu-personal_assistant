"""
User repository for database operations
Location: backend/database/repositories/user_repo.py
"""
from typing import Optional, Dict, Any
from datetime import datetime
from backend.database.mongodb import user_collection


class UserRepository:
    """Repository for user database operations"""
    
    @staticmethod
    async def find_by_email(email: str) -> Optional[Dict[str, Any]]:
        """Find user by email"""
        return await user_collection.find_one({"email": email})
    
    @staticmethod
    async def find_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Find user by ID"""
        return await user_collection.find_one({"user_id": user_id})
    
    @staticmethod
    async def create(user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new user"""
        result = await user_collection.insert_one(user_data)
        if result.inserted_id:
            return user_data
        return None
    
    @staticmethod
    async def update_password(user_id: str, hashed_password: str) -> bool:
        """Update user password"""
        result = await user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"hashed_password": hashed_password, "password_changed_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    @staticmethod
    async def increment_failed_attempts(user_id: str) -> None:
        """Increment failed login attempts"""
        await user_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"failed_login_attempts": 1}, "$set": {"last_failed_login": datetime.utcnow()}}
        )
    
    @staticmethod
    async def reset_failed_attempts(user_id: str) -> None:
        """Reset failed login attempts"""
        await user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"failed_login_attempts": 0}}
        )
    
    @staticmethod
    async def update_last_login(user_id: str, ip_address: str) -> None:
        """Update last login information"""
        await user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.utcnow(), "last_login_ip": ip_address}}
        )
    
    @staticmethod
    async def set_reset_token(user_id: str, token: str) -> None:
        """Set password reset token"""
        await user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"reset_token": token, "reset_token_created_at": datetime.utcnow()}}
        )
    
    @staticmethod
    async def clear_reset_token(user_id: str) -> None:
        """Clear password reset token"""
        await user_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"reset_token": "", "reset_token_created_at": ""}}
        )

    @staticmethod
    async def find_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
        """Find user by reset token"""
        return await user_collection.find_one({"reset_token": token})