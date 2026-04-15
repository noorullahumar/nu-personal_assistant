from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from typing import List
import os
import shutil
import uuid
from datetime import datetime
import logging
from backend.rag.ingest import process_pdf_to_mongodb
from backend.rag.rag_pipeline import build_vector_store
import secrets

from backend.database.mongodb import (
    file_collection, doc_collection, user_collection,
    conversation_collection, chat_collection, activity_log_collection,
    admin_2fa_collection, admin_session_collection, contact_collection  
)

from backend.api.dependencies.auth_deps import get_current_admin
from backend.config import settings
from backend.core.security import  sanitize_filename ,get_password_hash
from backend.api.dependencies.auth_deps import *
from backend.database.repositories.user_repo import UserRepository
from backend.rag.ingest import process_pdf_to_mongodb
from backend.models.schemas import (
    DocumentInfo, DocumentUploadResponse, DocumentDeleteResponse,
    SystemStats, ActivityLog, UserResponse, AdminLoginRequest, Admin2FAVerifyRequest, CreateAdminRequest
)

from backend.api.dependencies.admin_auth import AdminAuth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/auth/login")
async def admin_login(request: Request, login_data: AdminLoginRequest):
    """Dedicated admin login endpoint with enhanced security"""
    
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")
    
    result = await AdminAuth.login_admin(
        email=login_data.email,
        password=login_data.password,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    return result


@router.post("/verify-2fa")
async def verify_2fa(request: Request, verify_data: Admin2FAVerifyRequest):
    """Verify 2FA code for admin login"""
    
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")
    
    result = await AdminAuth.verify_2fa(
        user_id=verify_data.user_id,
        code=verify_data.code,
        temp_token=verify_data.temp_token,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    return result


@router.get("/documents", response_model=List[DocumentInfo])
async def list_documents(
    current_admin: dict = Depends(get_current_admin),
    skip: int = 0,
    limit: int = 50
):
    try:
        logger.info(f"Admin {current_admin['email']} listing documents")
        
        documents = []
        cursor = file_collection.find().sort("upload_date", -1).skip(skip).limit(limit)
        
        async for doc in cursor:
            uploader = await user_collection.find_one({"user_id": doc.get("uploaded_by", "unknown")})
            uploader_name = uploader["email"] if uploader else "Unknown"
            
            documents.append(DocumentInfo(
                document_id=doc.get("document_id", ""),
                filename=doc.get("filename", "Unknown"),
                file_type=doc.get("file_type", "unknown"),
                size=doc.get("size", 0),
                upload_date=doc.get("upload_date", datetime.utcnow()),
                status=doc.get("status", "unknown"),
                chunk_count=doc.get("chunk_count", 0),
                uploaded_by=uploader_name
            ))
        
        logger.info(f"Found {len(documents)} documents")
        return documents
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_admin: dict = Depends(get_current_admin)
):
    try:
        logger.info(f"Admin {current_admin['email']} uploading file: {file.filename}")

        # -------- FILE VALIDATION --------
        # Check file extension
        allowed_extensions = ['.pdf', '.txt', '.doc', '.docx']
        filename_lower = file.filename.lower()
        ext = filename_lower.split('.')[-1]
        
        if not any(filename_lower.endswith(allowed_ext) for allowed_ext in allowed_extensions):
            raise HTTPException(
                status_code=400, 
                detail=f"File type .{ext} not allowed. Allowed types: pdf, txt, doc, docx"
            )
        
        # Check file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        
        # Basic malware check on first 1KB of file
        file_content = await file.read(1024)
        await file.seek(0)  # Reset file pointer
        
        suspicious_patterns = [
            b'<?php',
            b'<script',
            b'exec(',
            b'system(',
            b'eval(',
            b'base64_decode',
            b'passthru(',
            b'shell_exec',
            b'javascript:',
            b'onload=',
            b'onerror=',
        ]
        
        for pattern in suspicious_patterns:
            if pattern in file_content:
                raise HTTPException(
                    status_code=400, 
                    detail="File contains suspicious content and was rejected for security reasons"
                )
        
        # Generate safe filename
        import hashlib
        
        safe_filename = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}{file.filename}".encode()
        ).hexdigest()
        safe_filename = f"{safe_filename}.{ext}"
        
        # -------- FILE STORAGE --------
        document_id = str(uuid.uuid4())
        
        # Create directory if it doesn't exist
        os.makedirs("data/documents", exist_ok=True)
        
        # Use safe filename to prevent path traversal attacks
        file_path = f"data/documents/{safe_filename}"
        
        with open(file_path, "wb") as buffer:
            # Read file in chunks to avoid memory issues
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                buffer.write(chunk)
        
        logger.info(f"File saved to: {file_path}")
        
        # -------- METADATA --------
        doc_metadata = {
            "document_id": document_id,
            "filename": file.filename,  # Store original filename for display
            "safe_filename": safe_filename,  # Store safe filename for reference
            "file_path": file_path,
            "file_type": ext,
            "size": file_size,
            "upload_date": datetime.utcnow(),
            "status": "processing",
            "chunk_count": 0,
            "uploaded_by": current_admin["user_id"],
            "metadata": {}
        }
        
        await file_collection.insert_one(doc_metadata)
        logger.info(f"Document metadata saved for {document_id}")
        
        # -------- DOCUMENT PROCESSING --------
        chunk_count = 0
        
        if ext in ["pdf", "txt", "doc", "docx"]:
            try:
                # Process the document and extract chunks
                chunk_count = await process_pdf_to_mongodb(file_path, document_id)
                
                # Update document status to active
                await file_collection.update_one(
                    {"document_id": document_id},
                    {
                        "$set": {
                            "status": "active",
                            "chunk_count": chunk_count,
                            "processed_at": datetime.utcnow()
                        }
                    }
                )
                
                # Rebuild vector store with new document
                await build_vector_store()
                logger.info(f"Vector store rebuilt after uploading {file.filename} with {chunk_count} chunks")
                
            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
                
                # Update document status to failed
                await file_collection.update_one(
                    {"document_id": document_id},
                    {"$set": {"status": "failed", "error": str(e)}}
                )
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Document uploaded but processing failed: {str(e)}"
                )
        else:
            # For non-text files, just mark as active without processing
            await file_collection.update_one(
                {"document_id": document_id},
                {"$set": {"status": "active"}}
            )
            logger.info(f"Non-text file {file.filename} uploaded (no processing needed)")
        
        # -------- ACTIVITY LOG --------
        await activity_log_collection.insert_one({
            "log_id": str(uuid.uuid4()),
            "user_id": current_admin["user_id"],
            "username": current_admin["email"],
            "action": "DOCUMENT_UPLOADED",
            "details": {
                "document_id": document_id,
                "filename": file.filename,
                "file_type": ext,
                "size": file_size,
                "chunk_count": chunk_count,
                "status": "active" if ext in ["pdf", "txt", "doc", "docx"] else "active_no_processing"
            },
            "timestamp": datetime.utcnow(),
            "ip_address": None
        })
        
        logger.info(f"Document {document_id} uploaded successfully by {current_admin['email']}")
        
        return DocumentUploadResponse(
            document_id=document_id,
            filename=file.filename,
            message=f"Document uploaded successfully with {chunk_count} chunks processed" if chunk_count > 0 else "Document uploaded successfully",
            chunk_count=chunk_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        logger.info(f"Admin {current_admin['email']} deleting document: {document_id}")
        
        doc = await file_collection.find_one({"document_id": document_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        try:
            if os.path.exists(doc.get("file_path", "")):
                os.remove(doc["file_path"])
                logger.info(f"Deleted file: {doc['file_path']}")
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
        
        delete_result = await doc_collection.delete_many({
            "metadata.document_id": document_id
        })
        logger.info(f"Deleted {delete_result.deleted_count} chunks")
        
        await file_collection.delete_one({"document_id": document_id})
        
        await build_vector_store()
        logger.info("Vector store rebuilt after deletion")
        
        await activity_log_collection.insert_one({
            "log_id": str(uuid.uuid4()),
            "user_id": current_admin["user_id"],
            "username": current_admin["email"],
            "action": "DOCUMENT_DELETED",
            "details": {
                "document_id": document_id,
                "filename": doc.get("filename", "Unknown"),
                "deleted_chunks": delete_result.deleted_count
            },
            "timestamp": datetime.utcnow()
        })
        
        return DocumentDeleteResponse(
            message="Document deleted successfully",
            document_id=document_id,
            deleted_chunks=delete_result.deleted_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/documents/search")
async def search_documents(
    query: str,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        logger.info(f"Admin {current_admin['email']} searching documents with query: {query}")
        
        results = []
        
        file_cursor = file_collection.find({
            "filename": {"$regex": query, "$options": "i"}
        }).limit(10)
        
        async for doc in file_cursor:
            results.append({
                "document_id": doc.get("document_id", ""),
                "filename": doc.get("filename", "Unknown"),
                "type": "document",
                "upload_date": doc.get("upload_date", datetime.utcnow()).isoformat() if doc.get("upload_date") else None
            })
        
        chunk_cursor = doc_collection.find({
            "page_content": {"$regex": query, "$options": "i"}
        }).limit(20)
        
        async for chunk in chunk_cursor:
            metadata = chunk.get("metadata", {})
            doc_id = metadata.get("document_id")
            if doc_id:
                doc_info = await file_collection.find_one({"document_id": doc_id})
                if doc_info and not any(r.get("document_id") == doc_id for r in results):
                    results.append({
                        "document_id": doc_id,
                        "filename": doc_info.get("filename", "Unknown"),
                        "type": "content_match",
                        "snippet": chunk.get("page_content", "")[:200] + "...",
                        "upload_date": doc_info.get("upload_date", datetime.utcnow()).isoformat() if doc_info.get("upload_date") else None
                    })
        
        return results
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(current_admin: dict = Depends(get_current_admin)):
    try:
        logger.info(f"Admin {current_admin['email']} requesting system stats")
        
        total_documents = await file_collection.count_documents({})
        total_chunks = await doc_collection.count_documents({})
        
        total_users = await user_collection.count_documents({})
        
        total_conversations = await conversation_collection.count_documents({})
        total_messages = await chat_collection.count_documents({})
        
        vector_store_size = "0 MB"
        if os.path.exists("vector_store"):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk("vector_store"):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            vector_store_size = f"{total_size / (1024*1024):.2f} MB"
        
        return SystemStats(
            total_documents=total_documents,
            total_chunks=total_chunks,
            total_users=total_users,
            total_conversations=total_conversations,
            total_messages=total_messages,
            vector_store_size=vector_store_size,
            database_size="N/A"
        )
        
    except Exception as e:
        logger.error(f"Stats error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get system stats: {str(e)}")


@router.get("/users", response_model=List[UserResponse])
async def list_users(current_admin: dict = Depends(get_current_admin)):
    try:
        logger.info(f"Admin {current_admin['email']} listing users")
        
        users = []
        cursor = user_collection.find({})
        
        async for user in cursor:
            users.append(UserResponse(
                user_id=user.get("user_id", ""),
                username=user.get("username", "Unknown"),
                email=user.get("email", ""),
                role=user.get("role", "user"),
                created_at=user.get("created_at", datetime.utcnow()),
                last_login=user.get("last_login")
            ))
        
        return users
        
    except Exception as e:
        logger.error(f"List users error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        logger.info(f"Admin {current_admin['email']} deleting user: {user_id}")
        
        if user_id == current_admin["user_id"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
        user = await user_collection.find_one({"user_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        conv_result = await conversation_collection.delete_many({"user_id": user_id})
        msg_result = await chat_collection.delete_many({"user_id": user_id})
        
        result = await user_collection.delete_one({"user_id": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        await activity_log_collection.insert_one({
            "log_id": str(uuid.uuid4()),
            "user_id": current_admin["user_id"],
            "username": current_admin["email"],
            "action": "USER_DELETED",
            "details": {
                "deleted_user_id": user_id,
                "deleted_user_email": user.get("email"),
                "deleted_conversations": conv_result.deleted_count,
                "deleted_messages": msg_result.deleted_count
            },
            "timestamp": datetime.utcnow()
        })
        
        return {
            "message": "User deleted successfully",
            "deleted_conversations": conv_result.deleted_count,
            "deleted_messages": msg_result.deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.get("/logs", response_model=List[ActivityLog])
async def get_activity_logs(
    current_admin: dict = Depends(get_current_admin),
    limit: int = 100,
    skip: int = 0
):
    try:
        logger.info(f"Admin {current_admin['email']} requesting activity logs")
        
        logs = []
        cursor = activity_log_collection.find().sort("timestamp", -1).skip(skip).limit(limit)
        
        async for log in cursor:
            logs.append(ActivityLog(
                log_id=log.get("log_id", ""),
                user_id=log.get("user_id", ""),
                username=log.get("username", "System"),
                action=log.get("action", "Unknown"),
                details=log.get("details", {}),
                timestamp=log.get("timestamp", datetime.utcnow()),
                ip_address=log.get("ip_address")
            ))
        
        return logs
        
    except Exception as e:
        logger.error(f"Logs error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get activity logs: {str(e)}")


@router.get("/health")
async def admin_health_check(current_admin: dict = Depends(get_current_admin)):
    try:
        logger.info(f"Admin {current_admin['email']} requesting health check")
        
        try:
            await file_collection.count_documents({})
            mongo_status = "healthy"
        except Exception as e:
            mongo_status = f"unhealthy: {str(e)}"
        
        vector_store_status = "healthy" if os.path.exists("vector_store") else "not_built"
        
        import shutil
        disk_usage = shutil.disk_usage(".")
        free_space_gb = disk_usage.free / (1024**3)
        total_space_gb = disk_usage.total / (1024**3)
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "mongodb": mongo_status,
                "vector_store": vector_store_status,
                "api": "healthy"
            },
            "system": {
                "free_disk_space": f"{free_space_gb:.2f} GB",
                "total_disk_space": f"{total_space_gb:.2f} GB",
                "free_percentage": f"{(free_space_gb/total_space_gb*100):.1f}%",
                "python_version": os.sys.version
            }
        }
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/contacts")
async def get_contact_messages(current_admin: dict = Depends(get_current_admin)):
    """Get all contact messages (admin only)"""
    try:
        messages = []
        # Query contact_messages collection using the imported contact_collection
        cursor = contact_collection.find().sort("submitted_at", -1)
        async for msg in cursor:
            messages.append({
                "message_id": msg.get("message_id"),
                "name": msg.get("name"),
                "email": msg.get("email"),
                "subject": msg.get("subject"),
                "message": msg.get("message"),
                "status": msg.get("status", "pending"),
                "submitted_at": msg.get("submitted_at"),
                "replied_at": msg.get("replied_at"),
                "admin_reply": msg.get("admin_reply")
            })
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Get contacts error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/create-admin")
async def create_admin_endpoint(request: CreateAdminRequest):
    """
    Create admin user via API (requires admin_secret)
    """
    # Verify admin secret key (store this in environment variables)
    ADMIN_CREATION_SECRET = os.getenv("ADMIN_CREATION_SECRET", "your-super-secret-key-change-this")
    
    if request.admin_secret != ADMIN_CREATION_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    # Check if user already exists
    existing_user = await user_collection.find_one({
        "$or": [
            {"email": request.email.lower()},
            {"username": request.username}
        ]
    })
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create admin user
    user_id = secrets.token_urlsafe(16)
    hashed_password = get_password_hash(request.password)
    
    admin_user = {
        "user_id": user_id,
        "username": request.username,
        "email": request.email.lower(),
        "hashed_password": hashed_password,
        "role": "admin",
        "created_at": datetime.utcnow(),
        "is_active": True,
        "is_verified": True,
        "failed_login_attempts": 0,
        "last_login": None
    }
    
    await user_collection.insert_one(admin_user)
    
    return {
        "message": "Admin user created successfully",
        "user_id": user_id,
        "email": request.email,
        "username": request.username
    }