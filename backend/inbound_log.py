"""Inbound delivery log: every webhook (and polled) payload and what became of it.

One document per delivery item in `inbound_log`, kept INBOUND_LOG_TTL:

    platform     facebook | instagram | linkedin | tiktok
    source       webhook | challenge | poll | replay
    outcome      accepted     stored as a responder event (event_id set)
                 duplicate    already stored (a platform retry)
                 dropped      not a comment we answer (reason says why)
                 unattributed no Morrow workspace could be matched; kept here only
                 rejected     signature or body invalid
                 challenge    the platform validated the webhook URL
                 error        parsing or processing failed
    reason       human-readable why
    user_id      the workspace it was routed to (None when unattributed)
    event_id     the responder event it became, if any
    raw          the payload as JSON text (trimmed)

Nothing that reaches a webhook route can disappear without a line here, so a
quiet channel can be told apart from a broken one.
"""
from __future__ import annotations

import json
from datetime import timedelta

import firebase_db
from firebase_db import FieldFilter
from config import utc_now

INBOUND_LOG_TTL = timedelta(days=30)
RAW_LIMIT = 8000
# "ignored": the platform is not in RESPONDER_PLATFORMS, so nothing was stored.
OUTCOMES = ("accepted", "duplicate", "dropped", "unattributed", "rejected", "challenge", "error", "ignored")


def _raw_text(raw) -> str | None:
    if raw is None:
        return None
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    return text[:RAW_LIMIT]


async def record(platform: str, outcome: str, reason: str, *, raw=None, source: str = "webhook",
                 user_id: str | None = None, event_id: str | None = None) -> None:
    """Write one log entry. Never raises: logging must not break ingestion."""
    now = utc_now()
    print(f"[INBOUND] {platform} {source} {outcome}: {reason}" + (f" (event {event_id})" if event_id else ""), flush=True)
    try:
        await firebase_db.inbound_log.add({
            "platform": platform,
            "source": source,
            "outcome": outcome if outcome in OUTCOMES else "error",
            "reason": (reason or "")[:500],
            "user_id": user_id,
            "event_id": event_id,
            "raw": _raw_text(raw),
            "received_at": now,
            "expires_at": now + INBOUND_LOG_TTL,
        })
    except Exception as e:
        print(f"[INBOUND] could not write the log entry: {e}", flush=True)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


async def recent(platform: str | None, *, user_id: str | None, include_unattributed: bool,
                 limit: int = 20, scan: int = 500) -> list[dict]:
    """The newest entries for one workspace (plus unattributed ones when allowed).

    Filters on one field only and sorts here, so no composite index is needed.
    """
    query = firebase_db.inbound_log
    if platform:
        query = query.where(filter=FieldFilter("platform", "==", platform))
    rows = await firebase_db.fetch(query.limit(scan))
    visible = [r for r in rows
               if (user_id and r.get("user_id") == user_id) or (include_unattributed and not r.get("user_id"))]
    visible.sort(key=lambda r: r.get("received_at") or utc_now(), reverse=True)
    return [{
        "id": r["id"],
        "platform": r.get("platform"),
        "source": r.get("source"),
        "outcome": r.get("outcome"),
        "reason": r.get("reason", ""),
        "user_id": r.get("user_id"),
        "event_id": r.get("event_id"),
        "raw": r.get("raw"),
        "received_at": _iso(r.get("received_at")),
    } for r in visible[:limit]]


async def latest_at(platform: str, user_id: str) -> object | None:
    """When the newest delivery for this workspace on `platform` arrived (any outcome)."""
    rows = await recent(platform, user_id=user_id, include_unattributed=False, limit=1)
    return rows[0]["received_at"] if rows else None
