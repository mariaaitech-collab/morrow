"""Registry of posts this app published, so an inbound comment can be routed to
its workspace by the post it was made on (LinkedIn notifications identify the
post, and the organization or subscriber, but not our workspace).

    await record(user_id, "linkedin", "urn:li:share:123")
    await owner_of("linkedin", "urn:li:share:123")  -> user_id | None
"""
from __future__ import annotations

import hashlib

import firebase_db
from config import utc_now


def _ref(platform: str, post_id: str):
    return firebase_db.published_posts.document(
        hashlib.sha256(f"{platform}|{post_id}".encode()).hexdigest()[:32]
    )


async def record(user_id: str, platform: str, post_id: str) -> None:
    """Remember who published `post_id`. Best effort: never breaks a publish."""
    if not (user_id and platform and post_id):
        return
    try:
        await _ref(platform, str(post_id)).set({
            "user_id": user_id, "platform": platform, "post_id": str(post_id), "published_at": utc_now(),
        })
    except Exception as e:
        print(f"[POSTS] could not record {platform} post {post_id}: {e}")


async def record_results(user_id: str, results: dict) -> None:
    """Record every successful post id in a publish `results` map."""
    for platform, result in (results or {}).items():
        if isinstance(result, dict) and result.get("status") == "success" and result.get("post_id"):
            # Facebook multi-page publishes join several ids with commas.
            for post_id in str(result["post_id"]).split(","):
                await record(user_id, platform, post_id.strip())


async def owner_of(platform: str, post_id: str) -> str | None:
    if not post_id:
        return None
    doc = await firebase_db.get(_ref(platform, str(post_id)))
    return (doc or {}).get("user_id")
