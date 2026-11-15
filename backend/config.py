import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def _required_url(name: str) -> str:
    value = os.getenv(name, "").strip().rstrip("/")
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to backend/.env (see .env.example).")
    return value


# Where the app runs. Every other URL the backend needs (OAuth redirect URIs,
# where users land after connecting a channel, CORS) is built from these two,
# so moving to another port or domain is a .env change, never a code change.
#   APP_BASE_URL  the frontend users open (the Vite dev server, which proxies /api)
#   API_BASE_URL  this backend itself
APP_BASE_URL = _required_url("APP_BASE_URL")
API_BASE_URL = _required_url("API_BASE_URL")

_DEFAULT_SECRET = "brandora-secret-key-change-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
# A publicly known signing key lets anyone forge a session for any account.
SECRET_KEY_IS_DEFAULT = SECRET_KEY == _DEFAULT_SECRET
if SECRET_KEY_IS_DEFAULT:
    print(
        "[SECURITY] CRITICAL: SECRET_KEY is the built-in default. Anyone who has "
        "read the source can forge login tokens for ANY account. Set a long "
        "random SECRET_KEY in backend/.env before exposing this server."
    )
    if urlparse(APP_BASE_URL).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Refusing to start with the built-in SECRET_KEY on a non-local APP_BASE_URL.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
TOKEN_EXPIRE_DAYS = 7

# Password-reset tokens are short-lived (15 minutes) to limit abuse window.
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "15"))

# Firebase Firestore uses Application Default Credentials (see firebase_db.py).
FIREBASE_PROJECT_ID = (
    os.getenv("FIREBASE_PROJECT_ID", "").strip()
    or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    or "morrow-2916d"
)
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "").strip()

# Where users land after login/connect flows. Defaults to the app itself.
FRONTEND_URL = (os.getenv("FRONTEND_URL", "").strip() or APP_BASE_URL).rstrip("/")

# The browser normally reaches the API through Vite's /api proxy (same origin),
# so CORS only matters for direct calls. Allow the app's own origin, plus its
# 127.0.0.1 twin when it runs on localhost. CORS_ORIGINS in .env overrides this.
DEFAULT_CORS_ORIGINS = ",".join(dict.fromkeys(
    [APP_BASE_URL]
    + ([APP_BASE_URL.replace("://localhost", "://127.0.0.1", 1)] if urlparse(APP_BASE_URL).hostname == "localhost" else [])
))
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in (os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
)
if "*" in CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS must list explicit origins when credentialed CORS is enabled.")

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
# Meta / LinkedIn send the user back to the frontend route /auth/callback/<platform>
# (pages/Callback.jsx), which hands the code to /api/social/callback/<platform>.
# The token exchange reuses these same values, so they must match the dashboards.
FACEBOOK_REDIRECT_URI = os.getenv("FACEBOOK_REDIRECT_URI", "").strip() or f"{APP_BASE_URL}/auth/callback/facebook"

# Meta Graph API version used by every Facebook / Instagram call. Bump it here
# (or via env) when Meta retires a version.
META_API_VERSION = os.getenv("META_API_VERSION", "v26.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{META_API_VERSION}"
GRAPH_VIDEO_BASE = f"https://graph-video.facebook.com/{META_API_VERSION}"
RUPLOAD_BASE = f"https://rupload.facebook.com/ig-api-upload/{META_API_VERSION}"
FB_OAUTH_DIALOG = f"https://www.facebook.com/{META_API_VERSION}/dialog/oauth"

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "").strip() or f"{APP_BASE_URL}/auth/callback/linkedin"

INSTAGRAM_CLIENT_ID = os.getenv("INSTAGRAM_CLIENT_ID", "")
INSTAGRAM_CLIENT_SECRET = os.getenv("INSTAGRAM_CLIENT_SECRET", "")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "").strip() or f"{APP_BASE_URL}/auth/callback/instagram"

# TikTok (Content Posting API). TikTok calls the app id the "Client Key".
# The callback is handled server-side by routers/auth.py (unlike FB/LI/IG which
# bounce through the frontend Callback page), so the redirect_uri points at
# this backend's /api/auth/tiktok/callback route. It has no default on purpose:
# it must match the TikTok portal byte for byte, so it only ever comes from the
# environment, and TikTok connect stays disabled until it is set.
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "").strip()
TIKTOK_SCOPES = os.getenv("TIKTOK_SCOPES", "user.info.basic,video.upload,video.publish").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# AI image generation (see image_provider.py). pollinations | none.
IMAGE_PROVIDER = (os.getenv("IMAGE_PROVIDER") or "pollinations").strip().lower()
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "").strip()
# Drawn bottom-right on every AI-generated image (watermark.py). Empty = no watermark.
WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "Morrow").strip()

# ---------------------------------------------------------------------------
# AI Auto-Responder: webhooks + engagement
# ---------------------------------------------------------------------------
# Public base URL of THIS backend, used to show the exact webhook callback URLs
# in the dashboard. Defaults to API_BASE_URL. Platforms only deliver webhooks to
# a public https URL, so while this is localhost no webhooks arrive (Meta comment
# polling still works).
PUBLIC_BACKEND_URL = (os.getenv("PUBLIC_BACKEND_URL", "").strip() or API_BASE_URL).rstrip("/")

# Meta (Facebook + Instagram) webhook verification. The verify token is any
# secret string you also type into the Meta App Dashboard. The app secret
# signs every POST (X-Hub-Signature-256) and defaults to the FB app secret.
META_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "").strip()
META_APP_SECRET = (os.getenv("META_APP_SECRET", "") or FACEBOOK_CLIENT_SECRET).strip()
INSTAGRAM_APP_SECRET = (os.getenv("INSTAGRAM_APP_SECRET", "") or INSTAGRAM_CLIENT_SECRET or META_APP_SECRET).strip()

# Extra OAuth scopes Meta needs to READ and REPLY to comments / DMs. Leave the
# default for apps in Development mode; set to an empty string if your Live
# app has not been approved for these permissions yet.
META_ENGAGEMENT_SCOPES = os.getenv(
    "META_ENGAGEMENT_SCOPES",
    "pages_manage_metadata,pages_messaging,instagram_manage_comments,instagram_manage_messages",
).strip()

# Reject unsigned / badly signed webhook POSTs. Only disable for local testing.
WEBHOOK_REQUIRE_SIGNATURE = os.getenv("WEBHOOK_REQUIRE_SIGNATURE", "true").strip().lower() not in ("0", "false", "no")

# Rule-based responder (rule_matcher.py). Similarity is 0-100 (rapidfuzz ratio).
RESPONDER_FUZZY_CUTOFF = min(100, max(50, int(os.getenv("RESPONDER_FUZZY_CUTOFF", "85") or 85)))
# A keyword match needs this many hits, or one hit on a keyword of at least
# RESPONDER_STRONG_KEYWORD_LEN characters ("longer than 5" = 6).
RESPONDER_MIN_KEYWORD_HITS = max(1, int(os.getenv("RESPONDER_MIN_KEYWORD_HITS", "2") or 2))
RESPONDER_STRONG_KEYWORD_LEN = max(1, int(os.getenv("RESPONDER_STRONG_KEYWORD_LEN", "6") or 6))
# Flood protection: automatic replies per workspace per hour. Beyond it, new
# comments wait in "Needs your attention" with their reply ready.
RESPONDER_HOURLY_REPLY_LIMIT = max(1, int(os.getenv("RESPONDER_HOURLY_REPLY_LIMIT", "200") or 200))

# Platforms the AI Responder works on (comma-separated). This is the one place
# that decides it: the API, webhooks, channel health and the AI Responder page
# all read it. Comments from any other platform are logged and ignored.
# Connecting and publishing are not affected.
RESPONDER_ALL_PLATFORMS = ("facebook", "instagram", "linkedin", "tiktok")
_responder_requested = [p.strip().lower() for p in os.getenv("RESPONDER_PLATFORMS", "facebook,instagram").split(",") if p.strip()]
RESPONDER_PLATFORMS = tuple(p for p in RESPONDER_ALL_PLATFORMS if p in _responder_requested)
RESPONDER_PLATFORMS_UNKNOWN = tuple(p for p in _responder_requested if p not in RESPONDER_ALL_PLATFORMS)

# Polling fallback for Meta comments (meta_poller.py). Development-mode Meta apps
# get no real comment webhooks, so the backend polls the Graph API instead.
# Set to false once the app is Live and webhooks arrive.
META_POLLING_ENABLED = os.getenv("META_POLLING_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
META_POLL_INTERVAL = max(15, int(os.getenv("META_POLL_INTERVAL", "30") or 30))
