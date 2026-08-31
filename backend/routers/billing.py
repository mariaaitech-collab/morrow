"""Subscription & billing endpoints for the Free-Trial / Pro paywall.

Paid Pro plans are NOT purchased through an automated payment gateway. Instead,
the upgrade flow directs users to contact the administrator (meveryx@gmail.com)
who manually activates Pro via ``POST /api/admin/activate-user``. The simulated
``/billing/subscribe`` endpoint is retained only as a non-UI helper.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from config import utc_now
import mongodb
from deps import get_current_user, compute_subscription, require_admin

router = APIRouter(prefix="/api/billing", tags=["billing"])
admin_router = APIRouter(tags=["admin"])

TRIAL_DAYS = 30


class ActivateRequest(BaseModel):
    email: EmailStr


@router.get("/status")
async def billing_status(user: dict = Depends(get_current_user)):
    """Return the caller's current plan / trial / paywall status."""
    return compute_subscription(user)


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
    target = await mongodb.users.find_one({"email": email})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    now = utc_now()
    await mongodb.users.update_one(
        {"_id": target["_id"]},
        {
            "$set": {
                "subscribed": True,
                "plan": "pro",
                # Long activation window; admin can re-run to extend.
                "subscription_ends_at": now + timedelta(days=365),
                "trial_ends_at": now + timedelta(days=365),
            }
        },
    )
    updated = await mongodb.users.find_one({"_id": target["_id"]})
    return {
        **compute_subscription(updated),
        "message": f"{email} has been activated as BrandAura Pro.",
    }


@router.post("/subscribe")
async def subscribe(user: dict = Depends(get_current_user), plan: str = "pro"):
    """Simulate a successful $29/mo checkout and upgrade the account to Pro.

    Real integration: verify the payment intent / webhook here, then apply the
    same document update below.
    """
    if plan not in ("pro",):
        raise HTTPException(status_code=400, detail="Unsupported plan.")

    now = utc_now()
    await mongodb.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "subscribed": True,
                "plan": "pro",
                "subscription_ends_at": now + timedelta(days=30),
                "trial_ends_at": now + timedelta(days=TRIAL_DAYS),  # keep trial clock full
            }
        },
    )
    updated = await mongodb.users.find_one({"_id": user["_id"]})
    return {**compute_subscription(updated), "message": "Welcome to BrandAura Pro!"}


@router.post("/cancel")
async def cancel(user: dict = Depends(get_current_user)):
    """Cancel Pro. Access remains until the current period ends, then the
    user falls back to whatever trial window is still valid."""
    await mongodb.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"subscribed": False, "plan": "free"}},
    )
    updated = await mongodb.users.find_one({"_id": user["_id"]})
    return {**compute_subscription(updated), "message": "Pro cancelled. You keep access until your period ends."}
