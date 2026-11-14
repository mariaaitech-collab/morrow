"""Channel health: can each connected channel actually receive comments, and
when did the last one arrive? So a dead channel looks broken, not just quiet.

    await channel_health(user_id) -> [{key, platform, name, status, headline,
                                       detail, method, last_event_at,
                                       last_delivery_at, checked_at}]

status: "ok"      comments can arrive (and the path was verified)
        "idle"    connected and able to receive, but nothing has arrived yet
        "broken"  comments cannot arrive; `detail` says why and what fixes it
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

import httpx

import firebase_db
from firebase_db import FieldFilter
import inbound_log
from config import (
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    META_POLL_INTERVAL,
    META_POLLING_ENABLED,
    PUBLIC_BACKEND_URL,
    utc_now,
)

# What LinkedIn requires before it will tell an app about comments. They come
# only for Company Page posts, through the Community Management API.
LINKEDIN_COMMENT_SCOPES = {
    "rw_organization_admin": "subscribe to Company Page comment notifications",
    "r_organization_social": "read Company Page comments",
    "w_organization_social": "reply as the Company Page",
}
INTROSPECT_TTL = 600  # seconds; token scopes rarely change
_introspect_cache: dict[str, tuple[float, dict]] = {}


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


async def linkedin_token_info(token: str | None) -> dict:
    """LinkedIn's own view of a token: {active, status, scopes, expires_at, error}."""
    if not token:
        return {"active": False, "status": "missing", "scopes": [], "expires_at": None, "error": ""}
    key = hashlib.sha256(token.encode()).hexdigest()  # never keep the token itself
    cached = _introspect_cache.get(key)
    if cached and time.time() - cached[0] < INTROSPECT_TTL:
        return cached[1]
    info = {"active": False, "status": "unknown", "scopes": [], "expires_at": None, "error": ""}
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                "https://www.linkedin.com/oauth/v2/introspectToken",
                data={"client_id": LINKEDIN_CLIENT_ID, "client_secret": LINKEDIN_CLIENT_SECRET, "token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        body = resp.json()
        expires = body.get("expires_at")
        info = {
            "active": bool(body.get("active")),
            "status": body.get("status") or ("active" if body.get("active") else "inactive"),
            "scopes": [s for s in (body.get("scope") or "").split(",") if s],
            "expires_at": datetime.fromtimestamp(expires, timezone.utc) if isinstance(expires, (int, float)) else None,
            "error": "" if resp.status_code == 200 else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
        return info  # not cached: try again next time
    _introspect_cache[key] = (time.time(), info)
    return info


async def _last_event(user_id: str, channel: dict) -> dict | None:
    """Newest real (not simulated) event that arrived on this channel."""
    query = (
        firebase_db.responder_events
        .where(filter=FieldFilter("user_id", "==", user_id))
        .where(filter=FieldFilter("platform", "==", channel["platform"]))
        .order_by("created_at", direction=firebase_db.DESCENDING)
        .limit(50)
    )
    for doc in await firebase_db.fetch(query):
        if doc.get("simulated"):
            continue
        same = (doc.get("channel_key") == channel["key"] or channel["account_ref"] is None
                or str(doc.get("account_ref") or "") == channel["account_ref"])
        if same:
            return {"at": doc.get("received_at") or doc.get("created_at"), "status": doc.get("status")}
    return None


def _meta_health(channel: dict) -> dict:
    import meta_poller

    webhooks = PUBLIC_BACKEND_URL.startswith("https://")
    methods = ([f"polling every {META_POLL_INTERVAL}s"] if META_POLLING_ENABLED else []) + (["webhooks"] if webhooks else [])
    method = " + ".join(methods) or "none"
    if not methods:
        return {"status": "broken", "method": method, "headline": "Not receiving comments",
                "detail": "Polling is off (META_POLLING_ENABLED=false) and there is no public https webhook URL, so nothing can deliver comments."}
    if not META_POLLING_ENABLED:
        return {"status": "idle", "method": method, "headline": "Waiting for webhooks",
                "detail": f"Comments arrive only if Meta delivers webhooks to {PUBLIC_BACKEND_URL}."}
    key = ("page:" if channel["platform"] == "facebook" else "ig:") + str(channel["account_ref"])
    st = meta_poller.POLL_STATUS.get(key, {})
    last_ok, last_error, error_at = st.get("last_ok"), st.get("last_error"), st.get("last_error_at")
    if last_error and (not last_ok or error_at > last_ok):
        return {"status": "broken", "method": method, "headline": "Not receiving comments",
                "detail": f"The last check failed: {last_error}", "checked_at": _iso(error_at)}
    if last_ok:
        return {"status": "ok", "method": method, "headline": "Receiving",
                "detail": "Checked for new comments successfully.", "checked_at": _iso(last_ok)}
    return {"status": "idle", "method": method, "headline": "Starting",
            "detail": f"Not checked yet since the server started; it runs every {META_POLL_INTERVAL}s."}


async def _linkedin_health(account: dict) -> dict:
    method = "webhook (Company Page notifications)"
    info = await linkedin_token_info(account.get("access_token"))
    if info["error"] and not info["active"]:
        return {"status": "broken", "method": method, "headline": "Could not check the connection",
                "detail": f"LinkedIn token check failed: {info['error']}"}
    if not info["active"]:
        return {"status": "broken", "method": method, "headline": "Not receiving comments",
                "detail": f"The LinkedIn connection is {info['status']}. Reconnect LinkedIn on the Channels page."}
    missing = [s for s in LINKEDIN_COMMENT_SCOPES if s not in info["scopes"]]
    if missing:
        needs = "; ".join(f"{s} ({LINKEDIN_COMMENT_SCOPES[s]})" for s in missing)
        return {"status": "broken", "method": method, "headline": "Cannot receive comments",
                "detail": ("LinkedIn only tells apps about comments on Company Page posts, through the Community "
                           f"Management API. This connection has {', '.join(info['scopes']) or 'no scopes'}; it is missing {needs}. "
                           "Morrow publishes to your personal profile, and LinkedIn gives apps no access to comments "
                           "there (r_member_social is closed to new apps).")}
    if not account.get("organization_ids"):
        return {"status": "idle", "method": method, "headline": "No Company Page linked",
                "detail": "The token can read Company Page comments, but no Page is linked to this connection yet. "
                          "Comments are matched by the subscribing member or the post until it is."}
    return {"status": "ok", "method": method, "headline": "Receiving",
            "detail": "Subscribed to Company Page comment notifications."}


def _tiktok_health(account: dict) -> dict:
    method = "webhook"
    refresh_expires = account.get("refresh_expires_at")
    if refresh_expires and time.time() >= float(refresh_expires):
        return {"status": "broken", "method": method, "headline": "Not receiving comments",
                "detail": "The TikTok connection has expired. Reconnect TikTok on the Channels page."}
    return {"status": "idle", "method": method, "headline": "Waiting for webhooks",
            "detail": "Comments arrive only if TikTok delivers them to this app's webhook."}


async def channel_health(user_id: str) -> list[dict]:
    import responder_service as svc
    from routers.social import get_user_accounts

    accounts = get_user_accounts(user_id)
    out = []
    for channel in svc.list_channels(user_id):
        platform = channel["platform"]
        if platform in ("facebook", "instagram"):
            health = _meta_health(channel)
        elif platform == "linkedin":
            health = await _linkedin_health(accounts.get("linkedin") or {})
        else:
            health = _tiktok_health(accounts.get("tiktok") or {})
        try:
            last = await _last_event(user_id, channel)
        except Exception as e:
            last, health["detail"] = None, f"{health.get('detail', '')} (Could not read the last event: {e})"
        last_delivery = await inbound_log.latest_at(platform, user_id)
        # A channel that can receive and has received is shown as such.
        if last and health["status"] == "idle":
            health = {**health, "status": "ok", "headline": "Receiving"}
        out.append({
            **channel,
            **health,
            "last_event_at": _iso(last["at"]) if last else None,
            "last_event_status": last["status"] if last else None,
            "last_delivery_at": last_delivery,
            "checked_at": health.get("checked_at") or _iso(utc_now()),
        })
    return out
