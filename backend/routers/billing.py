"""Subscription & billing endpoints for the Free-Trial / Pro paywall.

Paid Pro plans are NOT purchased through an automated payment gateway. Instead,
the upgrade flow directs users to contact the administrator (meveryx@gmail.com)
who manually activates Pro via ``POST /api/admin/activate-user``. The simulated
``/billing/subscribe`` endpoint is retained only as a non-UI helper.

In addition, a Freemium token system is in place: standard / premium upgrades
grant a fixed token allotment (50 / 150) that is consumed per core action, so
API usage stays capped even after paying.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from config import utc_now
import firebase_db
import limits
from deps import get_current_user, compute_subscription, require_admin

router = APIRouter(prefix="/api/billing", tags=["billing"])
admin_router = APIRouter(tags=["admin"])

TRIAL_DAYS = 30

# Per-plan one-time token allotment granted on a successful purchase.
PLAN_CONFIG = {
    "starter": {"tokens": 50, "days": 30, "price": "1,500 PKR", "price_range": "1,500 PKR"},
    "standard": {"tokens": 50, "days": 30, "price": "1,200 PKR", "price_range": "1,000 - 1,500 PKR"},
    "plus": {"tokens": 150, "days": 30, "price": "2,800 PKR", "price_range": "2,000 - 4,000 PKR"},
    "premium": {"tokens": 150, "days": 30, "price": "2,800 PKR", "price_range": "2,000 - 4,000 PKR"},
    "enterprise": {"tokens": 500, "days": 30, "price": "6,500 PKR", "price_range": "6,000+ PKR / Custom"},
    "pro": {"tokens": 500, "days": 30, "price": "6,500 PKR", "price_range": "6,000+ PKR / Custom"},
}


class ActivateRequest(BaseModel):
    email: EmailStr


@firebase_db.async_transactional
async def _apply_plan(transaction, ref, fields: dict, now, add_tokens: int = 0) -> None:
    """Write the plan fields; quota cycles stay anchored on the first activation date."""
    snap = await ref.get(transaction=transaction)
    current = snap.to_dict() or {}
    update = {**fields, "subscription_started_at": current.get("subscription_started_at") or now}
    if add_tokens:
        update["free_tokens"] = int(current.get("free_tokens", 0) or 0) + add_tokens
    transaction.update(ref, update)


async def _set_plan(user_id: str, fields: dict, now, add_tokens: int = 0) -> dict:
    ref = firebase_db.users.document(user_id)
    await _apply_plan(firebase_db.db.transaction(), ref, fields, now, add_tokens)
    return await firebase_db.get(ref)


class PaymentSuccessRequest(BaseModel):
    plan: str = Field(..., description="Purchased plan: 'starter', 'plus', 'enterprise', 'standard', or 'premium'")
    session_id: str | None = None
    transaction_id: str | None = None


@router.get("/status")
async def billing_status(user: dict = Depends(get_current_user)):
    """Return the caller's current plan / trial / paywall status."""
    return compute_subscription(user)


@router.get("/usage")
async def billing_usage(user: dict = Depends(get_current_user)):
    """Return the caller's 30-day quota/cost usage for the frontend UI."""
    usage = await limits.get_usage(user)
    return {
        "user": user.get("email"),
        "plan": user.get("plan", "free"),
        "usage": usage,
    }


@admin_router.post("/api/admin/activate-user")
async def admin_activate_user(
    payload: ActivateRequest,
    admin: dict = Depends(require_admin),
):
    """Manually flip a user to Pro.

    Restricted to the administrator account. Extends the user's access by a
    full year and marks them as subscribed so the paywall clears immediately.
    """
    email = payload.email.strip().lower()
    target = await firebase_db.user_by_email(email)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    now = utc_now()
    updated = await _set_plan(target["id"], {
        "subscribed": True,
        "plan": "pro",
        # Long activation window; admin can re-run to extend.
        "subscription_ends_at": now + timedelta(days=365),
        "trial_ends_at": now + timedelta(days=365),
    }, now)
    return {
        **compute_subscription(updated),
        "message": f"{email} has been activated as Morrow Pro.",
    }


@router.post("/subscribe")
async def subscribe(user: dict = Depends(get_current_user), plan: str = "pro"):
    """Keep the legacy route, but never grant a paid plan without verification."""
    raise HTTPException(
        status_code=501,
        detail="Automated checkout is not configured. Contact the administrator for manual activation.",
    )


@router.post("/success")
async def payment_success(payload: PaymentSuccessRequest, user: dict = Depends(get_current_user)):
    """Retain the old callback path without trusting client-declared payment."""
    raise HTTPException(
        status_code=501,
        detail="Payment verification is not configured. Contact the administrator for manual activation.",
    )


@router.post("/cancel")
async def cancel(user: dict = Depends(get_current_user)):
    """Cancel Pro. Access remains until the current period ends, then the
    user falls back to whatever trial window is still valid."""
    ref = firebase_db.users.document(user["id"])
    await ref.update({"subscribed": False, "plan": "free"})
    updated = await firebase_db.get(ref)
    return {**compute_subscription(updated), "message": "Pro cancelled. You keep access until your period ends."}
