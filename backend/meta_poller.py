"""Polling fallback for Meta comments (Facebook Pages + Instagram Business).

While a Meta app is in Development mode, Meta does not deliver real comment
webhooks from the public. This poller fetches recent comments through the
Graph API and feeds each NEW one into the exact same handler the webhook route
uses (routers.webhooks._dispatch, with a Meta-shaped payload). Parsing,
self-comment skipping, owner routing, toxicity scoring, the approval queue,
auto-posting and the Activity log therefore behave identically.

    Facebook:  GET /{page-id}/feed?fields=comments{...}       (1 call per Page)
    Instagram: GET /{ig-user-id}/media?fields=comments_count   (1 call)
               GET /{media-id}/comments   only for posts whose comment count
                                          changed, plus a full rescan every 5 min

State lives in Firestore, so restarts never re-reply:
    meta_poll_seen   one doc per comment id already handled (TTL 45 days on expires_at)
    meta_poll_state  per account: seeded flag, IG username, comment counts

The FIRST pass for an account only SEEDS the store with its existing comments,
so old comments are never answered. Comments posted while the backend was
stopped are picked up on the next run after a restart.

Enable/disable with META_POLLING_ENABLED (and META_POLL_INTERVAL seconds) in
backend/.env. Turn it off once the app is Live and real webhooks arrive; the
event store also de-duplicates, so running both never replies twice.
"""
from __future__ import annotations

import asyncio
import time

import httpx

import firebase_db
import routers.social as social_store
from config import GRAPH_BASE, utc_now
from responder_service import platform_enabled
from routers.webhooks import _dispatch

GRAPH = GRAPH_BASE
FB_POSTS_PER_POLL = 10
IG_MEDIA_PER_POLL = 10
COMMENTS_PER_OBJECT = 50
IG_FULL_RESCAN_SECONDS = 300
RATE_LIMIT_CODES = {4, 17, 32, 613, 80001, 80002}
RATE_LIMIT_BACKOFF = 600
ERROR_LOG_EVERY = 600

seen = firebase_db.meta_poll_seen
state = firebase_db.meta_poll_state

_backoff_until: dict[str, float] = {}
_last_error_log: dict[str, float] = {}

# Per account ("page:<id>" / "ig:<id>"): last successful poll and last error,
# for the channel health indicator. In memory: empty again after a restart.
POLL_STATUS: dict[str, dict] = {}


def _mark(key: str, ok: bool, message: str = "") -> None:
    entry = POLL_STATUS.setdefault(key, {})
    if ok:
        entry["last_ok"] = utc_now()
    else:
        entry["last_error"], entry["last_error_at"] = message, utc_now()

# Firestore bills every document read, and a pass looks at up to ~500 comment
# ids per account every META_POLL_INTERVAL seconds. Ids and account state this
# process has already read or written are kept here, so the database is only
# asked about comments it has not seen since the last restart.
_seen_cache: set[str] = set()
_state_cache: dict[str, dict] = {}


async def _load_state(key: str) -> dict:
    if key not in _state_cache:
        _state_cache[key] = await firebase_db.get(state.document(key)) or {}
    return _state_cache[key]


async def _save_state(key: str, fields: dict) -> None:
    await firebase_db.upsert(state.document(key), fields)
    _state_cache[key] = {**_state_cache.get(key, {}), **fields}


def _log(msg: str) -> None:
    print(f"[POLLER] {msg}", flush=True)


def _log_error(key: str, msg: str) -> None:
    now = time.time()
    if now - _last_error_log.get(key, 0) >= ERROR_LOG_EVERY:
        _last_error_log[key] = now
        _log(msg)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
def collect_targets() -> tuple[dict[str, str], dict[str, str]]:
    """Return ({page_id: page_token}, {ig_user_id: page_token}) across all users.

    Each Page / IG account is polled once even if several users connected it;
    the webhook dispatcher then routes the comment to its owner.
    """
    pages: dict[str, str] = {}
    igs: dict[str, str] = {}
    for platforms in list(social_store.connected_accounts.values()):
        if not isinstance(platforms, dict):
            continue
        for key in ("facebook", "instagram"):
            acct = platforms.get(key)
            if not isinstance(acct, dict):
                continue
            entries = list(acct.get("pages") or [])
            if not entries and acct.get("page_id") and acct.get("page_access_token"):
                entries = [{"id": acct["page_id"], "access_token": acct["page_access_token"],
                            "instagram_business_id": acct.get("instagram_business_id")}]
            for page in entries:
                pid, token = str(page.get("id") or ""), page.get("access_token")
                if not (pid and token):
                    continue
                if key == "facebook":
                    pages.setdefault(pid, token)
                ig = page.get("instagram_business_id")
                if ig:
                    igs.setdefault(str(ig), token)
    return pages, igs


# ---------------------------------------------------------------------------
# Graph + store helpers
# ---------------------------------------------------------------------------
class GraphError(RuntimeError):
    def __init__(self, message: str, code=None):
        super().__init__(message)
        self.code = code


async def _graph(http: httpx.AsyncClient, path: str, token: str, **params) -> dict:
    resp = await http.get(f"{GRAPH}/{path}", params={**params, "access_token": token})
    try:
        body = resp.json()
    except Exception:
        raise GraphError(f"HTTP {resp.status_code} (non-JSON)")
    if "error" in body:
        err = body["error"]
        raise GraphError(err.get("message", "unknown error"), err.get("code"))
    return body


async def _claim_new(platform: str, comment_ids: list[str]) -> set[str]:
    """Mark ids as seen; return the ones that were NOT seen before."""
    if not comment_ids:
        return set()
    keys = {f"{platform}:{cid}": cid for cid in dict.fromkeys(comment_ids)}
    unknown = [k for k in keys if k not in _seen_cache]
    if not unknown:
        return set()
    existing = {d["id"] for d in await firebase_db.get_many(seen, unknown)}
    _seen_cache.update(existing)
    fresh = [k for k in unknown if k not in existing and firebase_db.valid_id(k)]
    if not fresh:
        return set()
    now = utc_now()
    doc = {"created_at": now, "expires_at": now + firebase_db.POLL_SEEN_TTL}

    async def claim(key: str) -> bool:
        try:
            await seen.document(key).create(doc)
            return True
        except firebase_db.AlreadyExists:
            return False  # a concurrent run claimed it first

    claimed = await asyncio.gather(*(claim(k) for k in fresh))
    _seen_cache.update(fresh)  # claimed here or by a concurrent run: seen either way
    return {keys[k] for k, ok in zip(fresh, claimed) if ok}


def _iso_to_unix(value: str | None) -> int:
    from routers.webhooks import _ts

    dt = _ts(value)
    return int(dt.timestamp()) if dt else int(time.time())


# ---------------------------------------------------------------------------
# Facebook Pages
# ---------------------------------------------------------------------------
async def poll_page(http: httpx.AsyncClient, page_id: str, token: str) -> int:
    key = f"page:{page_id}"
    body = await _graph(
        http, f"{page_id}/feed", token,
        fields=(f"id,comments.limit({COMMENTS_PER_OBJECT}).filter(stream).order(reverse_chronological)"
                "{id,message,from,created_time,parent{id}}"),
        limit=FB_POSTS_PER_POLL,
    )
    found: list[tuple[str, dict]] = []
    for post in body.get("data") or []:
        for c in (post.get("comments") or {}).get("data") or []:
            found.append((post["id"], c))

    st = await _load_state(key)
    new_ids = await _claim_new("facebook", [c["id"] for _, c in found])
    if not st.get("seeded"):
        await _save_state(key, {"seeded": True, "seeded_at": utc_now()})
        _log(f"Facebook Page {page_id}: seeded {len(found)} existing comment(s); only new ones will be answered")
        return 0

    handled = 0
    for post_id, c in reversed(found):  # oldest first
        if c["id"] not in new_ids:
            continue
        author = c.get("from") or {}
        if str(author.get("id")) == page_id or not c.get("message"):
            continue  # the Page's own comment/reply, or a sticker/photo-only comment
        payload = {"object": "page", "entry": [{"id": page_id, "time": int(time.time()), "changes": [{
            "field": "feed",
            "value": {
                "item": "comment", "verb": "add",
                "comment_id": c["id"], "post_id": post_id,
                "parent_id": (c.get("parent") or {}).get("id") or post_id,
                "message": c["message"],
                "from": {"id": author.get("id"), "name": author.get("name", "")},
                "created_time": _iso_to_unix(c.get("created_time")),
            },
        }]}]}
        _log(f"Facebook Page {page_id}: new comment {c['id']} from {author.get('name') or 'someone'}")
        await _dispatch("facebook", payload, source="poll")
        handled += 1
    return handled


# ---------------------------------------------------------------------------
# Instagram Business accounts
# ---------------------------------------------------------------------------
async def poll_instagram(http: httpx.AsyncClient, ig_id: str, token: str) -> int:
    key = f"ig:{ig_id}"
    st = await _load_state(key)
    username = st.get("username")
    if not username:
        username = (await _graph(http, ig_id, token, fields="username")).get("username", "")

    media = (await _graph(http, f"{ig_id}/media", token, fields="id,comments_count,timestamp",
                          limit=IG_MEDIA_PER_POLL)).get("data") or []
    counts = dict(st.get("counts") or {})
    full_scan = not st.get("seeded") or time.time() - float(st.get("full_scan_at") or 0) >= IG_FULL_RESCAN_SECONDS

    found: list[tuple[str, dict]] = []
    for m in media:
        mid, n = m["id"], int(m.get("comments_count") or 0)
        if not full_scan and counts.get(mid) == n:
            continue
        if n == 0 and not full_scan:
            counts[mid] = 0
            continue
        body = await _graph(
            http, f"{mid}/comments", token,
            fields="id,text,username,timestamp,from,replies{id,text,username,timestamp,from}",
            limit=COMMENTS_PER_OBJECT,
        )
        for c in body.get("data") or []:
            found.append((mid, c))
            for r in (c.get("replies") or {}).get("data") or []:
                found.append((mid, r))
        counts[mid] = n

    new_ids = await _claim_new("instagram", [c["id"] for _, c in found])
    update = {"username": username, "counts": counts}
    if full_scan:
        update["full_scan_at"] = time.time()
    if not st.get("seeded"):
        update.update({"seeded": True, "seeded_at": utc_now()})
        await _save_state(key, update)
        _log(f"Instagram @{username}: seeded {len(found)} existing comment(s); only new ones will be answered")
        return 0
    if full_scan or username != st.get("username") or counts != (st.get("counts") or {}):
        await _save_state(key, update)  # skipped when nothing changed: a write per pass adds up

    handled = 0
    for mid, c in sorted(found, key=lambda x: x[1].get("timestamp") or ""):
        if c["id"] not in new_ids:
            continue
        author = c.get("from") or {}
        author_id = str(author.get("id") or "")
        author_name = author.get("username") or c.get("username") or ""
        if author_id == ig_id or (username and author_name.lower() == username.lower()):
            continue  # our own reply (including the AI's) - never answer ourselves
        if not c.get("text"):
            continue
        payload = {"object": "instagram", "entry": [{"id": ig_id, "time": _iso_to_unix(c.get("timestamp")), "changes": [{
            "field": "comments",
            "value": {
                "id": c["id"],
                "text": c["text"],
                "from": {"id": author_id or f"username:{author_name}", "username": author_name},
                "media": {"id": mid},
            },
        }]}]}
        _log(f"Instagram @{username}: new comment {c['id']} from @{author_name or 'someone'}")
        await _dispatch("instagram", payload, source="poll")
        handled += 1
    return handled


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------
async def poll_once() -> int:
    """One polling pass over every connected Page and IG account. Never raises."""
    if firebase_db.INIT_ERROR:
        _log_error("database", f"Firestore unavailable, skipping poll: {firebase_db.INIT_ERROR}")
        return 0
    pages, igs = collect_targets()
    total = 0
    async with httpx.AsyncClient(timeout=25) as http:
        # Only platforms the AI Responder handles (RESPONDER_PLATFORMS) are polled.
        jobs = [("page", pid, tok, poll_page) for pid, tok in pages.items()] if platform_enabled("facebook") else []
        jobs += [("ig", igid, tok, poll_instagram) for igid, tok in igs.items()] if platform_enabled("instagram") else []
        for kind, ident, token, fn in jobs:
            key = f"{kind}:{ident}"
            if time.time() < _backoff_until.get(key, 0):
                continue
            try:
                total += await fn(http, ident, token)
                _mark(key, True)
            except GraphError as e:
                if e.code in RATE_LIMIT_CODES:
                    _backoff_until[key] = time.time() + RATE_LIMIT_BACKOFF
                    _log(f"{key}: Meta rate limit hit; pausing this account for {RATE_LIMIT_BACKOFF // 60} min")
                    _mark(key, False, f"Meta rate limit: paused for {RATE_LIMIT_BACKOFF // 60} min")
                elif e.code == 190:
                    _log_error(key, f"{key}: access token expired or revoked; reconnect Facebook in BrandAura")
                    _mark(key, False, "Access token expired or revoked: reconnect Facebook")
                else:
                    _log_error(key, f"{key}: Graph API error ({e.code}): {str(e)[:160]}")
                    _mark(key, False, f"Graph API error ({e.code}): {str(e)[:160]}")
            except Exception as e:
                _log_error(key, f"{key}: poll failed: {type(e).__name__}: {str(e)[:160]}")
                _mark(key, False, f"Poll failed: {type(e).__name__}: {str(e)[:160]}")
    return total


async def reset_seed(account_key: str | None = None) -> None:
    """Forget seeding (and seen ids) so the next pass re-seeds. For maintenance."""
    if account_key:
        await state.document(account_key).delete()
        _state_cache.pop(account_key, None)
        return
    await firebase_db.delete_where(state)
    await firebase_db.delete_where(seen)
    _state_cache.clear()
    _seen_cache.clear()
