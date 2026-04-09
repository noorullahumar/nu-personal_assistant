"""
Conversation management routes
Location: backend/api/routes/conversations.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime
import uuid
import logging
from typing import List

from backend.api.dependencies.auth_deps import get_current_user
from backend.database.mongodb import conversation_collection, chat_collection
from backend.models.schemas import ConversationSummary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.post("/create")
async def create_conversation(current_user: dict = Depends(get_current_user)):
    """Create a new conversation for the current user"""
    try:
        conversation_id = str(uuid.uuid4())
        
        conversation = {
            "conversation_id": conversation_id,
            "user_id": current_user["user_id"],
            "title": "New Conversation",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "message_count": 0
        }
        
        await conversation_collection.insert_one(conversation)
        
        return {
            "conversation_id": conversation_id,
            "title": "New Conversation",
            "message": "Conversation created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@router.get("/", response_model=List[ConversationSummary])
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """Get all conversations for the current user"""
    try:
        conversations = []
        cursor = conversation_collection.find(
            {"user_id": current_user["user_id"]}
        ).sort("updated_at", -1)
        
        async for conv in cursor:
            last_msg = await chat_collection.find_one(
                {"conversation_id": conv["conversation_id"], "role": "user"},
                sort=[("timestamp", -1)]
            )
            
            conversations.append(ConversationSummary(
                conversation_id=conv["conversation_id"],
                title=conv["title"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                message_count=conv["message_count"],
                preview=last_msg["content"][:50] + "..." if last_msg else "No messages"
            ))
        
        return conversations
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all messages for a specific conversation"""
    try:
        conv = await conversation_collection.find_one({
            "conversation_id": conversation_id,
            "user_id": current_user["user_id"]
        })
        
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = []
        cursor = chat_collection.find(
            {"conversation_id": conversation_id}
        ).sort("timestamp", 1)
        
        async for msg in cursor:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg["timestamp"].isoformat()
            })
        
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a conversation and all its messages"""
    try:
        conv = await conversation_collection.find_one({
            "conversation_id": conversation_id,
            "user_id": current_user["user_id"]
        })
        
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        await chat_collection.delete_many({"conversation_id": conversation_id})
        await conversation_collection.delete_one({"conversation_id": conversation_id})
        
        return {"message": "Conversation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")