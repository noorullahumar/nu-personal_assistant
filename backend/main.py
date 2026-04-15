# backend/main.py
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


app = FastAPI(
    title="NU AI Assistant API",
    version="2.0.0",
    description="Production-ready AI Assistant API",
    lifespan=lifespan
)

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

# ========== API ROUTES ==========
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(admin.router)
app.include_router(contact.router)

# ========== SERVE FRONTEND ==========
# Get the absolute path to frontend directory
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(os.path.dirname(current_dir), "frontend")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


# Check if index.html exists
index_path = os.path.join(frontend_dir, "index.html")

if os.path.exists(frontend_dir) and os.path.exists(index_path):
    # Mount static files
    css_dir = os.path.join(frontend_dir, "css")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    
    js_dir = os.path.join(frontend_dir, "js")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    
    # Root route - serve index.html
    @app.get("/")
    async def root():
        print(f"Serving index.html from: {index_path}")
        return FileResponse(index_path)
    
    # HTML pages
    @app.get("/{page_name}")
    async def serve_html_pages(page_name: str):
        if page_name.endswith('.html'):
            file_path = os.path.join(frontend_dir, page_name)
        else:
            file_path = os.path.join(frontend_dir, f"{page_name}.html")
        
        if os.path.exists(file_path):
            return FileResponse(file_path)
        return {"error": "Page not found"}, 404
    
    print("✅ Frontend routes configured")
else:
    print("❌ Frontend directory or index.html not found!")
    
    @app.get("/")
    async def root():
        return {
            "message": "NU AI Assistant API",
            "version": "2.0.0",
            "status": "running",
            "docs": "/docs",
            "frontend_path": frontend_dir,
            "index_exists": os.path.exists(index_path)
        }