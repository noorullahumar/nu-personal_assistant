# middleware/csrf.py
from fastapi import Request, HTTPException

async def verify_csrf(request: Request):
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        csrf_token = request.headers.get("X-CSRF-Token")
        session_token = request.cookies.get("csrf_token")
        if not csrf_token or csrf_token != session_token:
            raise HTTPException(403, "Invalid CSRF token")