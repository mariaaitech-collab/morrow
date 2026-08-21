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

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import ScheduledPost, SessionLocal
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
    }


def _get_session():
    return SessionLocal()


@router.post("/schedule")
async def create_scheduled_post(
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
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        print(f"[SCHEDULER] Saved scheduled post #{post.id} at {post.scheduled_at} UTC for {platform_list}")
        return _serialize(post)
    finally:
        session.close()


@router.get("/schedule")
def list_scheduled_posts():
    """Return all scheduled posts ordered by their scheduled time."""
    session = _get_session()
    try:
        rows = (
            session.query(ScheduledPost)
            .order_by(ScheduledPost.scheduled_at.asc())
            .all()
        )
        return [_serialize(r) for r in rows]
    finally:
        session.close()


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