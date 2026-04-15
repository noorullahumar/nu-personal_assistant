# cleanup_conversations.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

async def cleanup_conversations():
    """Clean up corrupted conversation records from MongoDB"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.nu_ai_db
    conversations = db.conversations
    chat_messages = db.chat_history
    
    print("🔍 Scanning for invalid conversations...")
    
    invalid_count = 0
    fixed_count = 0
    
    cursor = conversations.find({})
    
    async for conv in cursor:
        issues = []
        
        # Check for missing conversation_id
        if not conv.get("conversation_id"):
            issues.append("missing conversation_id")
        
        # Check for missing user_id
        if not conv.get("user_id"):
            issues.append("missing user_id")
        
        # Check for missing created_at
        if not conv.get("created_at"):
            issues.append("missing created_at")
        
        # Check for invalid conversation_id format
        conv_id = conv.get("conversation_id")
        if conv_id and len(conv_id) < 10:
            issues.append("invalid conversation_id format")
        
        if issues:
            print(f"❌ Invalid conversation {conv.get('_id')}: {', '.join(issues)}")
            
            # Delete the invalid conversation
            await conversations.delete_one({"_id": conv["_id"]})
            invalid_count += 1
            print(f"   Deleted invalid conversation")
            
            # Also delete any associated messages
            if conv.get("conversation_id"):
                result = await chat_messages.delete_many({"conversation_id": conv["conversation_id"]})
                if result.deleted_count > 0:
                    print(f"   Also deleted {result.deleted_count} associated messages")
    
    print(f"\n✅ Cleanup complete!")
    print(f"   - Invalid conversations deleted: {invalid_count}")
    print(f"   - Fixed conversations: {fixed_count}")
    
    # Show remaining valid conversations
    valid_count = await conversations.count_documents({})
    print(f"   - Remaining valid conversations: {valid_count}")
    
    # Close connection properly
    client.close()
    print("   - Database connection closed")

async def list_all_conversations():
    """List all conversations for debugging"""
    try:
        client = AsyncIOMotorClient('mongodb://localhost:27017')
        db = client.nu_ai_db
        conversations = db.conversations
        
        print("\n📋 Current conversations in database:")
        cursor = conversations.find({})
        count = 0
        
        async for conv in cursor:
            count += 1
            print(f"\n   {count}. ID: {conv.get('_id')}")
            print(f"      Conversation ID: {conv.get('conversation_id')}")
            print(f"      User ID: {conv.get('user_id')}")
            print(f"      Title: {conv.get('title')}")
            print(f"      Created: {conv.get('created_at')}")
            print(f"      Message Count: {conv.get('message_count')}")
        
        if count == 0:
            print("   No conversations found")
        
        client.close()
        return count
        
    except Exception as e:
        print(f"Error listing conversations: {e}")
        return 0

async def delete_user_conversations(user_id: str):
    """Delete all conversations for a specific user"""
    try:
        client = AsyncIOMotorClient('mongodb://localhost:27017')
        db = client.nu_ai_db
        conversations = db.conversations
        chat_messages = db.chat_history
        
        print(f"\n🗑️ Deleting conversations for user: {user_id}")
        
        # Find all conversations for this user
        user_conversations = []
        cursor = conversations.find({"user_id": user_id})
        async for conv in cursor:
            user_conversations.append(conv)
        
        print(f"   Found {len(user_conversations)} conversations")
        
        # Delete messages first
        for conv in user_conversations:
            conv_id = conv.get("conversation_id")
            if conv_id:
                result = await chat_messages.delete_many({"conversation_id": conv_id})
                print(f"   Deleted {result.deleted_count} messages from {conv_id}")
        
        # Delete conversations
        result = await conversations.delete_many({"user_id": user_id})
        print(f"   Deleted {result.deleted_count} conversations")
        
        client.close()
        return result.deleted_count
        
    except Exception as e:
        print(f"Error deleting conversations: {e}")
        return 0

async def get_user_conversations(user_id: str):
    """Get all conversations for a specific user"""
    try:
        client = AsyncIOMotorClient('mongodb://localhost:27017')
        db = client.nu_ai_db
        conversations = db.conversations
        
        print(f"\n📋 Conversations for user: {user_id}")
        cursor = conversations.find({"user_id": user_id})
        count = 0
        
        async for conv in cursor:
            count += 1
            print(f"\n   {count}. {conv.get('conversation_id')}")
            print(f"      Title: {conv.get('title')}")
            print(f"      Messages: {conv.get('message_count')}")
        
        if count == 0:
            print("   No conversations found")
        
        client.close()
        return count
        
    except Exception as e:
        print(f"Error getting conversations: {e}")
        return 0

if __name__ == "__main__":
    print("=" * 50)
    print("NU AI Conversation Cleanup Tool")
    print("=" * 50)
    
    # First list existing conversations
    print("\n1. Listing all conversations...")
    count = asyncio.run(list_all_conversations())
    
    if count == 0:
        print("\n✅ No conversations found in database.")
    else:
        print(f"\n📊 Total conversations: {count}")
        print("\n" + "=" * 50)
        print("Options:")
        print("1. Clean up invalid conversations (recommended)")
        print("2. Delete all conversations for a specific user")
        print("3. Delete ALL conversations (use with caution!)")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            print("\n🔧 Cleaning up invalid conversations...")
            asyncio.run(cleanup_conversations())
            
        elif choice == '2':
            user_id = input("\nEnter User ID to delete conversations: ").strip()
            if user_id:
                # First show user's conversations
                asyncio.run(get_user_conversations(user_id))
                confirm = input(f"\n⚠️ Delete ALL conversations for user {user_id}? (yes/no): ")
                if confirm.lower() == 'yes':
                    deleted = asyncio.run(delete_user_conversations(user_id))
                    print(f"\n✅ Deleted {deleted} conversations")
            
        elif choice == '3':
            print("\n⚠️⚠️⚠️ WARNING: This will delete ALL conversations! ⚠️⚠️⚠️")
            confirm = input("Type 'DELETE ALL' to confirm: ")
            if confirm == 'DELETE ALL':
                asyncio.run(cleanup_conversations())
                print("\n✅ All invalid conversations cleaned up")
            else:
                print("Operation cancelled")
        
        else:
            print("Exiting...")
    
    print("\n" + "=" * 50)
    print("Done!")