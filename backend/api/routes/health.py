from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "NU AI Assistant API",
        "version": "2.0.0"
    }

@router.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "NU AI Assistant API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }