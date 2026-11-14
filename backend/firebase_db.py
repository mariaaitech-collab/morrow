"""Firestore data layer for Morrow: the one place the database client is created.

The backend reaches Firestore through the Firebase Admin SDK with Application
Default Credentials, so Production-mode security rules (deny all client access)
never apply to it, and the browser never talks to the database directly.

Configure in backend/.env:
    FIREBASE_PROJECT_ID      optional; defaults to GOOGLE_CLOUD_PROJECT or
                             morrow-2916d
    FIRESTORE_DATABASE       optional; only for a named (non-default) database
    FIRESTORE_EMULATOR_HOST  e.g. 127.0.0.1:8080 to use the local emulator instead

Collections [document id]. Records copied from MongoDB keep their ObjectId hex
as the document id, so every stored user_id still points at its user.
    users              [auto id]                       accounts, plan, tokens, profile
    user_emails        [email_key(email)]              guarantees one account per email
    activities         [auto id]                       product-usage history
    password_resets    [sha256 of the token]           single-use reset links   (TTL)
    oauth_states       [state nonce]                   TikTok PKCE state         (TTL)
    calendar_notes     [auto id]
    usage_cycles       [cycle_doc_id(user, start)]     30-day quota counters
    cost_logs          [auto id]
    cost_alerts        [auto id]                                                 (TTL)
    analysis_cache     [cache key]
    brand_personas     [user id]                       auto-responder rules
    responder_events   [event_doc_id(user, platform, external id)]  inbound comments / DMs
    notifications      [auto id]                                                 (TTL)
    meta_poll_seen     ["platform:comment id"]                                   (TTL)
    meta_poll_state    ["page:<id>" / "ig:<id>"]

(TTL) collections carry an `expires_at` field. The TTL policies and the composite
indexes the queries need are declared in firestore.indexes.json at the repository
root: `firebase deploy --only firestore:indexes`.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import timedelta, timezone

from google.api_core.exceptions import AlreadyExists  # noqa: F401  (re-exported)
from google.cloud import firestore
from google.cloud.firestore import (  # noqa: F401  (re-exported for the routers)
    DELETE_FIELD,
    ArrayUnion,
    FieldFilter,
    Increment,
    async_transactional,
)

from config import FIREBASE_PROJECT_ID, FIRESTORE_DATABASE, utc_now

HERE = os.path.dirname(os.path.abspath(__file__))
DESCENDING = firestore.Query.DESCENDING
BATCH_SIZE = 400  # Firestore allows 500 writes per batch


class FirestoreUnavailable(RuntimeError):
    """Raised by every database call when the client could not be created."""


class _Unavailable:
    """Stands in for the client when it could not be created, so the app still
    starts (and /api/health answers) while each database call says why."""

    def __init__(self, reason: str):
        self._reason = reason

    def collection(self, _name):
        return self

    def __getattr__(self, _name):
        raise FirestoreUnavailable(self._reason)


def _make_client() -> firestore.AsyncClient:
    database = FIRESTORE_DATABASE or None
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        # The SDK routes to the emulator on this variable; it needs no credentials.
        return firestore.AsyncClient(project=FIREBASE_PROJECT_ID or "demo-morrow", database=database)

    import firebase_admin
    from firebase_admin import credentials, firestore_async

    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {"projectId": FIREBASE_PROJECT_ID},
        )
    return firestore_async.client(app, database)


try:
    db = _make_client()
    INIT_ERROR = ""
except Exception as e:
    INIT_ERROR = f"Firestore is not configured ({type(e).__name__}: {e}). Check Application Default Credentials and the project id."
    print(f"[DB] {INIT_ERROR}")
    db = _Unavailable(INIT_ERROR)

users = db.collection("users")
user_emails = db.collection("user_emails")
activities = db.collection("activities")
password_resets = db.collection("password_resets")
calendar_notes = db.collection("calendar_notes")

# Usage-cycle + cost controls
usage_cycles = db.collection("usage_cycles")
cost_logs = db.collection("cost_logs")
cost_alerts = db.collection("cost_alerts")
analysis_cache = db.collection("analysis_cache")

# OAuth state (TikTok PKCE verifier + connecting user), single-use.
oauth_states = db.collection("oauth_states")

# Auto-Responder
brand_personas = db.collection("brand_personas")      # one rule set per user
responder_events = db.collection("responder_events")  # every inbound comment / DM + its outcome
notifications = db.collection("notifications")        # in-app alerts (approval required, failures)
# Reply mode per scope: one "workspace" row per user (mode, no-match action,
# kill switch, always-review accounts) plus one row per channel override.
reply_mode_settings = db.collection("reply_mode_settings")
# Every inbound platform delivery and what became of it (accepted / dropped and
# why), so nothing is lost silently. TTL on expires_at.
inbound_log = db.collection("inbound_log")
# Posts this app published: post id -> owner, so a comment can be routed by the
# post it was made on. Doc id: sha256(platform|post id).
published_posts = db.collection("published_posts")

# Meta comment poller (meta_poller.py)
meta_poll_seen = db.collection("meta_poll_seen")
meta_poll_state = db.collection("meta_poll_state")

# How long records in TTL collections are kept.
NOTIFICATION_TTL = timedelta(days=90)
COST_ALERT_TTL = timedelta(days=30)
POLL_SEEN_TTL = timedelta(days=45)


# ---------------------------------------------------------------------------
# Document ids
# ---------------------------------------------------------------------------
def valid_id(doc_id) -> bool:
    """Whether a string can be a Firestore document id (ids from URLs are untrusted)."""
    return (isinstance(doc_id, str) and 0 < len(doc_id.encode()) <= 1500 and "/" not in doc_id
            and doc_id not in (".", "..") and not (doc_id.startswith("__") and doc_id.endswith("__")))


def email_key(email: str) -> str:
    """Id of an address's `user_emails` document (hashed, since an email may contain '/')."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def event_doc_id(user_id: str, platform: str, external_id: str) -> str:
    """One document per inbound message per workspace, so a webhook retry can't add a second."""
    return hashlib.sha256(f"{user_id}|{platform}|{external_id}".encode()).hexdigest()[:32]


def cycle_doc_id(user_id: str, start) -> str:
    """One usage-cycle document per user per 30-day window."""
    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc)
    return f"{user_id}_{start.strftime('%Y%m%dT%H%M%S%f')}"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def as_dict(snap) -> dict | None:
    """A snapshot as a plain dict with its document id under "id" (None if missing)."""
    if snap is None or not snap.exists:
        return None
    return {**(snap.to_dict() or {}), "id": snap.id}


async def get(ref) -> dict | None:
    return as_dict(await ref.get())


async def get_by_id(collection, doc_id) -> dict | None:
    """Fetch by id; an id Firestore can't hold is simply not found."""
    if not valid_id(doc_id):
        return None
    return await get(collection.document(doc_id))


async def first(query) -> dict | None:
    for snap in await query.limit(1).get():
        return as_dict(snap)
    return None


async def fetch(query) -> list[dict]:
    return [as_dict(snap) for snap in await query.get()]


async def count(query) -> int:
    result = await query.count().get()
    return int(result[0][0].value) if result else 0


async def get_many(collection, ids) -> list[dict]:
    """Existing documents among `ids` (invalid ids are skipped)."""
    refs = [collection.document(i) for i in dict.fromkeys(ids) if valid_id(i)]
    if not refs:
        return []
    return [as_dict(snap) async for snap in db.get_all(refs) if snap.exists]


async def user_by_email(email: str) -> dict | None:
    if not email:
        return None
    return await first(users.where(filter=FieldFilter("email", "==", email.strip().lower())))


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
async def upsert(ref, fields: dict, on_create: dict | None = None) -> None:
    """Create or update a document. Each top-level field in `fields` is replaced
    whole (nested maps are not merged); `on_create` is written only when the
    document is new."""
    if not on_create:
        await ref.set(fields, merge=list(fields))
        return

    @async_transactional
    async def _write(transaction):
        if (await ref.get(transaction=transaction)).exists:
            transaction.update(ref, fields)
        else:
            transaction.set(ref, {**on_create, **fields})

    await _write(db.transaction())


async def update_refs(refs, fields: dict) -> int:
    refs = list(refs)
    for i in range(0, len(refs), BATCH_SIZE):
        batch = db.batch()
        for ref in refs[i:i + BATCH_SIZE]:
            batch.update(ref, fields)
        await batch.commit()
    return len(refs)


async def delete_refs(refs) -> int:
    refs = list(refs)
    for i in range(0, len(refs), BATCH_SIZE):
        batch = db.batch()
        for ref in refs[i:i + BATCH_SIZE]:
            batch.delete(ref)
        await batch.commit()
    return len(refs)


async def update_where(query, fields: dict) -> int:
    """Apply `fields` to every document the query matches; returns how many."""
    return await update_refs([snap.reference for snap in await query.get()], fields)


async def delete_where(query) -> int:
    """Delete every document the query matches, in batches; returns how many."""
    deleted = 0
    while True:
        snaps = await query.limit(BATCH_SIZE).get()
        if not snaps:
            return deleted
        deleted += await delete_refs(snap.reference for snap in snaps)
        if len(snaps) < BATCH_SIZE:
            return deleted


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
async def firestore_ok() -> tuple[bool, str]:
    if INIT_ERROR:
        return False, INIT_ERROR
    try:
        await asyncio.wait_for(users.limit(1).get(), timeout=15)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:300]}"


async def backfill_users() -> None:
    """One pass over `users` at startup (Firestore can't query for a missing field).

    - A 30-day trial only for accounts that have no trial window yet. It does
      NOT re-grant a trial to users whose window has already expired; those
      must hit the 402 paywall and be activated by the administrator. Pro
      subscribers are left untouched.
    - The sign-up token allowance for accounts that were never granted tokens,
      so a depleted balance is never silently refilled.
    """
    from deps import FREE_TOKENS_ON_SIGNUP

    now = utc_now()
    trials, tokens, writes = 0, 0, []
    try:
        async for snap in users.stream():
            data = snap.to_dict() or {}
            fields = {}
            if data.get("subscribed") is not True and data.get("trial_ends_at") is None:
                fields.update({"trial_ends_at": now + timedelta(days=30), "plan": "trial"})
                trials += 1
            if "free_tokens" not in data:
                fields["free_tokens"] = FREE_TOKENS_ON_SIGNUP
                tokens += 1
            if fields:
                writes.append((snap.reference, fields))
        for i in range(0, len(writes), BATCH_SIZE):
            batch = db.batch()
            for ref, fields in writes[i:i + BATCH_SIZE]:
                batch.update(ref, fields)
            await batch.commit()
        if trials:
            print(f"[DB] Bootstrapped trial window for {trials} existing user(s)")
        if tokens:
            print(f"[DB] Granted {FREE_TOKENS_ON_SIGNUP} free token(s) to {tokens} existing user(s)")
    except Exception as e:
        print("backfill_users error:", e)
