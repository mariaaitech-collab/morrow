"""Shared FastAPI dependencies: authentication + subscription gating.

These power the 1-month free-trial / Pro paywall architecture:

  - get_current_user:    resolves the logged-in user (Bearer JWT) or 401s.
  - require_subscription: allows the request only while the user has an
                          ACTIVE trial OR an active Pro plan; otherwise it
                          raises 402 ("Upgrade to Pro ($29/mo)") so the
                          frontend can show the upgrade modal.
  - compute_subscription: pure helper returning the user's plan status,
                          reused by /auth/me and /billing/status.
"""
from datetime import timedelta, datetime

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError

import firebase_db
from config import SECRET_KEY, ALGORITHM, utc_now, ADMIN_EMAIL

TRIAL_DAYS = 30
PRO_PRICE = "$29/mo"
FREE_TOKENS_ON_SIGNUP = 3
TOKEN_NOT_AVAILABLE_MSG = (
    "You've used all your free tokens! Upgrade to Standard or Premium to keep creating content."
)

# Developer testing override: this ONE account is auto-topped-up and unlocked so
# the app can be tested without hitting token limits or paywalls. Strictly
# limited to this exact email — every other user keeps the normal 3-token/free
# trial behaviour. Change the value in built/type builds; never in production.
DEV_OVERRIDE_EMAIL = "maria.ai.tech@gmail.com"
DEV_OVERRIDE_TOKENS = 1000


def _decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def _ensure_trial(user: dict) -> dict:
    """Bootstrap a 30-day trial only for users who have none yet.

    A brand-new account (or a legacy account created before trial tracking
    existed) gets a fresh 30-day window. Crucially, this does NOT re-grant a
    trial to users whose window has genuinely expired and who are not on an
    active Pro plan -- those users must hit the 402 paywall and be activated
    by the administrator.
    """
    now = utc_now()
    te = user.get("trial_ends_at")
    if te is None and not user.get("subscribed"):
        fresh = now + timedelta(days=30)
        await firebase_db.users.document(user["id"]).update({"trial_ends_at": fresh, "plan": "trial"})
        user["trial_ends_at"] = fresh
        user["plan"] = "trial"
    return user


# Freemium token refresh: standard / free / trial users get their base free
# allowance topped back up on a rolling weekly period so the app stays usable
# without ever granting unlimited access. Paid plans keep their finite balance.
FREE_TOKENS_BASE = 3
FREE_TOKENS_RESET_HOURS = 24 * 7  # weekly reset

async def maybe_refresh_free_tokens(user: dict) -> dict:
    """Refresh a free-tier user's base token allowance on a weekly cadence.

    Only applies to users who are NOT on an active paid plan and NOT the
    (unlimited) admin. Their stored ``free_tokens`` is capped at the base
    allowance and refilled when the reset window has elapsed, preserving a
    standard, bounded free quota for everyday users.
    """
    email = (user.get("email") or "").lower()
    if email == ADMIN_EMAIL:
        return user  # admin stays unlimited via the dev override

    status = compute_subscription(user)
    if status.get("is_unlimited"):
        return user  # unlimited users always pass

    # Paid Standard / Premium users hold a finite balance they purchased; never
    # overwrite it with the free base allowance.
    if status.get("subscribed"):
        return user

    now = utc_now()
    reset_at = _coerce_dt(user.get("free_token_reset_at"))
    if reset_at is None or now >= reset_at:
        try:
            await firebase_db.users.document(user["id"]).update(
                {"free_tokens": FREE_TOKENS_BASE, "free_token_reset_at": now + timedelta(hours=FREE_TOKENS_RESET_HOURS)}
            )
            user["free_tokens"] = FREE_TOKENS_BASE
            user["free_token_reset_at"] = now + timedelta(hours=FREE_TOKENS_RESET_HOURS)
        except Exception as e:
            print(f"[TOKENS] Weekly free-token refresh failed for {email}: {e}")
    return user


async def get_current_user(request: Request) -> dict:
    """Return the authenticated user document, or raise 401."""
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(auth.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload.")
    user = await firebase_db.user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    user = await _ensure_trial(user)
    user = await maybe_refresh_free_tokens(user)
    return await apply_dev_override(user)


async def apply_dev_override(user: dict) -> dict:
    """Developer testing override — applies ONLY to DEV_OVERRIDE_EMAIL.

    Every time this specific user's profile is resolved (login, /auth/me, or any
    authenticated request via get_current_user), we top them up to 1000 free
    tokens and unlock the account so paywalls / token limits never block testing.

    Strict isolation: the email must match EXACTLY (case-insensitive). All other
    users pass through untouched and keep the standard 3-token / free-trial
    behaviour.
    """
    if (user.get("email") or "").lower() != DEV_OVERRIDE_EMAIL.lower():
        return user

    locks = {"free_tokens": DEV_OVERRIDE_TOKENS}

    # Normalize any date fields stored as ISO strings (legacy accounts) into
    # proper datetime objects so every serializer (/auth/me, /user/me,
    # compute_subscription) can safely format them.
    for field in ("created_at", "trial_ends_at", "subscription_ends_at"):
        value = user.get(field)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                locks[field] = value
                user[field] = value
            except ValueError:
                pass

    # Persist a real 1000-token top-up so the balance is visible and survives.
    # Skipped when nothing would change, so a request does not cost a write.
    try:
        if user.get("free_tokens") != DEV_OVERRIDE_TOKENS or len(locks) > 1:
            await firebase_db.users.document(user["id"]).update(locks)
        user["free_tokens"] = DEV_OVERRIDE_TOKENS
    except Exception as e:
        print(f"[DEV] Override top-up failed: {e}")

    # Session unlock: unlimited tokens + premium + admin bypass for this request
    # so every gated endpoint (tokens, subscription, admin) lets the dev through.
    user["is_unlimited"] = True
    user["plan"] = "premium"
    user["subscribed"] = True
    user["is_admin"] = True
    user["subscription_ends_at"] = None
    return user


def _coerce_dt(value):
    """Coerce a datetime or ISO string into a tz-aware datetime, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=utc_now().tzinfo)
    return value


def compute_subscription(user: dict) -> dict:
    """Return a normalized subscription-status object for a user document."""
    now = utc_now()

    trial_ends = _coerce_dt(user.get("trial_ends_at"))
    sub_ends = _coerce_dt(user.get("subscription_ends_at"))

    subscribed = bool(user.get("subscribed"))
    plan = user.get("plan", "free")
    # Paid plans (Standard / Premium / Pro) are all "subscribed"; only Pro is
    # unlimited (its holder never burns a token). Standard & Premium hold a
    # finite token allotment that is consumed per core action.
    is_paid = subscribed and (sub_ends is None or sub_ends > now)
    known_plans = ("standard", "premium", "pro", "starter", "plus", "enterprise")
    active_plan = plan if (plan in known_plans and is_paid) else None

    trial_active = trial_ends is not None and trial_ends > now
    is_trialing = trial_active and not is_paid
    days_remaining = max(0, (trial_ends - now).days) if trial_ends else 0

    access_active = is_paid or trial_active
    # Explicit session override (dev override) short-circuits every paywall;
    # otherwise only the "pro" or "enterprise" plan is truly unlimited.
    is_unlimited = bool(user.get("is_unlimited")) or active_plan in ("pro", "enterprise")
    resolved_plan = active_plan or ("trial" if is_trialing else "free")

    return {
        "plan": resolved_plan,
        "subscribed": is_paid,
        "is_pro": is_paid,
        "is_trialing": is_trialing,
        "is_unlimited": is_unlimited,
        "trial_ends_at": trial_ends.isoformat() if trial_ends else None,
        "subscription_ends_at": sub_ends.isoformat() if sub_ends else None,
        "days_remaining": days_remaining,
        "access_active": access_active,
        "price": PRO_PRICE,
        "free_tokens": remaining_tokens(user, {"is_unlimited": is_unlimited}),
    }


async def require_subscription(user: dict = Depends(get_current_user)) -> dict:
    """Gate for auto-scheduling / content-generation endpoints.

    Blocks the request (402) once the free trial has expired AND the user is
    not on an active Pro plan. The message directs users to manual admin
    activation (no automated payment gateway is used).
    """
    status = compute_subscription(user)
    if not status["access_active"]:
        raise HTTPException(
            status_code=402,
            detail=(
                "Your free trial has ended. To upgrade to Morrow Pro ($29/mo), "
                "please contact our administration at meveryx@gmail.com with your "
                "registered email for manual activation and payment instructions."
            ),
        )
    return user


def remaining_tokens(user: dict, subscription: dict | None = None) -> int:
    """Return how many tokens a user has left.

    Unlimited Pro users get a large sentinel. Standard / Premium / trial / free
    users all consume their stored ``free_tokens`` balance.
    """
    if subscription is None:
        subscription = compute_subscription(user)
    if subscription.get("is_unlimited"):
        return 2 ** 31 - 1  # effectively unlimited
    return int(user.get("free_tokens", 0))


async def require_token(user: dict = Depends(get_current_user)) -> dict:
    """Gate for token-consuming core actions (AI content, images, auto-posts).

    Unlimited Pro users pass through without limits. Everyone else (Standard,
    Premium, trial, free) must still have at least one token remaining,
    otherwise we return 402 so the frontend opens the Pricing Modal.
    """
    if remaining_tokens(user) > 0:
        return user
    raise HTTPException(status_code=402, detail=TOKEN_NOT_AVAILABLE_MSG)


async def deduct_token(user: dict) -> int:
    """Atomically spend one token for a non-Pro (finite-balance) user.

    Returns the number of tokens left after the deduction, or a large sentinel
    for unlimited Pro users. If a finite-balance user reaches zero we raise 402
    so the frontend can prompt an upgrade.
    """
    status = compute_subscription(user)
    if status.get("is_unlimited"):
        return remaining_tokens(user, status)

    left = await _spend_token(firebase_db.db.transaction(), firebase_db.users.document(user["id"]))
    if left is None:
        raise HTTPException(status_code=402, detail=TOKEN_NOT_AVAILABLE_MSG)
    user["free_tokens"] = left
    return left


@firebase_db.async_transactional
async def _spend_token(transaction, ref) -> int | None:
    """Take one token if the stored balance is above zero; returns what is left."""
    snap = await ref.get(transaction=transaction)
    balance = int((snap.to_dict() or {}).get("free_tokens", 0) or 0) if snap.exists else 0
    if balance <= 0:
        return None
    transaction.update(ref, {"free_tokens": balance - 1})
    return balance - 1


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Restrict an endpoint to the sole administrator account.

    Admin access is granted EXCLUSIVELY to the exact email in ADMIN_EMAIL
    (maria.ai.tech@gmail.com by default). Any other authenticated user —
    regardless of any stored ``is_admin`` flag — is rejected with 403.
    """
    if (user.get("email") or "").lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Forbidden: admin access required.")
    return user
