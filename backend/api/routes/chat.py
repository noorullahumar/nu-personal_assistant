"""
Chat routes for AI conversations
Location: backend/api/routes/chat.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime
import uuid
import logging

from backend.core.security import sanitize_input, sanitize_output
from backend.api.dependencies.auth_deps import get_current_user
from backend.database.mongodb import conversation_collection, chat_collection
from backend.rag.rag_pipeline import get_qa_chain, role_based_query
from backend.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
@router.post("", response_model=ChatResponse)  # Support both with and without trailing slash
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Process chat message and return AI response
    """
    try:
        # Sanitize input
        sanitized_query = sanitize_input(chat_request.query, max_length=2000)
        
        logger.info(f"Chat request from user {current_user['user_id']}: {sanitized_query[:50]}...")
        
        conversation_id = chat_request.conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            title = sanitized_query[:30] + "..." if len(sanitized_query) > 30 else sanitized_query
            await conversation_collection.insert_one({
                "conversation_id": conversation_id,
                "user_id": current_user["user_id"],
                "title": title,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "message_count": 0
            })
        
        # Save user message
        user_message_id = str(uuid.uuid4())
        await chat_collection.insert_one({
            "message_id": user_message_id,
            "conversation_id": conversation_id,
            "user_id": current_user["user_id"],
            "role": "user",
            "content": sanitized_query,
            "timestamp": datetime.utcnow()
        })
        
        await conversation_collection.update_one(
            {"conversation_id": conversation_id},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Get response from RAG pipeline
        chain = await get_qa_chain()
        if not chain:
            reply = "Knowledge base is empty. Please contact admin to upload documents."
        else:
            response = await role_based_query(chain, sanitized_query)
            reply = response.get("result", "I couldn't generate a response.")
        
        # Sanitize output
        reply = sanitize_output(reply)
        
        # Save assistant message
        assistant_message_id = str(uuid.uuid4())
        await chat_collection.insert_one({
            "message_id": assistant_message_id,
            "conversation_id": conversation_id,
            "user_id": "assistant",
            "role": "assistant",
            "content": reply,
            "timestamp": datetime.utcnow()
        })
        
        await conversation_collection.update_one(
            {"conversation_id": conversation_id},
            {"$inc": {"message_count": 1}}
        )
        
        return ChatResponse(
            reply=reply,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            needs_clarification=False
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))