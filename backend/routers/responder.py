"""Auto-Responder API (authenticated). Rule-based: no model call anywhere.

Rules (Persona page)
    GET    /api/responder/persona               rules, fallback, escalation keywords, switches
    PUT    /api/responder/persona               save them
    POST   /api/responder/persona/logo          upload a logo or brand asset image
    POST   /api/responder/persona/preview       test box: what would happen to a comment (nothing stored)
    GET    /api/responder/gaps?days=30          rule coverage + unmatched comments, grouped

Reply modes (apply immediately; see responder_service "Reply modes")
    GET    /api/responder/modes                 workspace default, channels + overrides, always-review list
    PUT    /api/responder/modes/workspace       {mode?, no_match_action?, paused?}
    PUT    /api/responder/modes/channels/{key}  {mode: inherit | instant | review}
    POST   /api/responder/always-review         {platform, author_id, name, on}

Channel health / inbound deliveries
    GET    /api/responder/channel-health        per channel: can it receive, last event, why not
    GET    /api/responder/inbound-log?platform=&limit=20   every webhook/poll delivery and its outcome

Needs your attention / activity
    GET    /api/responder/queue                 held items (flagged, escalated, failed)
    GET    /api/responder/events?status=...     full activity log
    POST   /api/responder/events/{id}/accept    post the suggested (or edited) reply
    POST   /api/responder/events/{id}/decline   discard the suggestion
    POST   /api/responder/events/{id}/reply     post a custom manual reply
    POST   /api/responder/events/{id}/edit-reply    replace a posted reply on the platform
    POST   /api/responder/events/{id}/delete-reply  remove a posted reply from the platform
    POST   /api/responder/events/{id}/save-answer   make the current reply the rule's answer
    GET    /api/responder/stats                 counters for the dashboard

Notifications
    GET    /api/responder/notifications
    POST   /api/responder/notifications/read    mark all (or given ids) as read

Testing + setup
    POST   /api/responder/simulate              inject a fake comment/DM through the full pipeline
    GET    /api/responder/setup                 webhook URLs + per-platform readiness
    POST   /api/responder/subscribe/{platform}  subscribe connected FB Pages to webhook events
"""
from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

import firebase_db
from firebase_db import FieldFilter
from config import (
    GRAPH_BASE,
    LINKEDIN_CLIENT_SECRET,
    META_APP_SECRET,
    META_WEBHOOK_VERIFY_TOKEN,
    PUBLIC_BACKEND_URL,
    TIKTOK_CLIENT_SECRET,
    utc_now,
)
from deps import get_current_user
from models import (
    AlwaysReviewUpdate,
    ApprovalDecision,
    BrandPersonaUpdate,
    ChannelModeUpdate,
    PersonaTestRequest,
    ReplyEditRequest,
    SimulateEventRequest,
    WorkspaceModeUpdate,
)
import rule_matcher
import responder_service as svc
from routers.social import engagement_account, get_user_accounts

router = APIRouter(prefix="/api/responder", tags=["auto-responder"])

MAX_LOGO_BYTES = 5 * 1024 * 1024
STATUS_FILTERS = {
    "all": None,
    "pending": ["pending_approval", "failed"],
    "replied": ["auto_replied", "approved_sent", "manual_sent", "liked"],
    "declined": ["declined"],
    "deleted": ["reply_deleted"],
    "ignored": ["ignored"],
    "skipped": ["skipped"],
}


def _uid(user: dict) -> str:
    return user["id"]


# --------------------------------------------------------------------------
# Persona
# --------------------------------------------------------------------------
def _actor(user: dict) -> str:
    return user.get("email") or user.get("username") or "You"


def _dedupe(values: list[str]) -> list[str]:
    """Drop blanks and duplicates (same words after normalizing), keeping order."""
    seen, out = set(), []
    for value in values:
        key = rule_matcher.normalize(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _clean_persona(payload: BrandPersonaUpdate) -> dict:
    data = payload.model_dump()
    for rule in data["rules"]:
        rule["id"] = rule["id"] or uuid.uuid4().hex[:10]
        rule["source"] = rule["source"] or "custom"
        rule["keywords"] = _dedupe(rule["keywords"])
        rule["phrases"] = _dedupe(rule["phrases"])
    data["escalation_keywords"] = _dedupe(data["escalation_keywords"])
    return data


@router.get("/persona")
async def get_persona(user: dict = Depends(get_current_user)):
    persona = await svc.get_persona(_uid(user), user)
    doc = await firebase_db.get(firebase_db.brand_personas.document(_uid(user)))
    data = {k: persona[k] for k in svc.PERSONA_FIELDS}
    data["updated_at"] = svc._iso(doc.get("updated_at")) if doc else None
    return {"persona": data}


@router.put("/persona")
async def save_persona(payload: BrandPersonaUpdate, user: dict = Depends(get_current_user)):
    # Only rules, fallback, escalation keywords and switches are written; older
    # fields in the document (the original FAQs among them) are left as they are.
    data = _clean_persona(payload)
    data["user_id"] = _uid(user)
    data["updated_at"] = utc_now()
    await firebase_db.upsert(
        firebase_db.brand_personas.document(_uid(user)), data, on_create={"created_at": utc_now()}
    )
    data.pop("user_id", None)
    data["updated_at"] = data["updated_at"].isoformat()
    return {"persona": data, "message": "Rules saved."}


@router.post("/persona/logo")
async def upload_logo(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from routers.content import _upload_to_local

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file (PNG, JPG or WebP).")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    url = await _upload_to_local(data, file.filename or "logo.png", "image", request)
    return {"url": url}


def _require_enabled(platform: str) -> None:
    """400 for a platform outside RESPONDER_PLATFORMS (its code stays, switched off)."""
    if not svc.platform_enabled(platform):
        raise HTTPException(status_code=400, detail=svc.platform_off_reason(platform) + ".")


def _test_channel(user_id: str, platform: str, channel_key: str = "") -> dict | None:
    """The channel a test or simulated comment arrives on: the one asked for, else
    the platform's first connected channel (None if the platform has none)."""
    channels = [c for c in svc.list_channels(user_id) if c["platform"] == platform]
    return next((c for c in channels if c["key"] == channel_key), None) or (channels[0] if channels else None)


@router.post("/persona/preview")
async def preview(payload: PersonaTestRequest, user: dict = Depends(get_current_user)):
    """Test box: what would happen to this comment, from the same code live comments use.

    Uses the editor's unsaved rules when sent, and the saved reply modes for the
    chosen channel. Nothing is stored or posted. The per-person and hourly
    limits depend on live traffic, so they are not part of the test.
    """
    _require_enabled(payload.platform)
    if payload.persona is not None:
        persona = payload.persona.model_dump()
        for i, rule in enumerate(persona["rules"]):
            rule["id"] = rule["id"] or f"draft-{i}"
    else:
        persona = await svc.get_persona(_uid(user), user)
    settings = await svc.get_mode_settings(_uid(user))
    channel = _test_channel(_uid(user), payload.platform, payload.channel_key)
    fake_event = {"platform": payload.platform, "account_ref": channel["account_ref"] if channel else None, "author": {}}
    v = svc.evaluate(persona, payload.text, payload.platform, ctx=svc.mode_context(settings, fake_event))
    rule_index = next((i for i, r in enumerate(persona["rules"]) if r.get("id") == v["rule_id"]), None)
    answers = (persona["rules"][rule_index]["answers"] if rule_index is not None
               else (persona.get("fallback") or {}).get("answers") or [])
    return {
        "action": v["action"],
        "reason": v["reason"],
        "outcome": v["outcome"],
        "rule_id": v["rule_id"],
        "rule_index": rule_index,
        "rule_name": v["rule_name"],
        "score": v["score"],
        "method": v["method"],
        "phrase": v["phrase"],
        "keywords": v["keywords"],
        "fuzzy_keywords": v["fuzzy_keywords"],
        "reply": v["reply"],
        "answer_count": len(answers) if v["reply"] else 0,
        "lang": v["lang"],
        "normalized": v["normalized"],
        "flagged_terms": v["screen"]["offensive_terms"],
        "sensitive_terms": v["screen"]["sensitive_terms"],
        "escalation_terms": v["escalated"],
        "scored": v["scored"][:5],
        "auto_reply_on": bool((persona.get("auto_reply") or {}).get("enabled")),
        "decision": v["decision"],
        "mode": v["mode"],
        "mode_source": v["mode_source"],
        "channel": channel,
        "no_match_action": v["no_match_action"],
        "paused": v["paused"],
        "force_review": v["force_review"],
    }


# --------------------------------------------------------------------------
# Reply modes
# --------------------------------------------------------------------------
async def _modes(user: dict) -> dict:
    persona = await svc.get_persona(_uid(user), user)
    settings = await svc.get_mode_settings(_uid(user), persona)
    workspace = svc.serialize_workspace(settings["workspace"])
    channels = []
    for c in svc.list_channels(_uid(user)):
        row = settings["channels"].get(c["key"]) or {}
        override = row.get("mode") if row.get("mode") in svc.MODES else "inherit"
        channels.append({**c, "mode": override, "effective": workspace["mode"] if override == "inherit" else override,
                         "updated_by": row.get("updated_by", ""), "updated_at": svc._iso(row.get("updated_at"))})
    return {
        **svc.platform_config(),
        "workspace": workspace,
        "channels": channels,
        "responder_on": bool((persona.get("auto_reply") or {}).get("enabled")),
        "always_review_rules": [r.get("name", "") for r in persona.get("rules") or []
                                if r.get("force_review") and r.get("enabled", True)],
    }


@router.get("/modes")
async def get_modes(user: dict = Depends(get_current_user)):
    return await _modes(user)


@router.put("/modes/workspace")
async def set_workspace_mode(payload: WorkspaceModeUpdate, user: dict = Depends(get_current_user)):
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    await svc.update_workspace_settings(_uid(user), fields, _actor(user))
    return await _modes(user)


@router.put("/modes/channels/{channel_key}")
async def set_channel_mode(channel_key: str, payload: ChannelModeUpdate, user: dict = Depends(get_current_user)):
    _require_enabled(channel_key.split(":", 1)[0])
    if not any(c["key"] == channel_key for c in svc.list_channels(_uid(user))):
        raise HTTPException(status_code=404, detail="That channel is not connected.")
    await svc.set_channel_mode(_uid(user), channel_key, payload.mode, _actor(user))
    return await _modes(user)


@router.get("/channel-health")
async def get_channel_health(user: dict = Depends(get_current_user)):
    import channel_health

    return {"channels": await channel_health.channel_health(_uid(user)), "checked_at": utc_now().isoformat()}


def _is_admin(user: dict) -> bool:
    from config import ADMIN_EMAIL

    return bool(user.get("is_admin")) or (user.get("email") or "").lower() == ADMIN_EMAIL


@router.get("/inbound-log")
async def get_inbound_log(platform: str = "", limit: int = 20, user: dict = Depends(get_current_user)):
    """Newest deliveries routed to this workspace. Deliveries no workspace could
    be matched to are shown to the admin only (they may belong to anyone)."""
    import inbound_log

    if platform and platform not in ("facebook", "instagram", "linkedin", "tiktok"):
        raise HTTPException(status_code=400, detail="Unknown platform.")
    admin = _is_admin(user)
    items = await inbound_log.recent(platform or None, user_id=_uid(user), include_unattributed=admin,
                                     limit=max(1, min(limit, 100)))
    return {"items": items, "count": len(items), "includes_unattributed": admin}


@router.post("/always-review")
async def always_review(payload: AlwaysReviewUpdate, user: dict = Depends(get_current_user)):
    accounts = await svc.set_always_review(_uid(user), payload.platform, payload.author_id,
                                           payload.name, payload.on, _actor(user))
    name = payload.name or "This account"
    return {
        "always_review_accounts": [{**a, "added_at": svc._iso(a.get("added_at"))} for a in accounts],
        "message": f"{name}'s comments will always wait for your review." if payload.on
        else f"{name} was removed from the always-review list.",
    }


@router.get("/gaps")
async def gaps(days: int = 30, user: dict = Depends(get_current_user)):
    persona = await svc.get_persona(_uid(user), user)
    return await svc.rule_gaps(_uid(user), persona, max(1, min(days, 90)))


# --------------------------------------------------------------------------
# Queue + activity
# --------------------------------------------------------------------------
def _own_events(user_id: str):
    return firebase_db.responder_events.where(filter=FieldFilter("user_id", "==", user_id))


def _own_notifications(user_id: str):
    return firebase_db.notifications.where(filter=FieldFilter("user_id", "==", user_id))


async def _list(user_id: str, statuses: list[str] | None, limit: int, platform: str | None = None):
    query = _own_events(user_id)
    if statuses:
        query = query.where(filter=FieldFilter("status", "in", statuses))
    if platform:
        query = query.where(filter=FieldFilter("platform", "==", platform))
    query = query.order_by("created_at", direction=firebase_db.DESCENDING).limit(max(1, min(limit, 200)))
    return [svc.serialize_event(doc) for doc in await firebase_db.fetch(query)]


@router.get("/queue")
async def queue(user: dict = Depends(get_current_user)):
    items = await _list(_uid(user), STATUS_FILTERS["pending"], 100)
    return {"items": items, "count": len(items)}


@router.get("/events")
async def events(status: str = "all", platform: str = "", limit: int = 100, user: dict = Depends(get_current_user)):
    if status not in STATUS_FILTERS:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(STATUS_FILTERS)}")
    items = await _list(_uid(user), STATUS_FILTERS[status], limit, platform or None)
    return {"items": items, "count": len(items)}


COUNTED_STATUSES = ("pending_approval", "failed", "auto_replied", "liked", "approved_sent",
                    "manual_sent", "declined", "reply_deleted", "ignored", "skipped")


@router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    # Count aggregations are billed per 1,000 matches, not per document.
    events = _own_events(_uid(user))
    *per_status, total, unread = await asyncio.gather(
        *(firebase_db.count(events.where(filter=FieldFilter("status", "==", s))) for s in COUNTED_STATUSES),
        firebase_db.count(events),
        firebase_db.count(_own_notifications(_uid(user)).where(filter=FieldFilter("read", "==", False))),
    )
    counts = dict(zip(COUNTED_STATUSES, per_status))
    return {
        "pending": counts.get("pending_approval", 0) + counts.get("failed", 0),
        "auto_replied": counts.get("auto_replied", 0),
        "liked": counts.get("liked", 0),
        "approved": counts.get("approved_sent", 0) + counts.get("manual_sent", 0),
        "declined": counts.get("declined", 0),
        "reply_deleted": counts.get("reply_deleted", 0),
        "ignored": counts.get("ignored", 0),
        "skipped": counts.get("skipped", 0),
        "total": total,
        "unread_notifications": unread,
    }


async def _mark_event_notifications_read(user_id: str, event_id: str) -> None:
    await firebase_db.update_where(
        _own_notifications(user_id)
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("read", "==", False)),
        {"read": True},
    )


@router.post("/events/{event_id}/accept")
async def accept(event_id: str, payload: ApprovalDecision | None = None, user: dict = Depends(get_current_user)):
    doc = await svc.accept(_uid(user), event_id, (payload.reply_text if payload else None), actor=_actor(user))
    await _mark_event_notifications_read(_uid(user), event_id)
    item = svc.serialize_event(doc)
    if item["status"] == "failed":
        raise HTTPException(status_code=502, detail=item["error"] or "The platform rejected the reply.")
    return {"item": item, "message": "Reply posted."}


@router.post("/events/{event_id}/decline")
async def decline(event_id: str, user: dict = Depends(get_current_user)):
    doc = await svc.decline(_uid(user), event_id)
    await _mark_event_notifications_read(_uid(user), event_id)
    return {"item": svc.serialize_event(doc), "message": "Suggestion discarded."}


@router.post("/events/{event_id}/reply")
async def manual_reply(event_id: str, payload: ApprovalDecision, user: dict = Depends(get_current_user)):
    doc = await svc.send_manual(_uid(user), event_id, payload.reply_text or "", actor=_actor(user))
    await _mark_event_notifications_read(_uid(user), event_id)
    item = svc.serialize_event(doc)
    if item["status"] == "failed":
        raise HTTPException(status_code=502, detail=item["error"] or "The platform rejected the reply.")
    return {"item": item, "message": "Reply posted."}


@router.post("/events/{event_id}/edit-reply")
async def edit_reply(event_id: str, payload: ReplyEditRequest, user: dict = Depends(get_current_user)):
    """Replace a posted reply. On any platform error the event is left unchanged (502)."""
    doc = await svc.edit_reply(_uid(user), event_id, payload.reply_text, _actor(user))
    item = svc.serialize_event(doc)
    return {"item": item, "warning": item["error"], "message": "Reply updated."}


@router.post("/events/{event_id}/delete-reply")
async def delete_reply(event_id: str, user: dict = Depends(get_current_user)):
    """Remove a posted reply. On any platform error the event is left unchanged (502)."""
    doc = await svc.delete_posted_reply(_uid(user), event_id, _actor(user))
    return {"item": svc.serialize_event(doc), "message": "Reply deleted."}


@router.post("/events/{event_id}/save-answer")
async def save_answer(event_id: str, user: dict = Depends(get_current_user)):
    result = await svc.save_as_answer(_uid(user), event_id)
    return {**result, "message": f"Saved as the answer for {result['rule_name']}."}


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
@router.get("/notifications")
async def notifications(unread_only: bool = False, user: dict = Depends(get_current_user)):
    query = _own_notifications(_uid(user))
    if unread_only:
        query = query.where(filter=FieldFilter("read", "==", False))
    query = query.order_by("created_at", direction=firebase_db.DESCENDING).limit(30)
    items = [{
        "id": n["id"],
        "type": n.get("type"),
        "title": n.get("title", ""),
        "body": n.get("body", ""),
        "event_id": n.get("event_id"),
        "read": bool(n.get("read")),
        "created_at": svc._iso(n.get("created_at")),
    } for n in await firebase_db.fetch(query)]
    unread = await firebase_db.count(_own_notifications(_uid(user)).where(filter=FieldFilter("read", "==", False)))
    return {"items": items, "unread": unread}


class MarkReadRequest(BaseModel):
    ids: list[str] | None = None


@router.post("/notifications/read")
async def mark_read(payload: MarkReadRequest | None = None, user: dict = Depends(get_current_user)):
    if payload and payload.ids:
        docs = await firebase_db.get_many(firebase_db.notifications, payload.ids)
        updated = await firebase_db.update_refs(
            (firebase_db.notifications.document(n["id"]) for n in docs
             if n.get("user_id") == _uid(user) and n.get("read") is False),
            {"read": True},
        )
    else:
        updated = await firebase_db.update_where(
            _own_notifications(_uid(user)).where(filter=FieldFilter("read", "==", False)), {"read": True}
        )
    return {"updated": updated}


# --------------------------------------------------------------------------
# Simulator
# --------------------------------------------------------------------------
@router.post("/simulate")
async def simulate(payload: SimulateEventRequest, user: dict = Depends(get_current_user)):
    """Run a fake inbound message through the REAL pipeline (AI, queue, notifications).

    Simulated events are clearly labelled and never call a platform API, so
    this is safe to use before any webhook is configured.
    """
    _require_enabled(payload.platform)
    external_id = f"sim_{uuid.uuid4().hex}"
    # Arrives on the platform's first connected channel, so that channel's mode
    # applies; each test name counts as a different person for the per-person limit.
    channel = _test_channel(_uid(user), payload.platform)
    event = {
        "platform": payload.platform,
        "kind": payload.kind,
        "external_id": external_id,
        "text": payload.text,
        "author": {"id": f"sim:{rule_matcher.normalize(payload.author_name) or 'customer'}", "name": payload.author_name},
        "post_id": payload.post_id or None,
        "account_ref": channel["account_ref"] if channel else None,
        "reply_target": {},
        "platform_timestamp": utc_now(),
        "simulated": True,
    }
    event_id = await svc.handle_new_event(_uid(user), event)
    doc = await firebase_db.get(firebase_db.responder_events.document(event_id))
    return {"item": svc.serialize_event(doc)}


# --------------------------------------------------------------------------
# Setup helpers
# --------------------------------------------------------------------------
async def _public_backend_url() -> str:
    """PUBLIC_BACKEND_URL (re-read from .env so a new tunnel URL shows without a
    restart), or a running local ngrok tunnel to port 8000 when it is unset/local."""
    import os
    from dotenv import dotenv_values

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    live = (dotenv_values(env_path).get("PUBLIC_BACKEND_URL") or PUBLIC_BACKEND_URL).strip().rstrip("/")
    if live.startswith("https://"):
        return live
    try:
        async with httpx.AsyncClient(timeout=1.5) as http:
            tunnels = (await http.get("http://127.0.0.1:4040/api/tunnels")).json().get("tunnels") or []
        for t in tunnels:
            if t.get("public_url", "").startswith("https://") and ":8000" in str((t.get("config") or {}).get("addr", "")):
                return t["public_url"].rstrip("/")
    except Exception:
        pass
    return PUBLIC_BACKEND_URL


@router.get("/setup")
async def setup(user: dict = Depends(get_current_user)):
    accounts = get_user_accounts(_uid(user))
    if "instagram" not in accounts and engagement_account(_uid(user), "instagram"):
        accounts["instagram"] = engagement_account(_uid(user), "instagram")
    public_url = await _public_backend_url()
    base = f"{public_url}/api/webhooks"
    return {
        "public_backend_url": public_url,
        "is_public_https": public_url.startswith("https://"),
        "tunnel_detected": public_url != PUBLIC_BACKEND_URL,
        # Every platform's setup is described below; only RESPONDER_PLATFORMS are shown.
        "platforms": {k: v for k, v in {
            "facebook": {
                "connected": "facebook" in accounts,
                "webhook_url": f"{base}/facebook",
                "verify_token_set": bool(META_WEBHOOK_VERIFY_TOKEN),
                "secret_set": bool(META_APP_SECRET),
                "fields": ["feed", "messages"],
                "can_subscribe": "facebook" in accounts,
                "subscribed": bool((accounts.get("facebook") or {}).get("webhooks_subscribed")),
            },
            "instagram": {
                "connected": "instagram" in accounts,
                "webhook_url": f"{base}/instagram",
                "verify_token_set": bool(META_WEBHOOK_VERIFY_TOKEN),
                "secret_set": bool(META_APP_SECRET),
                "fields": ["comments", "messages"],
                "can_subscribe": "instagram" in accounts,
                "subscribed": bool((accounts.get("instagram") or {}).get("webhooks_subscribed")),
            },
            "linkedin": {
                "connected": "linkedin" in accounts,
                "webhook_url": f"{base}/linkedin",
                "secret_set": bool(LINKEDIN_CLIENT_SECRET),
                "fields": ["ORGANIZATION_SOCIAL_ACTION_NOTIFICATIONS"],
                "note": "Requires LinkedIn Community Management API access for an organization page.",
            },
            "tiktok": {
                "connected": "tiktok" in accounts,
                "webhook_url": f"{base}/tiktok",
                "secret_set": bool(TIKTOK_CLIENT_SECRET),
                "note": "Comment replies need a TikTok API for Business token; TikTok has no DM reply API.",
            },
        }.items() if svc.platform_enabled(k)},
    }


@router.post("/subscribe/{platform}")
async def subscribe(platform: str, user: dict = Depends(get_current_user)):
    """Subscribe every connected Facebook Page to this app's webhook fields.

    Meta only delivers Page/Instagram events for Pages that have installed the
    app via POST /{page-id}/subscribed_apps. Instagram events flow through the
    linked Facebook Page, so both platforms use the same call.
    """
    _require_enabled(platform)
    if platform not in ("facebook", "instagram"):
        raise HTTPException(status_code=400, detail="Only Facebook and Instagram need an explicit subscription.")
    from routers.social import refresh_fb_pages_for_user, save_user_account

    accounts = await refresh_fb_pages_for_user(_uid(user))
    account = accounts.get(platform) or (accounts.get("facebook") if platform == "instagram" else None)
    if not account:
        raise HTTPException(status_code=400, detail=f"Connect {platform.title()} first.")
    pages = account.get("pages") or []
    if platform == "instagram":
        pages = [p for p in pages if p.get("instagram_business_id")] or pages
    if not pages:
        raise HTTPException(status_code=400, detail="No Facebook Pages were found on this connection.")

    # `feed` carries Page comments, `messages` carries Messenger + IG DMs.
    fields = "feed,messages"
    results = []
    async with httpx.AsyncClient(timeout=20.0) as http:
        for page in pages:
            resp = await http.post(
                f"{GRAPH_BASE}/{page['id']}/subscribed_apps",
                data={"subscribed_fields": fields, "access_token": page.get("access_token", "")},
            )
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:200]}
            ok = resp.status_code == 200 and body.get("success") is True
            error = "" if ok else ((body.get("error") or {}).get("message") or f"HTTP {resp.status_code}")
            results.append({"page_id": page["id"], "page_name": page.get("name"), "ok": ok, "error": error})

    if any(r["ok"] for r in results):
        account["webhooks_subscribed"] = True
        save_user_account(_uid(user), platform if platform in accounts else "facebook", account)
    if not any(r["ok"] for r in results):
        raise HTTPException(
            status_code=502,
            detail="Meta rejected the subscription: "
            + "; ".join(r["error"] for r in results)
            + ". Reconnect the account to grant pages_manage_metadata.",
        )
    return {"results": results}
