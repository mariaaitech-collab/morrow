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
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError

import mongodb
from config import SECRET_KEY, ALGORITHM, utc_now, ADMIN_EMAIL

TRIAL_DAYS = 30
PRO_PRICE = "$29/mo"


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
        await mongodb.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"trial_ends_at": fresh, "plan": "trial"}},
        )
        user["trial_ends_at"] = fresh
        user["plan"] = "trial"
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
    user = await mongodb.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return await _ensure_trial(user)


def compute_subscription(user: dict) -> dict:
    """Return a normalized subscription-status object for a user document."""
    now = utc_now()

    trial_ends = user.get("trial_ends_at")
    if trial_ends is not None and trial_ends.tzinfo is None:
        trial_ends = trial_ends.replace(tzinfo=now.tzinfo)

    subscribed = bool(user.get("subscribed"))
    sub_ends = user.get("subscription_ends_at")
    if sub_ends is not None and sub_ends.tzinfo is None:
        sub_ends = sub_ends.replace(tzinfo=now.tzinfo)

    plan = user.get("plan", "free")
    is_pro = subscribed and (sub_ends is None or sub_ends > now)

    trial_active = trial_ends is not None and trial_ends > now
    is_trialing = trial_active and not is_pro
    days_remaining = max(0, (trial_ends - now).days) if trial_ends else 0

    access_active = is_pro or trial_active

    return {
        "plan": "pro" if is_pro else ("trial" if is_trialing else "free"),
        "subscribed": is_pro,
        "is_pro": is_pro,
        "is_trialing": is_trialing,
        "trial_ends_at": trial_ends.isoformat() if trial_ends else None,
        "subscription_ends_at": sub_ends.isoformat() if sub_ends else None,
        "days_remaining": days_remaining,
        "access_active": access_active,
        "price": PRO_PRICE,
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
                "Your free trial has ended. To upgrade to BrandAura Pro ($29/mo), "
                "please contact our administration at meveryx@gmail.com with your "
                "registered email for manual activation and payment instructions."
            ),
        )
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Restrict an endpoint to the administrator account only."""
    if not user.get("is_admin") and user.get("email", "").lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user
