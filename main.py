# main.py - Most flexible version
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os

from backend.config import settings
from backend.database.mongodb import init_database
from backend.api.routes import auth, chat, conversations, admin, health, contact
from backend.core.middleware.security import SecurityHeadersMiddleware
from backend.core.middleware.logging import RequestLoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    try:
        await init_database()
        logger.info("🚀 Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Lifespan initialization failed: {e}")
    yield


def create_app() -> FastAPI:
    """Application factory pattern"""
    app = FastAPI(
        title="NU AI Assistant API",
        version="2.0.0",
        description="Production-ready AI Assistant API",
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
        expose_headers=["Content-Length", "X-Total-Count"],
        max_age=600,
    )
    
    # ========== SERVE FRONTEND ==========
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    
    if os.path.exists(frontend_dir):
        # This catch-all route will handle both /css/file.css AND /frontend/css/file.css
        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            # Remove /frontend/ prefix if present
            if path.startswith("frontend/"):
                path = path[9:]  # Remove 'frontend/' prefix
            
            file_path = os.path.join(frontend_dir, path)
            
            # If file exists, serve it
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
            
            # If path is empty or points to directory, serve index.html
            if not path or path.endswith('/'):
                index_path = os.path.join(frontend_dir, "index.html")
                if os.path.exists(index_path):
                    return FileResponse(index_path)
            
            # For API routes, let them handle the request
            if path.startswith("api/"):
                return {"error": "API route not found"}, 404
            
            # Try to serve as HTML file
            html_path = os.path.join(frontend_dir, f"{path}.html")
            if os.path.exists(html_path):
                return FileResponse(html_path)
            
            return {"error": f"File '{path}' not found"}, 404
        
        logger.info(f"✅ Frontend serving from: {frontend_dir}")
    
    # Include routers (API routes) - MUST be after the catch-all route
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(admin.router)
    app.include_router(contact.router)
    
    return app


app = create_app()