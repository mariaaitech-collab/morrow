"""SaaS activity history for the logged-in user (Firestore).

History exclusively tracks product usage: AI images, competitive analyses,
AI captions, scheduled posts. Auth events are never recorded.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pydantic import BaseModel

import firebase_db
from firebase_db import FieldFilter
from config import SECRET_KEY, ALGORITHM
from models import UserProfileUpdate

router = APIRouter(prefix="/api/user", tags=["user"])
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")

    email = payload.get("sub")
    user = await firebase_db.user_by_email(email) if email else None
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    from deps import apply_dev_override
    return await apply_dev_override(user)


def _iso_utc(dt):
    if dt is None:
        return None
    from deps import _coerce_dt
    dt = _coerce_dt(dt)
    return dt.isoformat() if dt else None


def _profile(user):
    profile = user.get("profile") or {}
    return {
        "business_name": profile.get("business_name", ""),
        "business_type": profile.get("business_type", ""),
        "industry": profile.get("industry", ""),
        "bio": profile.get("bio", ""),
        "website": profile.get("website", ""),
        "location": profile.get("location", ""),
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "created_at": _iso_utc(user.get("created_at")),
        "free_tokens": int(user.get("free_tokens", 0)),
        "is_pro": bool(user.get("subscribed")),
        "profile": _profile(user),
    }


@router.patch("/profile")
async def update_profile(payload: UserProfileUpdate, user=Depends(get_current_user)):
    profile = payload.model_dump()
    await firebase_db.users.document(user["id"]).update({"profile": profile})
    return {"profile": profile, "message": "Profile updated."}


def _own_history(user):
    return firebase_db.activities.where(filter=FieldFilter("user_id", "==", user["id"]))


@router.get("/history")
async def get_history(user=Depends(get_current_user)):
    query = _own_history(user).order_by("created_at", direction=firebase_db.DESCENDING).limit(200)
    items = []
    for doc in await firebase_db.fetch(query):
        items.append({
            "id": doc["id"],
            "type": doc.get("type", "event"),
            "title": doc.get("title", ""),
            "detail": doc.get("detail", ""),
            "created_at": _iso_utc(doc.get("created_at")),
        })
    return {"items": items, "count": len(items)}


class HistoryDeleteRequest(BaseModel):
    record_ids: list[str] | None = None
    clear_all: bool = False


@router.delete("/history")
async def clear_history(payload: HistoryDeleteRequest, user=Depends(get_current_user)):
    """Delete specific history records, or wipe everything for this user."""
    if payload.clear_all:
        deleted = await firebase_db.delete_where(_own_history(user))
        print(f"[HISTORY] Cleared {deleted} records for {user.get('email')}")
        return {"message": "History cleared.", "deleted_count": deleted}

    # Malformed ids are ignored rather than failing the whole request.
    valid_ids = [rid for rid in (payload.record_ids or []) if firebase_db.valid_id(rid)]
    if not valid_ids:
        return {"message": "No valid records specified.", "deleted_count": 0}

    docs = await firebase_db.get_many(firebase_db.activities, valid_ids)
    deleted = await firebase_db.delete_refs(
        firebase_db.activities.document(d["id"]) for d in docs if d.get("user_id") == user["id"]
    )
    print(f"[HISTORY] Deleted {deleted} record(s) for {user.get('email')}")
    return {"message": "Records deleted.", "deleted_count": deleted}