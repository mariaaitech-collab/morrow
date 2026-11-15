"""Shared security primitives: password hashing and brute-force protection."""
import time
from collections import defaultdict, deque

from fastapi import Request, HTTPException
from passlib.context import CryptContext

# ---- Password hashing (passlib bcrypt) ----
# All hashing/verification goes through here so we never store plaintext
# and legacy bcrypt hashes (from the previous direct-bcrypt scheme) still verify.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


# ---- In-memory sliding-window rate limiter ----
# Protects against credential brute-force and password-reset email spam.
# (Per-process; sufficient for a single-instance deployment. For multi-instance,
#  back this with Redis.)
class RateLimiter:
    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        dq = self.hits[key]
        while dq and dq[0] <= now - self.seconds:
            dq.popleft()
        if len(dq) >= self.times:
            return False
        dq.append(now)
        return True


login_limiter = RateLimiter(times=10, seconds=60)    # 10 logins / minute / IP
forgot_limiter = RateLimiter(times=5, seconds=300)  # 5 reset emails / 5 min / IP


async def login_rate_limit(request: Request):
    if not login_limiter.is_allowed(f"login:{request.client.host}"):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait a minute and try again.",
        )


async def forgot_rate_limit(request: Request):
    if not forgot_limiter.is_allowed(f"forgot:{request.client.host}"):
        raise HTTPException(
            status_code=429,
            detail="Too many password-reset requests. Please wait a few minutes and try again.",
        )


signup_limiter = RateLimiter(times=10, seconds=3600)  # 10 new accounts / hour / IP
reset_limiter = RateLimiter(times=10, seconds=900)    # 10 reset submissions / 15 min / IP


async def signup_rate_limit(request: Request):
    if not signup_limiter.is_allowed(f"signup:{request.client.host}"):
        raise HTTPException(
            status_code=429,
            detail="Too many accounts created from this address. Please try again later.",
        )


async def reset_rate_limit(request: Request):
    if not reset_limiter.is_allowed(f"reset:{request.client.host}"):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait a few minutes and try again.",
        )


# ---- Whole-API protection layers (wired up in main.py) ----
# Starlette BaseHTTPMiddleware wraps every request; all three layers are
# deliberately simple and dependency-free.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Global flood guard. Generous enough for the UI (which polls a few endpoints
# every 30-60s) yet it stops dumb scraping/DoS loops from a single address.
GLOBAL_RATE = RateLimiter(times=300, seconds=60)  # 300 requests / minute / IP

# The largest legitimate request body is a TikTok video upload
# (media_rules.MAX_VIDEO_BYTES = 1 GiB); everything beyond that is junk.
MAX_BODY_BYTES = 1100 * 1024 * 1024


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # CORS preflights are cheap and browser-initiated: never throttle them.
        if request.method != "OPTIONS":
            host = request.client.host if request.client else "?"
            if not GLOBAL_RATE.is_allowed(f"any:{host}"):
                return JSONResponse(
                    {"detail": "Too many requests. Please slow down and try again shortly."},
                    status_code=429,
                    headers={"Retry-After": "30"},
                )
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defence-in-depth response headers on every API response.

    The backend serves JSON and uploaded media, never HTML pages, so the CSP
    can be maximally strict without affecting the React app (which is served
    by Vite / the static host, not by this process).
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "cross-origin")  # /uploads images are embedded by platforms
        # Only meaningful over TLS; harmless otherwise, so gate it on the scheme
        # (a reverse proxy terminates TLS and sets X-Forwarded-Proto).
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
