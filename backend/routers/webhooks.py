"""Inbound webhooks for the AI Auto-Responder.

    GET  /api/webhooks/{platform}   verification handshake
    POST /api/webhooks/{platform}   event delivery (comments + DMs)

platform = facebook | instagram | linkedin | tiktok  ("meta" is an alias that
accepts both Facebook Page and Instagram events on one callback URL).

Every POST is authenticated by the platform's HMAC signature, acknowledged
with 200 immediately, and processed in a background task. Meta retries
deliveries that take longer than ~20s, so the LLM call and the outgoing reply
must never run inside the request.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from config import (
    INSTAGRAM_APP_SECRET,
    LINKEDIN_CLIENT_SECRET,
    META_APP_SECRET,
    META_WEBHOOK_VERIFY_TOKEN,
    TIKTOK_CLIENT_SECRET,
    WEBHOOK_REQUIRE_SIGNATURE,
)
import inbound_log
import published_posts
from responder_service import handle_new_event, platform_enabled, platform_off_reason, spawn
import routers.social as social_store
from routers.social import find_owners_by_external_id, get_user_accounts

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

SUPPORTED = ("facebook", "instagram", "meta", "linkedin", "tiktok")
MAX_BODY_BYTES = 1_000_000


# --------------------------------------------------------------------------
# Signature verification
# --------------------------------------------------------------------------
def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _verify_meta(raw: bytes, header: str) -> bool:
    if not header.startswith("sha256="):
        return False
    received = header.split("=", 1)[1].strip()
    for secret in {META_APP_SECRET, INSTAGRAM_APP_SECRET} - {""}:
        if hmac.compare_digest(_hmac_hex(secret, raw), received):
            return True
    return False


def _verify_linkedin(raw: bytes, header: str) -> bool:
    if not LINKEDIN_CLIENT_SECRET or not header:
        return False
    received = header.split("=", 1)[1] if header.lower().startswith("hmacsha256=") else header
    return hmac.compare_digest(_hmac_hex(LINKEDIN_CLIENT_SECRET, raw), received.strip())


def _verify_tiktok(raw: bytes, header: str) -> bool:
    # TikTok-Signature: t=<unix ts>,s=<hex hmac of "<t>.<body>">
    if not TIKTOK_CLIENT_SECRET or not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, sig = parts.get("t", ""), parts.get("s", "")
    if not ts.isdigit() or not sig:
        return False
    if abs(time.time() - int(ts)) > 300:  # replay protection
        return False
    expected = _hmac_hex(TIKTOK_CLIENT_SECRET, ts.encode() + b"." + raw)
    return hmac.compare_digest(expected, sig)


def _check_signature(platform: str, raw: bytes, request: Request) -> None:
    if platform in ("facebook", "instagram", "meta"):
        ok = _verify_meta(raw, request.headers.get("X-Hub-Signature-256", ""))
        configured = bool(META_APP_SECRET or INSTAGRAM_APP_SECRET)
    elif platform == "linkedin":
        ok = _verify_linkedin(raw, request.headers.get("X-LI-Signature", ""))
        configured = bool(LINKEDIN_CLIENT_SECRET)
    else:
        ok = _verify_tiktok(raw, request.headers.get("TikTok-Signature", ""))
        configured = bool(TIKTOK_CLIENT_SECRET)

    if ok:
        return
    if not WEBHOOK_REQUIRE_SIGNATURE:
        print(f"[WEBHOOK] {platform}: signature missing/invalid but WEBHOOK_REQUIRE_SIGNATURE=false (dev only)")
        return
    if not configured:
        print(f"[WEBHOOK] {platform}: app secret not configured, rejecting unsigned delivery")
    raise HTTPException(status_code=401, detail="Invalid webhook signature")


# --------------------------------------------------------------------------
# GET: verification handshakes
# --------------------------------------------------------------------------
@router.get("/{platform}")
async def verify_webhook(platform: str, request: Request):
    platform = platform.lower()
    if platform not in SUPPORTED:
        raise HTTPException(status_code=404, detail="Unknown webhook platform")
    q = request.query_params

    if platform in ("facebook", "instagram", "meta"):
        mode = q.get("hub.mode", "")
        token = q.get("hub.verify_token", "")
        challenge = q.get("hub.challenge", "")
        if not META_WEBHOOK_VERIFY_TOKEN:
            raise HTTPException(status_code=500, detail="META_WEBHOOK_VERIFY_TOKEN is not set in .env")
        if mode == "subscribe" and hmac.compare_digest(token, META_WEBHOOK_VERIFY_TOKEN):
            print(f"[WEBHOOK] Meta verification succeeded for /{platform}")
            return PlainTextResponse(challenge)
        raise HTTPException(status_code=403, detail="Verification token mismatch")

    if platform == "linkedin":
        # LinkedIn sends ?challengeCode=... and expects an HMAC of it back.
        code = q.get("challengeCode", "")
        if not code:
            return {"status": "ok", "platform": "linkedin"}
        if not LINKEDIN_CLIENT_SECRET:
            await inbound_log.record("linkedin", "rejected", "Validation challenge failed: LINKEDIN_CLIENT_SECRET is not set",
                                     source="challenge")
            raise HTTPException(status_code=500, detail="LINKEDIN_CLIENT_SECRET is not set in .env")
        # Proof that LinkedIn knows this callback URL (it re-validates it periodically).
        await inbound_log.record("linkedin", "challenge", "LinkedIn validated the webhook URL", source="challenge")
        return JSONResponse({
            "challengeCode": code,
            "challengeResponse": _hmac_hex(LINKEDIN_CLIENT_SECRET, code.encode("utf-8")),
        })

    # TikTok has no GET challenge; it validates by POSTing a signed test event.
    return {"status": "ok", "platform": "tiktok"}


# --------------------------------------------------------------------------
# POST: event delivery
# --------------------------------------------------------------------------
@router.post("/{platform}")
async def receive_webhook(platform: str, request: Request):
    platform = platform.lower()
    if platform not in SUPPORTED:
        raise HTTPException(status_code=404, detail="Unknown webhook platform")
    raw = await request.body()
    log_platform = "facebook" if platform == "meta" else platform
    if len(raw) > MAX_BODY_BYTES:
        await inbound_log.record(log_platform, "rejected", f"Payload too large ({len(raw)} bytes)")
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        _check_signature(platform, raw, request)
    except HTTPException:
        await inbound_log.record(log_platform, "rejected", "Invalid or missing signature", raw=raw.decode("utf-8", "replace"))
        raise
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        await inbound_log.record(log_platform, "rejected", "Body is not JSON", raw=raw.decode("utf-8", "replace"))
        raise HTTPException(status_code=400, detail="Body must be JSON")

    # Acknowledge now; parse + AI + reply happen in the background.
    spawn(_dispatch(platform, payload))
    return {"status": "received"}


async def _dispatch(platform: str, payload: dict, source: str = "webhook") -> None:
    """Parse one delivery and hand each item to the responder. Every item ends
    in the inbound log: accepted, duplicate, dropped (with why), or unattributed."""
    log_platform = ("instagram" if payload.get("object") == "instagram" else "facebook") if platform in ("facebook", "instagram", "meta") else platform
    if not platform_enabled(log_platform):
        # Outside RESPONDER_PLATFORMS: logged, then ignored. Never parsed, stored,
        # queued or answered. The parsers and matching below stay for when it is on.
        await inbound_log.record(log_platform, "ignored", platform_off_reason(log_platform), raw=payload, source=source)
        return
    try:
        if platform in ("facebook", "instagram", "meta"):
            events, skipped = parse_meta(payload), []
        elif platform == "linkedin":
            events, skipped = await parse_linkedin(payload)
        else:
            events, skipped = parse_tiktok(payload), []
    except Exception as e:
        await inbound_log.record(log_platform, "error", f"Could not parse the payload: {type(e).__name__}: {e}", raw=payload, source=source)
        return

    for reason, item in skipped:
        await inbound_log.record(log_platform, "dropped", reason, raw=item, source=source)
    if not events and not skipped:
        await inbound_log.record(log_platform, "dropped", "No comment or message in this delivery", raw=payload, source=source)

    for owner_platform, account_id, event in events:
        routing = event.get("routing") or {}
        user_id = routing.get("user_id")
        if not user_id:
            # One reply per inbound message: if several users connected the same
            # Page, the first connection owns the auto-responder for it.
            owners = find_owners_by_external_id(owner_platform, account_id)
            user_id = owners[0][0] if owners else None
        if not user_id:
            # No workspace to put it in: it stays in the inbound log (admins can see it).
            await inbound_log.record(
                owner_platform, "unattributed",
                routing.get("note") or f"No Morrow workspace has {owner_platform} account {account_id} connected",
                raw=event.get("raw"), source=source,
            )
            continue
        try:
            event_id = await handle_new_event(user_id, event)
        except Exception as e:
            await inbound_log.record(owner_platform, "error", f"Processing failed: {type(e).__name__}: {e}",
                                     raw=event.get("raw"), source=source, user_id=user_id)
            continue
        how = f" (matched by {routing['matched_by']})" if routing.get("matched_by") else ""
        if event_id:
            await inbound_log.record(owner_platform, "accepted", f"Stored as a responder event{how}",
                                     raw=event.get("raw"), source=source, user_id=user_id, event_id=event_id)
        else:
            await inbound_log.record(owner_platform, "duplicate", "Already received (a platform retry); not stored again",
                                     raw=event.get("raw"), source=source, user_id=user_id)


def _ts(value) -> datetime | None:
    """Platform timestamps arrive as unix seconds, unix millis or ISO strings."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            num = float(value)
            if num > 1e12:
                num /= 1000.0
            return datetime.fromtimestamp(num, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").replace("+0000", "+00:00"))
    except Exception:
        return None


def _trim(obj: dict) -> dict:
    """Keep a bounded copy of the raw payload for debugging."""
    text = json.dumps(obj, default=str)
    return json.loads(text) if len(text) <= 8000 else {"truncated": text[:8000]}


# --------------------------------------------------------------------------
# Meta (Facebook Page + Instagram)
# --------------------------------------------------------------------------
def parse_meta(payload: dict) -> list[tuple[str, str, dict]]:
    obj = payload.get("object")
    platform = "instagram" if obj == "instagram" else "facebook"
    out: list[tuple[str, str, dict]] = []

    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id") or "")

        # Comments arrive as "changes".
        for change in entry.get("changes") or []:
            field = change.get("field")
            value = change.get("value") or {}
            if platform == "facebook" and field == "feed":
                if value.get("item") != "comment" or value.get("verb") != "add":
                    continue
                author = value.get("from") or {}
                if str(author.get("id")) == account_id:
                    continue  # the Page's own reply: never answer ourselves
                comment_id = value.get("comment_id")
                if not comment_id or not value.get("message"):
                    continue
                out.append((platform, account_id, {
                    "platform": "facebook",
                    "kind": "comment",
                    "external_id": comment_id,
                    "text": value.get("message", ""),
                    "author": {"id": author.get("id"), "name": author.get("name", "")},
                    "post_id": value.get("post_id"),
                    "account_ref": account_id,
                    "reply_target": {"comment_id": comment_id, "post_id": value.get("post_id")},
                    "platform_timestamp": _ts(value.get("created_time") or entry.get("time")),
                    "raw": _trim(value),
                }))
            elif platform == "instagram" and field == "comments":
                author = value.get("from") or {}
                if str(author.get("id")) == account_id:
                    continue
                comment_id = value.get("id")
                if not comment_id or not value.get("text"):
                    continue
                out.append((platform, account_id, {
                    "platform": "instagram",
                    "kind": "comment",
                    "external_id": comment_id,
                    "text": value.get("text", ""),
                    "author": {"id": author.get("id"), "name": author.get("username", "")},
                    "post_id": (value.get("media") or {}).get("id"),
                    "account_ref": account_id,
                    "reply_target": {"comment_id": comment_id, "media_id": (value.get("media") or {}).get("id")},
                    "platform_timestamp": _ts(entry.get("time")),
                    "raw": _trim(value),
                }))

        # DMs arrive as "messaging" (Messenger and Instagram Messaging).
        for msg_event in entry.get("messaging") or []:
            message = msg_event.get("message") or {}
            if message.get("is_echo") or not message.get("text"):
                continue  # our own outgoing message, or a sticker/attachment
            sender = str((msg_event.get("sender") or {}).get("id") or "")
            if not sender or sender == account_id:
                continue
            mid = message.get("mid")
            if not mid:
                continue
            out.append((platform, account_id, {
                "platform": platform,
                "kind": "dm",
                "external_id": mid,
                "text": message.get("text", ""),
                "author": {"id": sender, "name": ""},
                "post_id": None,
                "account_ref": account_id,
                "reply_target": {"recipient_id": sender},
                "platform_timestamp": _ts(msg_event.get("timestamp")),
                "raw": _trim(msg_event),
            }))
    return out


# --------------------------------------------------------------------------
# LinkedIn (Organization Social Action Notifications)
# --------------------------------------------------------------------------
def _linkedin_comment_id(activity_urn: str) -> str:
    # urn:li:comment:(urn:li:activity:123,456) -> 456
    if activity_urn.startswith("urn:li:comment:(") and activity_urn.endswith(")"):
        return activity_urn.rsplit(",", 1)[-1].rstrip(")")
    return ""


async def _fetch_linkedin_comment_text(user_id: str, post_urn: str, comment_id: str) -> tuple[str, str]:
    """(text, why it could not be fetched). Needs r_organization_social on the token."""
    from urllib.parse import quote

    acct = get_user_accounts(user_id).get("linkedin") or {}
    token = acct.get("access_token")
    if not token:
        return "", "the LinkedIn connection has no access token"
    if not (post_urn and comment_id):
        return "", "the notification has no post or comment id"
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"https://api.linkedin.com/v2/socialActions/{quote(post_urn, safe='')}/comments/{comment_id}",
                headers={"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0"},
            )
        if resp.status_code == 200:
            return ((resp.json() or {}).get("message") or {}).get("text", ""), ""
        return "", f"LinkedIn answered HTTP {resp.status_code}: {resp.text[:160]}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


# Notification actions that are not a new comment from someone else.
LINKEDIN_NOT_A_COMMENT = {
    "ADMIN_COMMENT": "A comment by a Page admin (you), so it is not answered",
    "COMMENT_EDIT": "An edit to an existing comment; only new comments are answered",
    "COMMENT_DELETE": "A comment was deleted",
    "LIKE": "A like, not a comment",
    "SHARE": "A share, not a comment",
    "SHARE_MENTION": "A mention in someone's post, not a comment",
}
LINKEDIN_NO_TEXT = "(LinkedIn did not include the comment text)"


async def _route_linkedin(org: str, subscriber: str, post_urns: list[str]) -> dict:
    """Which workspace a LinkedIn notification belongs to, and how we know.

    LinkedIn notifications carry the organization, the subscribing member and
    the post, but no id of ours. Tried in order: the organization (a connected
    channel), the subscribing member, then a post this app published. Only an
    organization match counts as a matched channel; the other two still route
    the comment to its workspace, where it waits for review.
    """
    if org:
        owners = find_owners_by_external_id("linkedin", org)
        if owners:
            return {"user_id": owners[0][0], "matched_by": "organization", "channel_matched": True,
                    "note": f"organization {org} is a connected channel"}
    route = None
    if subscriber:
        owners = find_owners_by_external_id("linkedin", subscriber)
        if owners:
            route = {"user_id": owners[0][0], "matched_by": "subscriber",
                     "how": f"the LinkedIn member who connected Morrow ({subscriber})"}
    if not route:
        for urn in post_urns:
            user_id = await published_posts.owner_of("linkedin", urn)
            if user_id:
                route = {"user_id": user_id, "matched_by": "post", "how": f"the post {urn}, published from Morrow"}
                break
    if not route:
        return {"user_id": None, "matched_by": "", "channel_matched": False,
                "note": (f"No Morrow workspace matched: organization {org or '(none)'}, subscriber {subscriber or '(none)'}, "
                         f"post {', '.join(u for u in post_urns if u) or '(none)'}")}
    how = route.pop("how")
    return {**route, "channel_matched": False,
            "note": f"organization {org or '(none)'} is not one of your connected LinkedIn channels; matched to you by {how}"}


async def parse_linkedin(payload: dict) -> tuple[list[tuple[str, str, dict]], list[tuple[str, dict]]]:
    """(events, skipped). LinkedIn's OrganizationSocialActionNotification fields:
    notificationId, organizationalEntity, action, sourcePost, decoratedSourcePost
    {entity, owner, text}, generatedActivity, decoratedGeneratedActivity
    {comment: {entity, owner, object, text}}, lastModifiedAt, subscriber."""
    events: list[tuple[str, str, dict]] = []
    skipped: list[tuple[str, dict]] = []
    items = payload.get("notifications") or ([payload] if payload.get("action") else [])
    for item in items:
        action = (item.get("action") or "").upper()
        if action != "COMMENT":
            skipped.append((LINKEDIN_NOT_A_COMMENT.get(action, f"Not a comment (action {action or 'missing'})"), item))
            continue
        org = item.get("organizationalEntity") or ""
        subscriber = item.get("subscriber") or ""
        post_urn = item.get("sourcePost") or ""
        post_entity = (item.get("decoratedSourcePost") or {}).get("entity") or ""
        comment = (item.get("decoratedGeneratedActivity") or {}).get("comment") or {}
        comment_urn = item.get("generatedActivity") or comment.get("entity") or ""
        if not comment_urn:
            skipped.append(("The notification has no comment id, so it cannot be stored or answered", item))
            continue
        commenter = comment.get("owner") or item.get("actor") or ""
        if org and commenter == org:
            skipped.append(("A comment by your own organization, not answered", item))
            continue

        route = await _route_linkedin(org, subscriber, [post_entity, post_urn])
        text = comment.get("text") or item.get("commentText") or ""
        missing_why = ""
        if not text and route["user_id"]:
            text, missing_why = await _fetch_linkedin_comment_text(
                route["user_id"], post_urn, _linkedin_comment_id(comment_urn) or comment_urn)
        events.append(("linkedin", org or subscriber, {
            "platform": "linkedin",
            "kind": "comment",
            "external_id": comment_urn,
            "text": text or LINKEDIN_NO_TEXT,
            "text_missing": not text,
            "text_missing_reason": missing_why if not text else "",
            "author": {"id": commenter, "name": ""},
            "post_id": post_entity or post_urn,
            "account_ref": org or None,
            "reply_target": {"post_urn": post_urn, "comment_urn": comment_urn, "actor_urn": org},
            "platform_timestamp": _ts(item.get("lastModifiedAt")),
            "routing": route,
            "raw": _trim(item),
        }))
    return events, skipped


# --------------------------------------------------------------------------
# TikTok
# --------------------------------------------------------------------------
def parse_tiktok(payload: dict) -> list[tuple[str, str, dict]]:
    event_name = (payload.get("event") or "").lower()
    open_id = str(payload.get("user_openid") or payload.get("business_id") or "")
    content = payload.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {"text": content}

    if event_name == "authorization.removed":
        # The creator revoked BrandAura in TikTok: drop the stale token.
        for user_id, _ in find_owners_by_external_id("tiktok", open_id):
            social_store.connected_accounts.get(user_id, {}).pop("tiktok", None)
            print(f"[WEBHOOK] TikTok authorization removed for user {user_id}; account disconnected")
        social_store._save_accounts()
        return []

    is_comment = "comment" in event_name
    is_dm = "message" in event_name or "direct" in event_name
    if not (is_comment or is_dm):
        return []  # video.publish.* etc. are informational

    text = content.get("text") or content.get("comment_text") or content.get("message") or ""
    external_id = content.get("comment_id") or content.get("message_id") or content.get("id")
    if not (text and external_id):
        return []
    author_id = str(content.get("user_id") or content.get("from_user_id") or content.get("open_id") or "")
    if author_id and author_id == open_id:
        return []
    video_id = content.get("video_id") or content.get("item_id")
    return [("tiktok", open_id, {
        "platform": "tiktok",
        "kind": "comment" if is_comment else "dm",
        "external_id": str(external_id),
        "text": text,
        "author": {"id": author_id, "name": content.get("username") or content.get("display_name") or ""},
        "post_id": video_id,
        "account_ref": open_id,
        "reply_target": {"comment_id": str(external_id), "video_id": video_id},
        "platform_timestamp": _ts(content.get("create_time") or payload.get("create_time")),
        "raw": _trim(payload),
    })]
