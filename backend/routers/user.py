"""SaaS activity history for the logged-in user (MongoDB).

History exclusively tracks product usage: AI images, competitive analyses,
AI captions, scheduled posts. Auth events are never recorded.
"""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pydantic import BaseModel

import mongodb
from config import SECRET_KEY, ALGORITHM

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
    user = await mongodb.users.find_one({"email": email}) if email else None
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return user


def _iso_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        from config import utc_now

        dt = dt.replace(tzinfo=utc_now().tzinfo)
    return dt.isoformat()


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": str(user["_id"]),
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "created_at": _iso_utc(user.get("created_at")),
    }


@router.get("/history")
async def get_history(user=Depends(get_current_user)):
    cursor = (
        mongodb.activities
        .find({"user_id": user["_id"]})
        .sort("created_at", -1)
        .limit(200)
    )
    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
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
        result = await mongodb.activities.delete_many({"user_id": user["_id"]})
        print(f"[HISTORY] Cleared {result.deleted_count} records for {user.get('email')}")
        return {"message": "History cleared.", "deleted_count": result.deleted_count}

    raw_ids = payload.record_ids or []
    valid_ids = []
    for rid in raw_ids:
        try:
            valid_ids.append(ObjectId(rid))
        except Exception:
            # Ignore malformed ids rather than failing the whole request.
            continue

    if not valid_ids:
        return {"message": "No valid records specified.", "deleted_count": 0}

    result = await mongodb.activities.delete_many(
        {"_id": {"$in": valid_ids}, "user_id": user["_id"]}
    )
    print(f"[HISTORY] Deleted {result.deleted_count} record(s) for {user.get('email')}")
    return {"message": "Records deleted.", "deleted_count": result.deleted_count}