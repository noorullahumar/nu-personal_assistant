from itsdangerous import URLSafeTimedSerializer
import os
from dotenv import load_dotenv
import re
import html

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT", "password-reset-salt")

def generate_reset_token(email: str) -> str:
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps(email, salt=SECURITY_PASSWORD_SALT)

def verify_reset_token(token: str, expiration: int = 3600) -> str | None:
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    try:
        email = serializer.loads(
            token,
            salt=SECURITY_PASSWORD_SALT,
            max_age=expiration
        )
        return email
    except Exception:
        return None
    
# ========== HELPER FUNCTIONS ==========
def sanitize_input(text: str) -> str:
    """Sanitize user input before processing"""
    if not text:
        return text
    
    # Remove potential injection patterns
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    text = html.escape(text)
    
    # Limit length
    if len(text) > 2000:
        text = text[:2000]
    
    return text


def sanitize_output(text: str) -> str:
    """Sanitize LLM output before sending to client"""
    if not text:
        return text
    return html.escape(text)
