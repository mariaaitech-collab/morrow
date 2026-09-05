import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "brandora-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
TOKEN_EXPIRE_DAYS = 7

# Password-reset tokens are short-lived (15 minutes) to limit abuse window.
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "15"))

# MongoDB (users + SaaS activity history)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "brandora")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Production deployments often run on a different domain than the local dev setup.
# Keep localhost support for local development, but allow server-side overrides
# via environment variables for hosted frontends/backends.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in (os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
)

# Administrator account that can manually approve Pro activations.
# This is the ONLY account that may access the /admin panel and admin routes.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "maria.ai.tech@gmail.com").strip().lower()

# SMTP for password-recovery emails (Gmail by default)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
# Accept both common env-var naming conventions for the credentials.
# .strip() guards against stray spaces (e.g. an app password pasted with
# spaces) that would otherwise cause Gmail to reject authentication.
SMTP_USER = (os.getenv("SMTP_USER", "") or os.getenv("SMTP_USERNAME", "")).strip()
SMTP_PASS = (os.getenv("SMTP_PASS", "") or os.getenv("SMTP_PASSWORD", "")).strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()

def utc_now():
    return datetime.now(timezone.utc)

FACEBOOK_CLIENT_ID = os.getenv("FACEBOOK_CLIENT_ID", "")
FACEBOOK_CLIENT_SECRET = os.getenv("FACEBOOK_CLIENT_SECRET", "")
FACEBOOK_REDIRECT_URI = os.getenv("FACEBOOK_REDIRECT_URI", "http://localhost:5173/auth/callback/facebook")

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:5173/auth/callback/linkedin")

INSTAGRAM_CLIENT_ID = os.getenv("INSTAGRAM_CLIENT_ID", "")
INSTAGRAM_CLIENT_SECRET = os.getenv("INSTAGRAM_CLIENT_SECRET", "")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "http://localhost:5173/auth/callback/instagram")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
