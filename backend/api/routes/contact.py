"""
Contact routes for handling contact form submissions
Location: backend/api/routes/contact.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime, timedelta
import uuid
import logging
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

from backend.api.dependencies.auth_deps import get_current_admin, get_current_user_optional
from backend.database.mongodb import contact_collection, user_collection
from backend.core.security import sanitize_input
from backend.utils.email import send_reply_email  # Make sure this function exists

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contact", tags=["Contact"])


# ========== MODELS ==========
class ContactRequest(BaseModel):
    """Contact form submission request"""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)


class ContactResponse(BaseModel):
    """Contact submission response"""
    message_id: str
    status: str
    submitted_at: datetime


class ContactMessage(BaseModel):
    """Contact message model for admin view"""
    message_id: str
    name: str
    email: str
    subject: str
    message: str
    status: str
    submitted_at: datetime
    read_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None


class ContactReplyRequest(BaseModel):
    """Admin reply to contact message"""
    reply: str = Field(..., min_length=1, max_length=5000)


# ========== PUBLIC ENDPOINTS ==========
@router.post("/submit", response_model=ContactResponse)
async def submit_contact_form(
    request: Request,
    contact_data: ContactRequest
):
    """Submit a contact form message (public endpoint)"""
    try:
        # Sanitize inputs
        sanitized_name = sanitize_input(contact_data.name)
        sanitized_subject = sanitize_input(contact_data.subject)
        sanitized_message = sanitize_input(contact_data.message)
        
        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Check for logged in user (optional)
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from backend.core.security import decode_token
                token = auth_header.replace("Bearer ", "")
                payload = decode_token(token, "access")
                if payload:
                    user_id = payload.get("sub")
            except Exception:
                pass
        
        # Create message record
        message_id = str(uuid.uuid4())
        message_doc = {
            "message_id": message_id,
            "name": sanitized_name,
            "email": contact_data.email,
            "subject": sanitized_subject,
            "message": sanitized_message,
            "status": "pending",
            "submitted_at": datetime.utcnow(),
            "read_at": None,
            "replied_at": None,
            "ip_address": client_ip,
            "user_agent": user_agent,
            "user_id": user_id
        }
        
        await contact_collection.insert_one(message_doc)
        
        logger.info(f"Contact message received from {contact_data.email} (ID: {message_id})")
        
        return ContactResponse(
            message_id=message_id,
            status="received",
            submitted_at=message_doc["submitted_at"]
        )
        
    except Exception as e:
        logger.error(f"Contact form error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit message")


# ========== ADMIN ENDPOINTS ==========
@router.get("/messages", response_model=List[ContactMessage])
async def get_contact_messages(
    current_admin: dict = Depends(get_current_admin),
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """Get all contact messages (admin only)"""
    try:
        query = {}
        if status and status in ["pending", "read", "replied", "archived"]:
            query["status"] = status
        
        messages = []
        cursor = contact_collection.find(query).sort("submitted_at", -1).skip(skip).limit(limit)
        
        async for msg in cursor:
            messages.append(ContactMessage(
                message_id=msg["message_id"],
                name=msg["name"],
                email=msg["email"],
                subject=msg["subject"],
                message=msg["message"],
                status=msg["status"],
                submitted_at=msg["submitted_at"],
                read_at=msg.get("read_at"),
                replied_at=msg.get("replied_at"),
                ip_address=msg.get("ip_address"),
                user_agent=msg.get("user_agent"),
                user_id=msg.get("user_id")
            ))
        
        return messages
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.get("/messages/{message_id}")
async def get_contact_message(
    message_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Get single contact message (admin only)"""
    try:
        message = await contact_collection.find_one({"message_id": message_id})
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Mark as read if not already
        if message.get("status") == "pending":
            await contact_collection.update_one(
                {"message_id": message_id},
                {
                    "$set": {
                        "status": "read",
                        "read_at": datetime.utcnow()
                    }
                }
            )
        
        return message
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get message error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get message")


@router.put("/messages/{message_id}/reply")
async def reply_to_contact_message(
    message_id: str,
    reply_data: ContactReplyRequest,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        # Find the message
        message = await contact_collection.find_one({"message_id": message_id})
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Update status to replied
        await contact_collection.update_one(
            {"message_id": message_id},
            {
                "$set": {
                    "status": "replied",
                    "replied_at": datetime.utcnow(),
                    "admin_reply": reply_data.reply,
                    "replied_by": current_admin["user_id"]
                }
            }
        )
        
        # ========== SEND EMAIL TO USER ==========
        email_sent = False
        try:
            from backend.utils.email import send_reply_email
            email_sent = await send_reply_email(
                to_email=message["email"],
                user_name=message["name"],
                original_message=message["message"],
                reply_message=reply_data.reply,
                admin_name=current_admin.get("username", "Admin")
            )
            
            if email_sent:
                logger.info(f"Reply email sent successfully to {message['email']}")
            else:
                logger.warning(f"Failed to send reply email to {message['email']}")
                
        except Exception as email_error:
            logger.error(f"Email error: {str(email_error)}", exc_info=True)
        
        return {
            "success": True,
            "message": "Reply sent successfully",
            "email_sent": email_sent,
            "replied_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reply error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send reply")

@router.delete("/messages/{message_id}")
async def delete_contact_message(
    message_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete a contact message (admin only)"""
    try:
        result = await contact_collection.delete_one({"message_id": message_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Message not found")
        
        logger.info(f"Admin deleted message {message_id}")
        
        return {"success": True, "message": "Message deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete message")


@router.get("/stats")
async def get_contact_stats(
    current_admin: dict = Depends(get_current_admin)
):
    """Get contact message statistics (admin only)"""
    try:
        total = await contact_collection.count_documents({})
        pending = await contact_collection.count_documents({"status": "pending"})
        read = await contact_collection.count_documents({"status": "read"})
        replied = await contact_collection.count_documents({"status": "replied"})
        archived = await contact_collection.count_documents({"status": "archived"})
        
        # Get last 7 days submissions
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        recent = await contact_collection.count_documents({
            "submitted_at": {"$gte": seven_days_ago}
        })
        
        return {
            "total": total,
            "pending": pending,
            "read": read,
            "replied": replied,
            "archived": archived,
            "submitted_last_7_days": recent
        }
        
    except Exception as e:
        logger.error(f"Stats error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get stats")