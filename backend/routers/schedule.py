"""Auto Posting & Weekly Scheduling module.

Persists scheduled posts in SQLite and provides a background job (APScheduler,
run every 60 seconds) that publishes due posts through the existing Cloudinary +
Meta pipeline from routers/content.py.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from bson import ObjectId

from db import ScheduledPost, SessionLocal
import mongodb
from config import utc_now
from usage import get_optional_user, record_usage
from deps import get_current_user, require_subscription
from routers.content import (
    _boosted_ai_prompt,
    _detect_media_type,
    _generate_post_content,
    _generate_pollinations_image,
    _post_to_facebook,
    _post_to_instagram,
    _post_to_linkedin,
    _upload_to_cloudinary,
)
from routers.social import connected_accounts

logger = logging.getLogger("brandora")

router = APIRouter(prefix="/api", tags=["schedule"])

# Keeps references to in-flight publish tasks alive so they are not garbage-collected.
_active_tasks = set()

VALID_PLATFORMS = {"facebook", "instagram", "linkedin"}


def _to_utc_naive(value):
    """Normalize any user supplied datetime to a naive datetime in UTC for storage."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_scheduled_at(value: str):
    """Parse a timezone-aware ISO string (with or without 'Z') into naive UTC.

    Accepts the exact output of JS `Date.toISOString()` (e.g.
    '2026-08-20T14:01:00.000Z') as well as offsets like '+02:00' or naive input
    (treated as UTC). Returns naive UTC datetime.
    """
    text = value.strip()
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        # Fallback: some clients send seconds-less or space-separated forms
        try:
            parsed = datetime.fromisoformat(normalized.replace(" ", "T"))
        except ValueError:
            raise HTTPException(status_code=400, detail="scheduled_at must be a valid ISO datetime (e.g. 2026-08-20T10:30:00)")
    return _to_utc_naive(parsed)


def _utc_iso(dt):
    """Serialize a datetime as UTC ISO 8601 (with tz info) so clients parse it correctly."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize(post):
    return {
        "id": post.id,
        "scheduled_at": _utc_iso(post.scheduled_at),
        "platforms": json.loads(post.platforms),
        "content": post.content,
        "media_url": post.media_url,
        "media_type": post.media_type,
        "status": post.status,
        "result": post.result,
        "created_at": _utc_iso(post.created_at),
        "recurrence": getattr(post, "recurrence", "none") or "none",
        "recurrence_end": _utc_iso(getattr(post, "recurrence_end", None)),
        "recurring": bool(getattr(post, "recurring", False)),
        "created_by": getattr(post, "created_by", None),
    }


def _get_session():
    return SessionLocal()


@router.post("/schedule")
async def create_scheduled_post(
    request: Request,
    user: dict = Depends(require_subscription),
    scheduled_at: str = Form(...),
    platforms: str = Form(...),
    content: str = Form(...),
    ai_prompt: str = Form(""),
    media: UploadFile = File(None),
):
    """Create a scheduled post.

    Two media options:
      - Option A (Upload): attach an existing image/video file.
      - Option B (AI Generation): provide an ai_prompt. The image is generated
        immediately (via Pollinations), uploaded to Cloudinary, and its URL is
        stored so posting time only needs the existing publish pipeline.
    """
    try:
        dt_utc = _parse_scheduled_at(scheduled_at)
    except HTTPException:
        raise

    if dt_utc < datetime.utcnow() - timedelta(seconds=60):
        raise HTTPException(
            status_code=400,
            detail="Scheduled time must be at least 1 minute in the future",
        )

    try:
        platform_list = json.loads(platforms)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["facebook","instagram"]')

    if not isinstance(platform_list, list) or not platform_list:
        raise HTTPException(status_code=400, detail="Select at least one platform")

    invalid = [p for p in platform_list if p not in VALID_PLATFORMS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported platform(s): {', '.join(invalid)}")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Content/topic is required")

    # Auto-generate a fully formatted, engaging caption (hashtags + emojis) from
    # the user's topic/prompt using the existing Gemini text-generation logic.
    # The generated caption is what actually gets published — never the raw topic.
    try:
        generated = await _generate_post_content(content.strip(), tone="viral")
        caption = generated.get("body") or content.strip()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Scheduled caption generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI caption generation failed: {str(e)}")

    print(f"[SCHEDULER] Generated AI caption for topic '{content.strip()[:60]}' -> {len(caption)} chars")

    media_url = None
    media_type = None

    if (ai_prompt or "").strip():
        # Option B — pre-generate the AI image NOW and save its Cloudinary URL
        try:
            prompt = _boosted_ai_prompt(ai_prompt.strip())
            img_bytes, mime = await _generate_pollinations_image(prompt, 1080, 1080)
            media_type = "image"
            filename = f"scheduled_ai_{int(time.time() * 1000)}.jpg"
            media_url = await _upload_to_cloudinary(img_bytes, filename, "image")
        except Exception as e:
            logger.error("Scheduled AI image pre-generation failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"AI image generation/upload failed: {str(e)}")

    elif media and media.filename:
        # Option A — upload the attached file now so the publish step is only a URL
        file_bytes = await media.read()
        media_type = _detect_media_type(media.filename, media.content_type or "")
        try:
            media_url = await _upload_to_cloudinary(file_bytes, media.filename, media_type)
        except Exception as e:
            logger.error("Scheduled media upload failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Media upload failed: {str(e)}")

    session = _get_session()
    try:
        post = ScheduledPost(
            scheduled_at=dt_utc,
            platforms=json.dumps(platform_list),
            content=caption,
            media_url=media_url,
            media_type=media_type,
            status="pending",
            created_by=user["email"],
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        print(f"[SCHEDULER] Saved scheduled post #{post.id} at {post.scheduled_at} UTC for {platform_list}")

        media_note = "with an AI-generated image" if (ai_prompt or "").strip() else ("with uploaded media" if media_url else "(text-only)")
        for plat in platform_list:
            await record_usage(
                user,
                "scheduled_post",
                f"Scheduled a post for {plat.capitalize()}",
                f"{media_note} · goes live {dt_utc.isoformat()} UTC",
            )

        return _serialize(post)
    finally:
        session.close()


@router.get("/schedule")
async def list_scheduled_posts(request: Request):
    """Return scheduled posts ordered by time. Scoped to the logged-in user
    when authenticated (the publish engine still tags every post with its
    owner, so multi-tenant safety is preserved)."""
    user = await get_optional_user(request)
    session = _get_session()
    try:
        q = session.query(ScheduledPost)
        if user:
            q = q.filter(ScheduledPost.created_by == user.get("email"))
        rows = q.order_by(ScheduledPost.scheduled_at.asc()).all()
        return [_serialize(r) for r in rows]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Visual Content Calendar API (month/week grid, recurring + bulk scheduling)
# ---------------------------------------------------------------------------

RECURRENCE_INTERVALS = {"daily": 1, "weekly": 7, "monthly": 30}
RECURRENCE_MAX = 52  # hard safety cap on generated instances


def _expand_recurrence(start_utc: datetime, recurrence: str, end_utc: Optional[datetime]):
    """Return a list of naive-UTC datetimes for a recurring schedule.

    Includes the start date, then steps by the recurrence interval until the
    end date (or a sane default of 12 occurrences) is reached.
    """
    interval = RECURRENCE_INTERVALS.get(recurrence)
    if not interval:
        return [start_utc]

    if end_utc is None:
        end_utc = start_utc + timedelta(days=interval * 11)  # default: 12 posts
    if end_utc.tzinfo is not None:
        end_utc = end_utc.replace(tzinfo=None)

    out = []
    cursor = start_utc
    while cursor <= end_utc and len(out) < RECURRENCE_MAX:
        out.append(cursor)
        cursor = cursor + timedelta(days=interval)
    return out


class CalendarPostCreate(BaseModel):
    scheduled_at: str
    platforms: List[str]
    content: str = ""
    ai_prompt: str = ""        # when `content` is empty, this topic generates the caption
    media_url: Optional[str] = None
    recurrence: str = "none"
    recurrence_end: Optional[str] = None
    tone: str = "viral"


async def _build_post_rows(payload: CalendarPostCreate, owner_email: str):
    """Resolve caption + media + recurrence, returning a list of ScheduledPost rows."""
    dt_start = _parse_scheduled_at(payload.scheduled_at)
    if dt_start < datetime.utcnow() - timedelta(seconds=60):
        raise HTTPException(status_code=400, detail="Scheduled time must be at least 1 minute in the future")

    platforms = payload.platforms
    if not isinstance(platforms, list) or not platforms:
        raise HTTPException(status_code=400, detail="Select at least one platform")
    invalid = [p for p in platforms if p not in VALID_PLATFORMS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported platform(s): {', '.join(invalid)}")

    # Resolve the caption — either use the supplied text or generate one.
    if payload.content and payload.content.strip():
        caption = payload.content.strip()
    else:
        topic = (payload.ai_prompt or "").strip() or "a general brand update"
        try:
            generated = await _generate_post_content(topic, tone=payload.tone)
            caption = generated.get("body") or topic
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI caption generation failed: {str(e)}")

    media_url = payload.media_url
    media_type = None
    # Optional AI image generation when a prompt is given and no media URL is supplied.
    if (payload.ai_prompt or "").strip() and not media_url:
        try:
            prompt = _boosted_ai_prompt(payload.ai_prompt.strip())
            img_bytes, mime = await _generate_pollinations_image(prompt, 1080, 1080)
            media_type = "image"
            media_url = await _upload_to_cloudinary(img_bytes, f"cal_ai_{int(time.time()*1000)}.jpg", "image")
        except Exception as e:
            logger.warning("AI image generation skipped for calendar post: %s", e)

    recurrence = payload.recurrence if payload.recurrence in RECURRENCE_INTERVALS else "none"
    end_utc = None
    if recurrence != "none" and payload.recurrence_end:
        end_utc = _parse_scheduled_at(payload.recurrence_end)

    slots = _expand_recurrence(dt_start, recurrence, end_utc)
    rows = []
    for slot in slots:
        rows.append(ScheduledPost(
            scheduled_at=slot,
            platforms=json.dumps(platforms),
            content=caption,
            media_url=media_url,
            media_type=media_type,
            status="pending",
            created_by=owner_email,
            recurrence=recurrence,
            recurrence_end=end_utc,
            recurring=(recurrence != "none"),
        ))
    return rows


@router.post("/calendar/post")
async def calendar_create_post(payload: CalendarPostCreate, user: dict = Depends(require_subscription)):
    """Create one post (or a recurring series) from the Visual Content Calendar."""
    rows = await _build_post_rows(payload, user["email"])
    session = _get_session()
    try:
        session.add_all(rows)
        session.commit()
        created = []
        for r in rows:
            session.refresh(r)
            created.append(_serialize(r))
        await record_usage(
            user, "scheduled_post",
            f"Scheduled {len(created)} post(s) via Calendar",
            f"{payload.recurrence} · {', '.join(payload.platforms)}",
        )
        return {"created": created, "count": len(created)}
    finally:
        session.close()


class CalendarBulkCreate(BaseModel):
    posts: List[CalendarPostCreate]


@router.post("/calendar/bulk")
async def calendar_bulk_create(payload: CalendarBulkCreate, user: dict = Depends(require_subscription)):
    """Bulk-queue many posts at once (e.g. a full content series)."""
    if not payload.posts:
        raise HTTPException(status_code=400, detail="No posts supplied")
    if len(payload.posts) > 200:
        raise HTTPException(status_code=400, detail="Bulk limit is 200 posts per request")
    all_rows = []
    for item in payload.posts:
        all_rows.extend(await _build_post_rows(item, user["email"]))
    session = _get_session()
    try:
        session.add_all(all_rows)
        session.commit()
        created = [_serialize(r) for r in all_rows]
        await record_usage(
            user, "scheduled_post",
            f"Bulk-queued {len(created)} post(s)",
            "Calendar bulk import",
        )
        return {"created": created, "count": len(created)}
    finally:
        session.close()


@router.get("/calendar/posts")
async def calendar_list_posts(user: dict = Depends(require_subscription)):
    """Return every scheduled post owned by the current user."""
    session = _get_session()
    try:
        rows = (
            session.query(ScheduledPost)
            .filter(ScheduledPost.created_by == user["email"])
            .order_by(ScheduledPost.scheduled_at.asc())
            .all()
        )
        return [_serialize(r) for r in rows]
    finally:
        session.close()


class CalendarPostUpdate(BaseModel):
    scheduled_at: Optional[str] = None
    platforms: Optional[List[str]] = None
    content: Optional[str] = None
    recurrence: Optional[str] = None
    recurrence_end: Optional[str] = None


@router.put("/calendar/post/{post_id}")
async def calendar_update_post(post_id: int, payload: CalendarPostUpdate, user: dict = Depends(require_subscription)):
    session = _get_session()
    try:
        post = session.get(ScheduledPost, post_id)
        if not post or post.created_by != user["email"]:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.status not in ("pending", "failed"):
            raise HTTPException(status_code=400, detail="Only pending or failed posts can be edited")

        if payload.scheduled_at:
            post.scheduled_at = _parse_scheduled_at(payload.scheduled_at)
        if payload.platforms is not None:
            post.platforms = json.dumps(payload.platforms)
        if payload.content is not None:
            post.content = payload.content
        if payload.recurrence is not None:
            post.recurrence = payload.recurrence if payload.recurrence in RECURRENCE_INTERVALS else "none"
            post.recurring = post.recurrence != "none"
        if payload.recurrence_end is not None:
            post.recurrence_end = _parse_scheduled_at(payload.recurrence_end) if payload.recurrence_end else None
        session.commit()
        session.refresh(post)
        return _serialize(post)
    finally:
        session.close()


@router.delete("/calendar/post/{post_id}")
async def calendar_delete_post(post_id: int, user: dict = Depends(require_subscription)):
    session = _get_session()
    try:
        post = session.get(ScheduledPost, post_id)
        if not post or post.created_by != user["email"]:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.status not in ("pending", "failed"):
            raise HTTPException(status_code=400, detail="Only pending or failed posts can be removed")
        session.delete(post)
        session.commit()
        return {"status": "deleted", "id": post_id}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Personal Notes & Reminders (the third layer of the unified calendar)
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    date: str                              # YYYY-MM-DD (the calendar day)
    title: Optional[str] = None
    body: Optional[str] = None
    note: Optional[str] = None             # alias for body (frontend uses this)
    color: Optional[str] = None           # mauve | violet | gold | aqua
    best_time: Optional[str] = None       # suggested posting time (HH:MM)
    notify: bool = False
    notify_at: Optional[str] = None       # ISO datetime for the reminder
    completed: bool = False


class NoteUpdate(BaseModel):
    date: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None
    best_time: Optional[str] = None
    notify: Optional[bool] = None
    notify_at: Optional[str] = None
    completed: Optional[bool] = None


def _parse_dt(value):
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _serialize_note(doc):
    na = doc.get("notify_at")
    if isinstance(na, datetime):
        na = na.isoformat()
    body = doc.get("body") or doc.get("note") or ""
    title = doc.get("title") or ""
    return {
        "id": str(doc["_id"]),
        "date": doc.get("date"),
        "title": title,
        "note": body,
        "body": body,
        "color": doc.get("color") or "mauve",
        "best_time": doc.get("best_time"),
        "notify": bool(doc.get("notify")),
        "notify_at": na,
        "notified": bool(doc.get("notified")),
        "completed": bool(doc.get("completed")),
    }


@router.get("/calendar/notes")
async def list_notes(user: dict = Depends(require_subscription)):
    docs = await mongodb.calendar_notes.find({"user_email": user["email"]}).sort("date", 1).to_list(length=500)
    return [_serialize_note(d) for d in docs]


@router.post("/calendar/notes")
async def create_note(payload: NoteCreate, user: dict = Depends(require_subscription)):
    body_text = (payload.body or payload.note or "").strip()
    if not (body_text or payload.title):
        raise HTTPException(status_code=400, detail="Note text is required")
    doc = {
        "user_email": user["email"],
        "date": payload.date,
        "title": (payload.title or "").strip(),
        "body": body_text,
        "note": body_text,
        "color": payload.color or "mauve",
        "best_time": payload.best_time,
        "completed": bool(payload.completed),
        "notify": bool(payload.notify),
        "notify_at": _parse_dt(payload.notify_at),
        "notified": False,
        "created_at": utc_now(),
    }
    res = await mongodb.calendar_notes.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _serialize_note(doc)


@router.put("/calendar/notes/{note_id}")
async def update_note(note_id: str, payload: NoteUpdate, user: dict = Depends(require_subscription)):
    try:
        oid = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    existing = await mongodb.calendar_notes.find_one({"_id": oid, "user_email": user["email"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    update = {}
    if payload.date is not None:
        update["date"] = payload.date
    if payload.title is not None:
        update["title"] = payload.title.strip()
    if payload.body is not None:
        update["body"] = payload.body.strip()
        update["note"] = payload.body.strip()
    if payload.note is not None and payload.body is None:
        update["body"] = payload.note.strip()
        update["note"] = payload.note.strip()
    if payload.color is not None:
        update["color"] = payload.color
    if payload.best_time is not None:
        update["best_time"] = payload.best_time
    if payload.notify is not None:
        update["notify"] = bool(payload.notify)
    if payload.notify_at is not None:
        update["notify_at"] = _parse_dt(payload.notify_at)
        update["notified"] = False  # re-arm the reminder
    if payload.completed is not None:
        update["completed"] = bool(payload.completed)
    if update:
        await mongodb.calendar_notes.update_one({"_id": oid}, {"$set": update})
    updated = await mongodb.calendar_notes.find_one({"_id": oid})
    return _serialize_note(updated)


@router.patch("/calendar/notes/{note_id}/notify")
async def mark_note_notified(note_id: str, user: dict = Depends(require_subscription)):
    try:
        oid = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    await mongodb.calendar_notes.update_one(
        {"_id": oid, "user_email": user["email"]}, {"$set": {"notified": True}})
    return {"status": "ok"}


@router.delete("/calendar/notes/{note_id}")
async def delete_note(note_id: str, user: dict = Depends(require_subscription)):
    try:
        oid = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    await mongodb.calendar_notes.delete_one({"_id": oid, "user_email": user["email"]})
    return {"status": "deleted", "id": note_id}


@router.delete("/schedule/{post_id}")
def delete_scheduled_post(post_id: int):
    """Remove a pending or failed scheduled post."""
    session = _get_session()
    try:
        post = session.get(ScheduledPost, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Scheduled post not found")
        if post.status not in ("pending", "failed"):
            raise HTTPException(status_code=400, detail="Only pending or failed posts can be removed")
        session.delete(post)
        session.commit()
        return {"status": "deleted", "id": post_id}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Cron engine — called by APScheduler every 60 seconds
# ---------------------------------------------------------------------------

async def scan_due_posts():
    """Find pending posts whose time has come, claim them, and publish in the background."""
    now = datetime.utcnow()
    session = _get_session()
    try:
        rows = (
            session.query(ScheduledPost)
            .filter(
                ScheduledPost.status == "pending",
                ScheduledPost.scheduled_at <= now,
            )
            .all()
        )
        if rows:
            print(f"[SCHEDULER] {datetime.utcnow().isoformat()} scan found {len(rows)} due post(s)")
        for row in rows:
            claimed = (
                session.query(ScheduledPost)
                .filter(
                    ScheduledPost.id == row.id,
                    ScheduledPost.status == "pending",
                )
                .update({"status": "processing"})
            )
            if claimed:
                task = asyncio.create_task(_execute_post(row.id))
                _active_tasks.add(task)
                task.add_done_callback(_active_tasks.discard)
    finally:
        session.close()


async def _execute_post(post_id: int):
    """Publish a single scheduled post through the existing pipeline, then mark it."""
    session = _get_session()
    try:
        post = session.get(ScheduledPost, post_id)
        if not post:
            return

        platforms = json.loads(post.platforms)
        results = {}

        for platform in platforms:
            account = connected_accounts.get(platform)
            if not account:
                results[platform] = {"status": "not_connected", "message": f"{platform} is not connected"}
                continue

            access_token = account.get("access_token")
            if not access_token:
                results[platform] = {"status": "no_token", "message": f"No access token for {platform}"}
                continue

            try:
                if platform == "facebook":
                    results[platform] = await _post_to_facebook(
                        account, post.content, post.media_url, post.media_type
                    )
                elif platform == "linkedin":
                    results[platform] = await _post_to_linkedin(
                        access_token, post.content, post.media_url, post.media_type
                    )
                elif platform == "instagram":
                    results[platform] = await _post_to_instagram(
                        account, post.content, post.media_url, post.media_type
                    )
                else:
                    results[platform] = {"status": "unsupported", "message": f"{platform} not supported"}
            except Exception as e:
                logger.error("Scheduled publish error [%s]: %s", platform, e, exc_info=True)
                results[platform] = {"status": "error", "message": str(e)}

        status = "published" if all(r.get("status") == "success" for r in results.values()) else "failed"

        # Log each successful auto-publish into the user's activity history
        if status == "published" and post.created_by:
            try:
                user_doc = await mongodb.users.find_one({"email": post.created_by})
                if user_doc:
                    for platform, res in results.items():
                        if res.get("status") == "success":
                            await record_usage(
                                user_doc,
                                "scheduled_post",
                                f"Auto-published to {platform.capitalize()}",
                                f"Your scheduled post went live on {platform.capitalize()}.",
                            )
            except Exception as log_err:
                logger.warning("Failed to log auto-publish history: %s", log_err)

        post = session.get(ScheduledPost, post_id)
        post.status = status
        post.result = json.dumps(results, indent=2)
        session.commit()
        print(f"[SCHEDULER] Post #{post_id} -> {status}: {json.dumps(results)}")
    except Exception as e:
        logger.error("Scheduled publish crashed for post %s: %s", post_id, e, exc_info=True)
        session2 = _get_session()
        try:
            p = session2.get(ScheduledPost, post_id)
            if p:
                p.status = "failed"
                p.result = json.dumps({"error": str(e)})
                session2.commit()
        except Exception:
            pass
        finally:
            session2.close()
    finally:
        session.close()