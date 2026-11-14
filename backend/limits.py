"""Usage-cycle enforcement + cost accounting for BrandAura.

Starter-plan cost baseline (fixed, do not change):
  - Image generation       : ~PKR 11 / image  (engine currently free; plan value)
  - Caption generation     : ~PKR  1 / post
  - Competitive/trend search: ~PKR  2 / post (Tavily, batched)
  - Hard cap               : 30 posts / month per Starter user
  - Max monthly API spend  : PKR 450 (30% of PKR 1,500 revenue)

Counters are tracked per billing cycle (rolling 30-day windows anchored on the
user's payment/subscription start date, NOT the calendar month) in the
``usage_cycles`` Firestore collection. Hard blocks always happen BEFORE any paid
external API call; every priced call is logged to ``cost_logs`` with an
estimated cost + running cycle total, and an alert fires if a user's estimated
cycle spend crosses PKR 450 even when their counted limits look fine.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException

from config import utc_now, ADMIN_EMAIL
import firebase_db

logger = logging.getLogger("brandora")
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Ceilings & cost baselines (Starter plan constants)
# ---------------------------------------------------------------------------
CYCLE_DAYS = 30
SOFT_LIMIT_RATIO = 0.80  # show an in-app warning at >=80% usage

STARTER_MAX_POSTS = 30
STARTER_MAX_IMAGES = 30
STARTER_MAX_CAPTIONS = 90     # 30 posts + room for a slim number of regenerations
STARTER_MAX_TAVILY = 21       # 21 Tavily credits/cycle (~7 full 3-platform runs)

MAX_INPUT_CHARS = 800          # hard reject for oversized request input
MAX_IMAGES_PER_REQUEST = 4     # 1..4 images allowed per single post
STARTER_IMAGE_SIZE = 1024      # images are locked to 1024x1024 for Starter tier

CAPTION_MAX_TOKENS = 400       # hard max_tokens param on every caption API call
ANALYSIS_MAX_TOKENS = 2048     # belt-and-braces cap on competitor/strategy output

# Estimated cost per unit (PKR), used for the audit log + PKR 450 alert.
IMAGE_COST_PKR = 11.0          # planning figure (Pollinations is free today)
CAPTION_COST_PKR = 1.0
TAVILY_CREDIT_COST_PKR = round(0.008 * 277.3, 2)   # $0.008/credit @ 277.3 PKR/USD
COST_ALERT_CEILING_PKR = 450.0                      # 30% of PKR 1,500 Starter revenue

# field -> (storage key on the cycle doc, hard limit, feature label, est cost)
LIMITS = {
    "posts":    {"key": "posts_used",          "limit": STARTER_MAX_POSTS,    "label": "posts",               "cost_pkr": 0.0},
    "images":   {"key": "images_used",         "limit": STARTER_MAX_IMAGES,   "label": "image generations",   "cost_pkr": IMAGE_COST_PKR},
    "captions": {"key": "captions_generated",  "limit": STARTER_MAX_CAPTIONS, "label": "caption generations", "cost_pkr": CAPTION_COST_PKR},
    "analysis": {"key": "analysis_used",       "limit": STARTER_MAX_TAVILY,   "label": "analysis lookups",    "cost_pkr": TAVILY_CREDIT_COST_PKR},
}

ANALYSIS_CACHE_TTL_DAYS = 4  # refresh competitor/trend data every ~4 days


def _fmt_date(dt):
    if dt is None:
        return "the next cycle"
    if isinstance(dt, str):
        dt = _coerce_dt(dt) or utc_now()
    try:
        return dt.strftime("%d %b %Y")
    except Exception:
        return "the next cycle"


def _coerce_dt(value):
    """Coerce a datetime or ISO string into a tz-aware datetime, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if hasattr(value, "tzinfo") and value.tzinfo is None:
        value = value.replace(tzinfo=utc_now().tzinfo)
    return value


def _zo(value):
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_exempt(user) -> bool:
    """The sole administrator (dev/admin override) is exempt from quotas."""
    return (user.get("email") or "").lower() == ADMIN_EMAIL or bool(
        user.get("is_admin") and user.get("is_unlimited")
    )


def _limit_msg(label, end_date):
    return (
        f"You've reached your limit for this feature. "
        f"Upgrade or wait until {_fmt_date(end_date)}."
    )


# ---------------------------------------------------------------------------
# Cycle resolution
# ---------------------------------------------------------------------------
async def get_cycle(user: dict) -> dict:
    """Return the user's active 30-day usage cycle doc, creating it on demand.

    Cycles are rolling 30-day windows anchored on the subscription/payment
    start date (falling back to account creation), so a user who subscribes
    mid-month does NOT reset on the 1st of the calendar month.
    """
    now = utc_now()
    anchor = user.get("subscription_started_at") or user.get("created_at") or now
    anchor = _coerce_dt(anchor) or now
    if anchor > now:
        anchor = now
    k = max(0, (now - anchor).days // CYCLE_DAYS)
    start = anchor + timedelta(days=k * CYCLE_DAYS)
    end = start + timedelta(days=CYCLE_DAYS)

    ref = firebase_db.usage_cycles.document(firebase_db.cycle_doc_id(user["id"], start))
    doc = await firebase_db.get(ref)
    if doc is not None:
        return doc

    fresh = {
        "user_id": user["id"],
        "cycle_start_date": start,
        "cycle_end_date": end,
        "posts_used": 0,
        "images_used": 0,
        "captions_generated": 0,
        "analysis_used": 0,
        "estimated_cost_pkr": 0.0,
        "last_updated": now,
    }
    try:
        await ref.create(fresh)
    except firebase_db.AlreadyExists:
        # A concurrent request created this cycle first; use theirs.
        doc = await firebase_db.get(ref)
        if doc is not None:
            return doc
    return {**fresh, "id": ref.id}


# ---------------------------------------------------------------------------
# Quota consumption (hard-block BEFORE any external API call)
# ---------------------------------------------------------------------------
async def check_available(user: dict, field: str, amount: int = 1) -> dict:
    """Non-consuming availability check; raises 402 if the feature is capped."""
    if _is_exempt(user):
        return {}
    cfg = LIMITS[field]
    cycle = await get_cycle(user)
    used = _zo(cycle.get(cfg["key"]))
    if used + amount > cfg["limit"]:
        raise HTTPException(
            status_code=402,
            detail=_limit_msg(cfg["label"], cycle.get("cycle_end_date")),
        )
    return {
        "used": used,
        "limit": cfg["limit"],
        "remaining": cfg["limit"] - used,
        "reset_date": _fmt_date(cycle.get("cycle_end_date")),
    }


async def consume(user: dict, field: str, amount: int = 1, action: str = "", endpoint: str = "") -> dict:
    """Atomically consume quota, log the estimated cost, and return usage info.

    Raises HTTP 402 (before any external call) when the cycle cap is hit. Every
    priced consumption is recorded to ``cost_logs`` with a running cycle total,
    and an internal alert fires if the running estimate crosses PKR 450.
    """
    if _is_exempt(user):
        return {}
    cfg = LIMITS[field]
    key = cfg["key"]
    limit = cfg["limit"]
    label = cfg["label"]
    cycle = await get_cycle(user)
    used0 = _zo(cycle.get(key))
    if used0 + amount > limit:
        raise HTTPException(status_code=402, detail=_limit_msg(label, cycle.get("cycle_end_date")))

    now = utc_now()
    updated = await _take_quota(
        firebase_db.db.transaction(), firebase_db.usage_cycles.document(cycle["id"]), key, amount, limit, now
    )
    if updated is None:
        raise HTTPException(status_code=402, detail=_limit_msg(label, cycle.get("cycle_end_date")))

    used = _zo(updated.get(key))
    remaining = limit - used
    pct = used / limit
    warning = None
    if remaining <= 0:
        warning = _limit_msg(label, updated.get("cycle_end_date"))
    elif pct >= SOFT_LIMIT_RATIO:
        warning = f"You've used {used} of {limit} {label} this cycle."

    info = {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "reset_date": _fmt_date(updated.get("cycle_end_date")),
        "warning": warning,
    }
    unit_cost = cfg.get("cost_pkr") or 0.0
    if action and unit_cost:
        await log_cost(user, action, endpoint, unit_cost * amount, info)
    return info


@firebase_db.async_transactional
async def _take_quota(transaction, ref, key: str, amount: int, limit: int, now):
    """Add `amount` to the counter unless that would pass `limit`; returns the updated cycle or None."""
    snap = await ref.get(transaction=transaction)
    if not snap.exists:
        return None
    cycle = snap.to_dict() or {}
    used = _zo(cycle.get(key)) + amount
    if used > limit:
        return None
    transaction.update(ref, {key: used, "last_updated": now})
    return {**cycle, key: used, "last_updated": now, "id": snap.id}


# ---------------------------------------------------------------------------
# Cost logging + PKR 450 alert
# ---------------------------------------------------------------------------
async def log_cost(user: dict, action: str, endpoint: str, cost_pkr: float, usage: dict = None) -> float:
    """Append one priced API call to the audit log with a running cycle total."""
    if _is_exempt(user):
        return 0.0
    cycle = await get_cycle(user)
    prev = float(cycle.get("estimated_cost_pkr", 0.0) or 0.0)
    now = utc_now()
    await firebase_db.usage_cycles.document(cycle["id"]).update(
        {"last_updated": now, "estimated_cost_pkr": firebase_db.Increment(cost_pkr)}
    )
    running = round(prev + cost_pkr, 2)
    await firebase_db.cost_logs.add({
        "user_id": user["id"],
        "email": user.get("email"),
        "action": action,
        "endpoint": endpoint,
        "cost_pkr": round(cost_pkr, 2),
        "running_cycle_cost_pkr": running,
        "cycle_end_date": cycle.get("cycle_end_date"),
        "created_at": now,
    })
    logger.info(
        "COST call user=%s action=%s endpoint=%s cost_pkr=%s running_pkr=%s",
        user.get("email"), action, endpoint, round(cost_pkr, 2), running,
    )
    if prev <= COST_ALERT_CEILING_PKR < running:
        logger.warning(
            "COST ALERT: user=%s running cycle cost PKR %.2f exceeded ceiling PKR %.2f "
            "— a usage limit is probably not enforcing correctly.",
            user.get("email"), running, COST_ALERT_CEILING_PKR,
        )
        try:
            await firebase_db.cost_alerts.add({
                "user_id": user["id"],
                "email": user.get("email"),
                "running_cycle_cost_pkr": running,
                "ceiling_pkr": COST_ALERT_CEILING_PKR,
                "created_at": now,
                "expires_at": now + firebase_db.COST_ALERT_TTL,
            })
        except Exception as e:
            logger.warning("Failed to persist cost alert: %s", e)
    return running


# ---------------------------------------------------------------------------
# Input-length guard (reject BEFORE any API spend)
# ---------------------------------------------------------------------------
def validate_input_len(value, field: str = "Input", max_len: int = MAX_INPUT_CHARS):
    if value is not None and len(value) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"Please shorten your {field.lower()} to {max_len} characters.",
        )


# ---------------------------------------------------------------------------
# Analysis-result cache (batch/reuse within a refresh window, free of quota)
# ---------------------------------------------------------------------------
def make_cache_key(parts) -> str:
    canonical = "|".join(str(p).strip() for p in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# The payload is model output of any shape, and Firestore can't store an array
# directly inside an array, so it is kept as JSON text.
def _payload(doc: dict):
    raw = doc.get("payload_json")
    return json.loads(raw) if raw else doc.get("payload")


async def get_cached_result(cache_key: str):
    doc = await firebase_db.get_by_id(firebase_db.analysis_cache, cache_key)
    if not doc:
        return None
    expires = doc.get("expires_at")
    if expires is not None and _coerce_dt(expires) <= utc_now():
        return None
    return {"payload": _payload(doc), "cached_at": doc.get("cached_at")}


async def get_expired_result(cache_key: str):
    """Return any stored result (even stale) so a capped user still gets data."""
    doc = await firebase_db.get_by_id(firebase_db.analysis_cache, cache_key)
    if not doc:
        return None
    return {"payload": _payload(doc), "cached_at": doc.get("cached_at")}


async def put_cached_result(cache_key: str, payload: dict) -> None:
    now = utc_now()
    await firebase_db.analysis_cache.document(cache_key).set({
        "key": cache_key,
        "payload_json": json.dumps(payload, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)),
        "cached_at": now,
        "expires_at": now + timedelta(days=ANALYSIS_CACHE_TTL_DAYS),
    })


# ---------------------------------------------------------------------------
# Usage summary (for /api/billing/usage)
# ---------------------------------------------------------------------------
async def get_usage(user: dict) -> dict:
    cycle = await get_cycle(user)
    out = {
        "cycle_start_date": _fmt_date(cycle.get("cycle_start_date")),
        "cycle_end_date": _fmt_date(cycle.get("cycle_end_date")),
        "estimated_cost_pkr": round(float(cycle.get("estimated_cost_pkr", 0.0) or 0.0), 2),
        "cost_ceiling_pkr": COST_ALERT_CEILING_PKR,
    }
    for field, cfg in LIMITS.items():
        used = _zo(cycle.get(cfg["key"]))
        out[field] = {
            "used": used,
            "limit": cfg["limit"],
            "remaining": max(0, cfg["limit"] - used),
            "pct": round((used / cfg["limit"]) * 100, 1) if cfg["limit"] else 0,
        }
    return out