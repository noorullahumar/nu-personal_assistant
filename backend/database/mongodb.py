import os
import ssl
import asyncio
import email
import logging
from datetime import datetime

from dotenv import load_dotenv
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

import os
from urllib.parse import quote_plus
# Load environment variables
load_dotenv()
MONGO_DB_NAME = os.getenv("MONGO_DB")
# Database Connection 
# Assemble the final URI
MONGO_DETAILS = os.getenv("MONGO_URL")
# NEW WORKING CODE
if MONGO_DETAILS and "mongodb+srv" in MONGO_DETAILS:
    client = AsyncIOMotorClient(
        MONGO_DETAILS,
        tls=True,                          # Use 'tls' instead of 'ssl'
        tlsAllowInvalidCertificates=False  # This replaces cert_reqs=ssl.CERT_REQUIRED
    )
else:
    client = AsyncIOMotorClient(MONGO_DETAILS)

# Database and collections
database = client[MONGO_DB_NAME]

doc_collection = database.get_collection("knowledge_base")
file_collection = database.get_collection("documents")
chat_collection = database.get_collection("chat_history")
conversation_collection = database.get_collection("conversations")
user_collection = database.get_collection("users")
activity_log_collection = database.get_collection("activity_logs")
refresh_token_collection = database.get_collection("refresh_tokens")
admin_session_collection = database.get_collection("admin_sessions")
admin_2fa_collection = database.get_collection("admin_2fa")
contact_collection = database.get_collection("contact_messages")

# Add to __all__ if needed

# Fixed: wrap async DB call inside function
async def safe_find_user(user_email):
    try:
        return await user_collection.find_one({"email": user_email})
    except Exception as e:
        logger.error(f"Database error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Index creation
# Add after other collections
refresh_token_collection = database.get_collection("refresh_tokens")

async def create_indexes():
    """Create database indexes with proper error handling"""
    
    # Activity logs index with TTL - handle existing index
    try:
        # Check if index exists first
        existing_indexes = await activity_log_collection.index_information()
        
        if "timestamp_1" in existing_indexes:
            # Check if it has TTL
            existing_opts = existing_indexes["timestamp_1"]
            if "expireAfterSeconds" not in existing_opts:
                # Drop and recreate with TTL
                await activity_log_collection.drop_index("timestamp_1")
                await activity_log_collection.create_index(
                    "timestamp",
                    expireAfterSeconds=7776000  # 90 days
                )
                print("✅ Recreated activity_logs index with TTL")
            else:
                print("✅ activity_logs index already has TTL")
        else:
            await activity_log_collection.create_index(
                "timestamp",
                expireAfterSeconds=7776000
            )
            print("✅ Created activity_logs index with TTL")
    except Exception as e:
        print(f"⚠️ Index creation warning: {e}")
    
    # Compound indexes for common queries
    try:
        await conversation_collection.create_index(
            [("user_id", 1), ("updated_at", -1)]
        )
        print("✅ Created conversation index")
    except Exception as e:
        print(f"⚠️ Conversation index warning: {e}")
    
    try:
        await chat_collection.create_index(
            [("conversation_id", 1), ("timestamp", 1)]
        )
        print("✅ Created chat index")
    except Exception as e:
        print(f"⚠️ Chat index warning: {e}")
    
    try:
        await file_collection.create_index(
            [("uploaded_by", 1), ("upload_date", -1)]
        )
        print("✅ Created file index")
    except Exception as e:
        print(f"⚠️ File index warning: {e}")
    
    # Refresh tokens index
    try:
        await refresh_token_collection.create_index("token", unique=True)
        print("✅ Created refresh token index")
    except Exception as e:
        print(f"⚠️ Refresh token index warning: {e}")
    
    try:
        await refresh_token_collection.create_index(
            "expires_at",
            expireAfterSeconds=0
        )
        print("✅ Created refresh token TTL index")
    except Exception as e:
        print(f"⚠️ Refresh token TTL index warning: {e}")

async def log_admin_activity(admin_id: str, action: str, details: dict):
    activity_log = {
        "admin_id": admin_id,
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow()
    }
    # This saves the record to your "admin_logs" collection in MongoDB
    await database.admin_logs.insert_one(activity_log)
    print(f"🛡️ Activity Logged: {action} for admin {admin_id}")

# Database initialization
async def init_database():
    try:
        await client.admin.command('ping')
        print("✅ Connected to MongoDB")
        
        await create_indexes()
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")


# Entry point
if __name__ == "__main__":
    async def main():
        await init_database()
    
    asyncio.run(main())
