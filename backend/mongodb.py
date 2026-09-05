"""MongoDB (Motor) layer for BrandAura users and SaaS activity history."""
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI, MONGO_DB

client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]

users = db.users
activities = db.activities
password_resets = db.password_resets
calendar_notes = db.calendar_notes


async def init_mongo():
    # Remove any legacy UNIQUE index on `username`. Display names are allowed
    # to repeat, and a unique constraint here silently blocks legitimate
    # registrations whose chosen name is already taken (returns a misleading
    # 400 "Email already registered").
    try:
        await users.drop_index("username_1")
    except Exception:
        pass
    await users.create_index("email", unique=True)
    await activities.create_index([("user_id", 1), ("created_at", -1)])
    # Partial unique: only enforce on real hashed tokens (legacy docs have none)
    await password_resets.create_index(
        "token_hash",
        unique=True,
        partialFilterExpression={"token_hash": {"$type": "string"}},
    )
    await password_resets.create_index("expires_at", expireAfterSeconds=0)


async def mongo_ok() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def fix_missing_trials():
    """Backfill a 30-day trial only for accounts that have no trial window yet.

    Runs once at startup so brand-new / legacy accounts (which predate trial
    tracking) get a valid window. It deliberately does NOT re-grant a trial to
    users whose window has already expired -- those users must hit the 402
    paywall and be activated manually by the administrator. Pro subscribers are
    left untouched.
    """
    now = datetime.now(timezone.utc)
    try:
        res = await users.update_many(
            {
                "subscribed": {"$ne": True},
                "$or": [
                    {"trial_ends_at": {"$exists": False}},
                    {"trial_ends_at": None},
                ],
            },
            {"$set": {"trial_ends_at": now + timedelta(days=30), "plan": "trial"}},
        )
        if res.modified_count:
            print(f"[DB] Bootstrapped trial window for {res.modified_count} existing user(s)")
    except Exception as e:
        print("fix_missing_trials error:", e)


async def fix_missing_tokens():
    """Backfill freemium tokens for accounts that don't have a balance yet.

    Runs once at startup so accounts created before the token system (and any
    that never received a grant) get the standard free-token allowance. Only
    users who have never been granted tokens are touched, so a depleted balance
    is never silently refilled.
    """
    from deps import FREE_TOKENS_ON_SIGNUP
    try:
        res = await users.update_many(
            {"free_tokens": {"$exists": False}},
            {"$set": {"free_tokens": FREE_TOKENS_ON_SIGNUP}},
        )
        if res.modified_count:
            print(f"[DB] Granted {FREE_TOKENS_ON_SIGNUP} free token(s) to {res.modified_count} existing user(s)")
    except Exception as e:
        print("fix_missing_tokens error:", e)