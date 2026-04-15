# scripts/clean_404_conversations.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def clean_404_errors():
    """Remove 404 error documents from conversations collection"""
    
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.nu_ai_db
    conversations = db.conversations
    
    print("🔍 Looking for 404 error documents...")
    
    # Find documents that have 'error' field (the 404 error)
    error_docs = []
    cursor = conversations.find({"error": {"$exists": True}})
    async for doc in cursor:
        error_docs.append(doc)
        print(f"❌ Found error document: {doc.get('_id')}")
    
    if error_docs:
        result = await conversations.delete_many({"error": {"$exists": True}})
        print(f"✅ Deleted {result.deleted_count} error documents")
    else:
        print("✅ No error documents found")
    
    # Also check for documents without conversation_id
    invalid_docs = []
    cursor = conversations.find({"conversation_id": {"$exists": False}})
    async for doc in cursor:
        invalid_docs.append(doc)
        print(f"❌ Found invalid document (no conversation_id): {doc.get('_id')}")
    
    if invalid_docs:
        result = await conversations.delete_many({"conversation_id": {"$exists": False}})
        print(f"✅ Deleted {result.deleted_count} invalid documents")
    
    # Show remaining count
    remaining = await conversations.count_documents({})
    print(f"\n📊 Remaining conversations: {remaining}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(clean_404_errors())