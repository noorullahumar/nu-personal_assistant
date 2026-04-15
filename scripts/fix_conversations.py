# fix_conversations.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def fix_conversations():
    """Fix conversations by removing invalid ones"""
    
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.nu_ai_db
    conversations = db.conversations
    
    print("🔍 Fixing conversations...")
    
    # Find all conversations
    invalid_ids = []
    cursor = conversations.find({})
    
    async for conv in cursor:
        conv_id = conv.get("conversation_id")
        
        # Check if conversation_id is valid
        if not conv_id or len(conv_id) < 10:
            invalid_ids.append(conv["_id"])
            print(f"❌ Found invalid conversation: {conv.get('_id')}")
    
    # Delete invalid conversations
    if invalid_ids:
        result = await conversations.delete_many({"_id": {"$in": invalid_ids}})
        print(f"\n✅ Deleted {result.deleted_count} invalid conversations")
    else:
        print("\n✅ No invalid conversations found")
    
    # Show remaining conversations
    remaining = await conversations.count_documents({})
    print(f"📊 Remaining conversations: {remaining}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_conversations())