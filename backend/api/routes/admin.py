from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from typing import List
import os
import shutil
import uuid
from datetime import datetime
import logging
from backend.rag.ingest import process_pdf_to_mongodb
from backend.rag.rag_pipeline import build_vector_store
import re
import magic
import hashlib
from typing import List



from backend.database.mongodb import (
    file_collection, doc_collection, user_collection,
    conversation_collection, chat_collection, activity_log_collection,
    admin_2fa_collection, admin_session_collection
)

from backend.config import settings
from backend.core.security import sanitize_filename
from backend.api.dependencies.auth_deps import *
from backend.database.repositories.user_repo import UserRepository
from backend.rag.ingest import process_pdf_to_mongodb
from backend.models.schemas import (
    DocumentInfo, DocumentUploadResponse, DocumentDeleteResponse,
    SystemStats, ActivityLog, UserResponse, AdminLoginRequest, Admin2FAVerifyRequest
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
        cursor = file_collection.find().sort("upload_date").skip(skip).limit(limit)
        
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

        # 1. READ INITIAL BYTES FOR VALIDATION
        # We read the first 2KB for both MIME check and suspicious pattern check
        header_content = await file.read(2048)
        
        # 2. MIME TYPE VALIDATION (Content-based)
        mime = magic.from_buffer(header_content, mime=True)
        allowed_mimes = [
            'application/pdf', 
            'text/plain', 
            'image/png', 
            'image/jpeg',
            'application/msword', 
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]
        
        if mime not in allowed_mimes:
            raise HTTPException(status_code=400, detail=f"Invalid file content type: {mime}")

        # 3. EXTENSION & SUSPICIOUS PATTERN VALIDATION
        allowed_extensions = ['.pdf', '.txt', '.doc', '.docx', '.png', '.jpg', '.jpeg']
        filename = file.filename.lower()
        ext = filename.split('.')[-1]
        
        if not any(filename.endswith(allowed_ext) for allowed_ext in allowed_extensions):
            raise HTTPException(
                status_code=400, 
                detail=f"File extension .{ext} not allowed."
            )

        suspicious_patterns = [
            b'<?php', b'<script', b'exec(', b'system(', b'eval(', 
            b'base64_decode', b'passthru(', b'shell_exec', 
            b'javascript:', b'onload=', b'onerror='
        ]
        
        for pattern in suspicious_patterns:
            if pattern in header_content:
                raise HTTPException(
                    status_code=400, 
                    detail="File contains suspicious code patterns."
                )

        # 4. FILE SIZE VALIDATION
        # Move to end to check size, then reset
        await file.seek(0, os.SEEK_END)
        file_size = await file.tell()
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")

        # IMPORTANT: Reset pointer to start before saving
        await file.seek(0)

        # 5. GENERATE SAFE FILENAME
        safe_filename = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}{file.filename}".encode()
        ).hexdigest()
        safe_filename = f"{safe_filename}.{ext}"
        
        # 6. FILE STORAGE
        document_id = str(uuid.uuid4())
        os.makedirs("data/documents", exist_ok=True)
        file_path = f"data/documents/{safe_filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 7. METADATA PERSISTENCE
        doc_metadata = {
            "document_id": document_id,
            "filename": file.filename,
            "safe_filename": safe_filename,
            "file_path": file_path,
            "file_type": ext,
            "size": file_size,
            "upload_date": datetime.utcnow(),
            "status": "processing",
            "chunk_count": 0,
            "uploaded_by": current_admin["user_id"],
        }
        await file_collection.insert_one(doc_metadata)

        # 8. DOCUMENT PROCESSING (PDF/Text)
        chunk_count = 0
        if ext in ["pdf", "txt", "doc", "docx"]:
            try:
                chunk_count = await process_pdf_to_mongodb(file_path, document_id)
                await file_collection.update_one(
                    {"document_id": document_id},
                    {"$set": {"status": "active", "chunk_count": chunk_count, "processed_at": datetime.utcnow()}}
                )
                await build_vector_store()
            except Exception as e:
                logger.error(f"Processing failed: {e}")
                await file_collection.update_one(
                    {"document_id": document_id},
                    {"$set": {"status": "failed", "error": str(e)}}
                )
                raise HTTPException(status_code=500, detail="Processing failed")
        else:
            await file_collection.update_one(
                {"document_id": document_id},
                {"$set": {"status": "active"}}
            )

        # 9. ACTIVITY LOGGING
        await activity_log_collection.insert_one({
            "log_id": str(uuid.uuid4()),
            "user_id": current_admin["user_id"],
            "action": "DOCUMENT_UPLOADED",
            "details": {"document_id": document_id, "filename": file.filename},
            "timestamp": datetime.utcnow()
        })
        
        return DocumentUploadResponse(
            document_id=document_id,
            filename=file.filename,
            message=f"Success! {chunk_count} chunks processed." if chunk_count > 0 else "Upload successful.",
            chunk_count=chunk_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
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
        

        safe_query = re.escape(query)  # Escape regex special characters
        file_cursor = file_collection.find({
            "filename": {"$regex": safe_query, "$options": "i"}
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
        cursor = activity_log_collection.find().sort("timestamp").skip(skip).limit(limit)
        
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
        # For demo: read from localStorage equivalent
        # In production, store in MongoDB
        messages = []
        # You can store contacts in MongoDB instead of localStorage
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))