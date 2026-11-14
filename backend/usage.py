"""Optional-auth + SaaS usage history helpers.

History exclusively tracks product usage (AI images, competitive analyses,
content generation, scheduled posts) — never auth events.
"""
from fastapi import Request
from jose import jwt, JWTError

import firebase_db
from config import SECRET_KEY, ALGORITHM, utc_now


def _decode(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_optional_user(request: Request):
    """Resolve the logged-in user from the Authorization header, or None.

    Never raises — lets public endpoints keep working for anonymous visitors
    while still attributing history to signed-in users.
    """
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    payload = _decode(auth.split(" ", 1)[1].strip())
    if not payload:
        return None

    email = payload.get("sub")
    if not email:
        return None
    return await firebase_db.user_by_email(email)


async def record_usage(user, type_: str, title: str, detail: str = ""):
    """Best-effort history write — logging failures must never break a feature."""
    if not user:
        return
    try:
        await firebase_db.activities.add({
            "user_id": user["id"],
            "type": type_,
            "title": title,
            "detail": detail,
            "created_at": utc_now(),
        })
    except Exception as e:
        print(f"[HISTORY] Failed to record '{type_}': {e}")
