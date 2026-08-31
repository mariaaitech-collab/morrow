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
