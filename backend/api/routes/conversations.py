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

# Change the router line to disable trailing slash redirect
router = APIRouter(prefix="/api/conversations", tags=["Conversations"], redirect_slashes=False)

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
        conversations_list = []
        
        # Get cursor for user's conversations
        cursor = conversation_collection.find(
            {"user_id": current_user["user_id"]}
        ).sort("updated_at", -1)
        
        async for conv in cursor:
            try:
                # Get last message safely
                last_msg = None
                try:
                    last_msg = await chat_collection.find_one(
                        {"conversation_id": conv["conversation_id"], "role": "user"},
                        sort=[("timestamp", -1)]
                    )
                except Exception as msg_error:
                    logger.error(f"Error getting last message: {msg_error}")
                
                # Create preview text
                preview_text = "No messages"
                if last_msg and last_msg.get("content"):
                    content = last_msg["content"]
                    preview_text = content[:50] + "..." if len(content) > 50 else content
                
                # Create conversation summary
                conversation_summary = ConversationSummary(
                    conversation_id=conv["conversation_id"],
                    title=conv.get("title", "Conversation"),
                    created_at=conv.get("created_at", datetime.utcnow()),
                    updated_at=conv.get("updated_at", datetime.utcnow()),
                    message_count=conv.get("message_count", 0),
                    preview=preview_text
                )
                conversations_list.append(conversation_summary)
                
            except Exception as conv_error:
                logger.error(f"Error processing conversation: {conv_error}")
                continue
        
        # IMPORTANT: Return ONLY the list - nothing else!
        logger.info(f"Returning {len(conversations_list)} conversations for user {current_user['user_id']}")
        return conversations_list
        
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}", exc_info=True)
        # Return empty list on error - NOT an error object
        return []


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all messages for a specific conversation"""
    try:
        if not conversation_id:
            raise HTTPException(status_code=400, detail="Invalid conversation ID")
        
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
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", datetime.utcnow()).isoformat()
            })
        
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a conversation and all its messages"""
    try:
        if not conversation_id:
            raise HTTPException(status_code=400, detail="Invalid conversation ID")
        
        conv = await conversation_collection.find_one({
            "conversation_id": conversation_id,
            "user_id": current_user["user_id"]
        })
        
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Delete all messages in the conversation
        delete_messages_result = await chat_collection.delete_many({"conversation_id": conversation_id})
        logger.info(f"Deleted {delete_messages_result.deleted_count} messages from conversation {conversation_id}")
        
        # Delete the conversation itself
        delete_conversation_result = await conversation_collection.delete_one({"conversation_id": conversation_id})
        
        if delete_conversation_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "message": "Conversation deleted successfully",
            "deleted_messages": delete_messages_result.deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete conversation")
    