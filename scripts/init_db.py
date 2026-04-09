from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def init_database():
    MONGO_DETAILS = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(MONGO_DETAILS)
    db = client.nu_ai_db1
    
    print("Creating indexes...")
    
    await db.conversations.create_index("conversation_id", unique=True)
    await db.conversations.create_index("user_id")
    await db.conversations.create_index("created_at")
    await db.conversations.create_index("updated_at")
    
    await db.chat_history.create_index("conversation_id")
    await db.chat_history.create_index("user_id")
    await db.chat_history.create_index("timestamp")
    await db.chat_history.create_index([("conversation_id", 1), ("timestamp", 1)])
    
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("email", unique=True)
    
    await db.activity_logs.create_index("timestamp")
    await db.activity_logs.create_index("user_id")
    await db.activity_logs.create_index("action")
    await db.activity_logs.create_index([("timestamp", -1)])
    
    await db.documents.create_index("document_id", unique=True)
    await db.documents.create_index("upload_date")
    
    await db.knowledge_base.create_index("metadata.document_id")
    await db.knowledge_base.create_index("metadata.source")
    
    print("✅ Database indexes created successfully")
    
    import uuid
    from datetime import datetime
    
    admin_exists = await db.users.find_one({"email": "admin@example.com"})
    if not admin_exists:
        await db.users.insert_one({
            "user_id": "admin",
            "username": "Admin",
            "email": "admin@example.com",
            "role": "admin",
            "created_at": datetime.utcnow()
        })
        print("✅ Default admin user created")
    
    user_exists = await db.users.find_one({"email": "user@example.com"})
    if not user_exists:
        await db.users.insert_one({
            "user_id": "default_user",
            "username": "User",
            "email": "user@example.com",
            "role": "user",
            "created_at": datetime.utcnow()
        })
        print("✅ Default user created")

if __name__ == "__main__":
    asyncio.run(init_database())
    print("Database initialization complete!")