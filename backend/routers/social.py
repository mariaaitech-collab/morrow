from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from typing import List
import httpx
import json
import os
import asyncio
from urllib.parse import urlencode
from models import SocialAccount
from deps import get_current_user
import mongodb
from config import (
    FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, FACEBOOK_REDIRECT_URI,
    LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI,
    INSTAGRAM_CLIENT_ID, INSTAGRAM_CLIENT_SECRET, INSTAGRAM_REDIRECT_URI,
    ADMIN_EMAIL, FRONTEND_URL,
)

router = APIRouter(prefix="/api/social", tags=["social"])

TOKENS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "connected_accounts.json")

# Per-user connected social accounts. Structure:
#   connected_accounts = { "<user_id>": { "<platform>": { ...account... } } }
# Accounts are ALWAYS scoped to their owner's user id so one user can never see
# another user's connected platforms (cross-user data leak).
connected_accounts = {}


def _user_accounts(user_id: str) -> dict:
    """Return the (mutable) account map for a single user id."""
    return connected_accounts.setdefault(user_id, {})


def get_user_accounts(user_id: str) -> dict:
    """Public helper: a copy of the given user's connected accounts."""
    return dict(connected_accounts.get(user_id, {}))


def _load_accounts():
    global connected_accounts
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                connected_accounts = data
            else:
                connected_accounts = {}
            print(f"[SOCIAL] Loaded {len(connected_accounts)} user(s) from disk")
        except Exception as e:
            print(f"[SOCIAL] Failed to load accounts: {e}")
            connected_accounts = {}


def _save_accounts():
    try:
        with open(TOKENS_FILE, "w") as f:
            json.dump(connected_accounts, f, indent=2)
        print(f"[SOCIAL] Saved {sum(len(v) for v in connected_accounts.values())} account(s) to disk")
    except Exception as e:
        print(f"[SOCIAL] Failed to save accounts: {e}")


_load_accounts()


def _migrate_legacy_flat_accounts():
    """Migrate the old flat {platform: account} file into the per-user layout.

    Legacy accounts (pre-multi-user) are bound to the administrator's user id so
    they stay usable by their likely owner without ever leaking to other users.
    """
    global connected_accounts
    if not connected_accounts:
        return
    # Detect the legacy flat layout: top-level keys are platform names.
    if any(k in ("facebook", "linkedin", "instagram") for k in connected_accounts):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        try:
            admin = loop.run_until_complete(mongodb.users.find_one({"email": ADMIN_EMAIL.lower()}))
            owner_id = str(admin["_id"]) if admin else "__legacy_orphan__"
            # Move only platform-shaped entries; drop any other junk.
            legacy = {k: v for k, v in connected_accounts.items() if isinstance(v, dict) and "access_token" in v}
            connected_accounts = {owner_id: legacy}
            _save_accounts()
            print(f"[SOCIAL] Migrated {len(legacy)} legacy account(s) to owner '{owner_id}'")
        except Exception as e:
            print(f"[SOCIAL] Legacy migration skipped: {e}")


_migrate_legacy_flat_accounts()

PLATFORM_CONFIGS = {
    "facebook": {
        "auth_url_template": "https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&scope=pages_show_list,pages_read_engagement,pages_manage_posts,business_management,instagram_basic,instagram_content_publish&response_type=code&auth_type=rerequest",
        "client_id": FACEBOOK_CLIENT_ID,
        "client_secret": FACEBOOK_CLIENT_SECRET,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
    },
    "linkedin": {
        "auth_url_template": "https://www.linkedin.com/oauth/v2/authorization?client_id={client_id}&redirect_uri={redirect_uri}&scope=openid+profile+w_member_social&response_type=code",
        "client_id": LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
    },
    "instagram": {
        "auth_url_template": "https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&scope=pages_show_list,pages_read_engagement,pages_manage_posts,business_management,instagram_basic,instagram_content_publish&response_type=code&auth_type=rerequest",
        "client_id": INSTAGRAM_CLIENT_ID,
        "client_secret": INSTAGRAM_CLIENT_SECRET,
        "redirect_uri": INSTAGRAM_REDIRECT_URI,
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
    },
}


@router.get("/accounts", response_model=List[SocialAccount])
def get_accounts(user: dict = Depends(get_current_user)):
    own = _user_accounts(str(user["_id"]))
    return [
        SocialAccount(
            platform=platform,
            account_name=own.get(platform, {}).get("account_name", ""),
            connected=platform in own,
            auth_url=None if platform in own else info["auth_url_template"].format(
                client_id=info["client_id"],
                redirect_uri=info["redirect_uri"],
            ),
        )
        for platform, info in PLATFORM_CONFIGS.items()
    ]


@router.get("/connect/{platform}")
def connect_platform(platform: str):
    if platform not in PLATFORM_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not supported")
    config = PLATFORM_CONFIGS[platform]
    if not config["client_id"]:
        raise HTTPException(
            status_code=500,
            detail=f"{platform.title()} client ID not configured. Add it to the .env file.",
        )
    auth_url = config["auth_url_template"].format(
        client_id=config["client_id"],
        redirect_uri=config["redirect_uri"],
    )
    return {"platform": platform, "auth_url": auth_url, "status": "ready"}


async def _exchange_code_for_token(platform: str, code: str) -> str:
    config = PLATFORM_CONFIGS[platform]

    if platform in ("facebook", "instagram"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                config["token_url"],
                params={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "redirect_uri": config["redirect_uri"],
                    "code": code,
                },
            )
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        raise Exception(data.get("error", {}).get("message", "Token exchange failed"))

    elif platform == "linkedin":
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                config["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config["redirect_uri"],
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                },
            )
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        raise Exception(data.get("error_description", "Token exchange failed"))

    raise Exception(f"Token exchange not implemented for {platform}")


async def _fetch_fb_pages(user_token: str) -> list:
    """Fetch Facebook Pages with their Page Access Tokens and Instagram Business Account IDs."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://graph.facebook.com/v18.0/me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account",
                "access_token": user_token,
            },
        )
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    print(f"CRITICAL DEBUG - META ACCOUNTS RESPONSE: HTTP {resp.status_code} {resp.text}")
    if "data" in data:
        return data["data"]
    print(f"[SOCIAL] Failed to fetch pages: {data}")
    return []


async def _extend_token(user_token: str) -> str:
    """Exchange short-lived token for a long-lived token (60 days)."""
    config = PLATFORM_CONFIGS["facebook"]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                config["token_url"],
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "fb_exchange_token": user_token,
                },
            )
        data = resp.json()
        if "access_token" in data:
            print(f"[SOCIAL] Extended token successfully")
            return data["access_token"]
    except Exception as e:
        print(f"[SOCIAL] Token extension failed (using short-lived): {e}")
    return user_token


async def refresh_fb_pages_for_user(user_id: str) -> dict:
    """Best-effort refresh of a user's FB/IG page data right before publishing.

    Re-fetches the FULL /me/accounts array (every authorized page, each with its
    own access_token and optional instagram_business_account id) from the stored
    USER access token and writes it back into the connection record. This heals
    legacy connections saved before multi-page support (page_id=null, or an
    account with no `pages` key) so 'publish to ALL pages' always has the truth.
    Never raises: on any failure it falls back to whatever is already stored and
    the caller surfaces a clear reconnect error if nothing usable remains.
    """
    own = _user_accounts(user_id)
    changed = False

    for platform in ("facebook", "instagram"):
        acct = own.get(platform)
        if not acct or not acct.get("access_token"):
            continue

        refreshed = []
        try:
            refreshed = await _fetch_fb_pages(acct["access_token"])
            print(f"[SOCIAL] refresh_fb_pages_for_user: {platform} fetched {len(refreshed)} page(s)")
        except Exception as e:
            print(f"[SOCIAL] refresh_fb_pages failed for {platform}/{user_id}: {e}")

        if refreshed:
            pages = [{
                "id": p.get("id"),
                "name": p.get("name"),
                "access_token": p.get("access_token"),
                "instagram_business_id": (p.get("instagram_business_account") or {}).get("id"),
            } for p in refreshed]
            fb_fallback = None
            ig_page = None
            for p in refreshed:
                if not fb_fallback:
                    fb_fallback = p
                if p.get("instagram_business_account"):
                    ig_page = p
                    break
            selected = ig_page or fb_fallback or {}
            acct["page_id"] = selected.get("id")
            acct["page_access_token"] = selected.get("access_token")
            ig_info = (ig_page or {}).get("instagram_business_account") or {}
            acct["instagram_business_id"] = ig_info.get("id")
            acct["pages"] = pages
            changed = True
            continue

        # Fallback: legacy single-page save (or already-saved page data).
        if acct.get("page_id") and acct.get("page_access_token"):
            acct["pages"] = [{
                "id": acct["page_id"],
                "name": acct.get("account_name", "Facebook Page"),
                "access_token": acct["page_access_token"],
                "instagram_business_id": acct.get("instagram_business_id"),
            }]
            changed = True

    if changed:
        _save_accounts()
    return dict(own)


def _dashboard_url(**params) -> str:
    """Build the frontend dashboard URL with query params for the callback."""
    return f"{FRONTEND_URL}/dashboard?{urlencode({k: v for k, v in params.items() if v is not None})}"


async def _resolve_callback_user(request: Request, access_token: str = "") -> dict:
    """Resolve the logged-in user from the Authorization header OR the query token.

    The OAuth callback may be reached via a full browser navigation (page-level
    redirect), in which case the JWT cannot go in an Authorization header — the
    frontend instead passes it as an ``access_token`` query parameter.
    """
    from deps import _decode_token, apply_dev_override

    token = ""
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = (access_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = _decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    user = await mongodb.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return await apply_dev_override(user)


@router.get("/callback/{platform}")
async def auth_callback(
    request: Request,
    platform: str,
    code: str = "",
    access_token: str = "",
):
    print(f"[SOCIAL] Callback for {platform}, code={'YES' if code else 'NO'}")

    def fail(error: str):
        return RedirectResponse(
            _dashboard_url(**{"connection_success": "false", "platform": platform, "error": error}),
            status_code=302,
        )

    if platform not in PLATFORM_CONFIGS:
        return fail("unsupported_platform")

    if not code:
        return fail("no_code")

    try:
        user = await _resolve_callback_user(request, access_token)
        user_token = await _exchange_code_for_token(platform, code)
        print(f"[SOCIAL] Got user token for {platform}")

        account_name = f"{platform}_user"
        pages = []
        page_token = None
        page_id = None
        ig_business_id = None

        if platform in ("facebook", "instagram"):
            long_lived_token = await _extend_token(user_token)

            me_resp = None
            async with httpx.AsyncClient(timeout=15.0) as client:
                me_resp = await client.get(
                    "https://graph.facebook.com/v18.0/me",
                    params={"fields": "name", "access_token": long_lived_token},
                )
            me_data = me_resp.json()
            print(f"CRITICAL DEBUG - META /me RESPONSE: HTTP {me_resp.status_code} {me_resp.text}")
            if "name" in me_data:
                account_name = me_data["name"]

            pages = await _fetch_fb_pages(long_lived_token)
            print(f"[SOCIAL] Found {len(pages)} pages")

            # ITERATE the ENTIRE /me/accounts array — never assume the IG
            # Business account lives on the first page. A user can authorize
            # several FB Pages; an Instagram Professional account is linked to
            # exactly ONE of them. We walk every page, prefer the one whose
            # `instagram_business_account` is not null, and only fall back to a
            # regular Facebook page when no IG-linked page exists.
            fb_fallback = None
            ig_page = None
            for p in pages:
                if not fb_fallback:
                    fb_fallback = p
                if p.get("instagram_business_account"):
                    ig_page = p
                    break

            selected = ig_page or fb_fallback
            if selected:
                page_id = selected.get("id")
                page_token = selected.get("access_token")
            if ig_page:
                ig_info = ig_page.get("instagram_business_account") or {}
                ig_business_id = ig_info.get("id")
                print(f"[SOCIAL] Instagram Business Account ID: {ig_business_id} (page {page_id})")

            # Save every authorized page (multi-page support) so the UI can
            # later let the user pick which Page to publish to.
            pages_saved = [
                {
                    "id": pg.get("id"),
                    "name": pg.get("name"),
                    "access_token": pg.get("access_token"),
                    "instagram_business_id": (pg.get("instagram_business_account") or {}).get("id"),
                }
                for pg in pages
            ]

            _user_accounts(str(user["_id"]))[platform] = {
                "account_name": account_name,
                "access_token": long_lived_token,
                "page_id": page_id,
                "page_access_token": page_token,
                "instagram_business_id": ig_business_id,
                "pages": pages_saved,
            }
            print(f"CRITICAL DEBUG - SAVING TO DB: {_user_accounts(str(user['_id']))[platform]}")

        elif platform == "linkedin":
            # The LinkedIn API REJECTS the hardcoded "urn:li:person:me" author.
            # Resolve the user's REAL profile id via OpenID userinfo (needs the
            # `openid profile` scopes we request) and persist it so publishing
            # can build `urn:li:person:{provider_account_id}`.
            provider_account_id = None
            lk_name = account_name
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    me_resp = await client.get(
                        "https://api.linkedin.com/v2/userinfo",
                        headers={"Authorization": f"Bearer {user_token}"},
                    )
                me_data = me_resp.json()
                if "sub" in me_data:
                    provider_account_id = me_data["sub"]
                if me_data.get("name"):
                    lk_name = me_data["name"]
                print(f"[SOCIAL] LinkedIn profile id={provider_account_id} name={lk_name}")
            except Exception as e:
                print(f"[SOCIAL] LinkedIn userinfo fetch failed: {e}")

            _user_accounts(str(user["_id"]))[platform] = {
                "account_name": lk_name,
                "access_token": user_token,
                "provider_account_id": provider_account_id,
            }

        _save_accounts()
        print(f"[SOCIAL] Saved {platform} account with page_id={page_id}, ig_id={ig_business_id}")

        return RedirectResponse(
            _dashboard_url(**{"connection_success": "true", "platform": platform}),
            status_code=302,
        )

    except HTTPException as e:
        print(f"[SOCIAL] Auth error for {platform}: {e.detail}")
        return fail("not_authenticated")
    except Exception as e:
        print(f"[SOCIAL] Error for {platform}: {e}")
        return fail("exchange_failed")


@router.delete("/disconnect/{platform}")
def disconnect_platform(platform: str, user: dict = Depends(get_current_user)):
    # HARD DISCONNECT: physically purge the ENTIRE platform record — the pages
    # array, access_token, page_access_token, instagram_business_id, everything.
    # A disconnected account must not linger (even as `{}` or an empty `pages`),
    # otherwise reconnect + self-heal refreshes resurrect stale OAuth data.
    uid = str(user["_id"])
    own = _user_accounts(uid)
    if platform not in own:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not connected")

    removed = own.pop(platform, None)
    # Prune the user entry entirely once they have zero platforms left, so the
    # JSON file never retains an empty shell for this user.
    if not own:
        connected_accounts.pop(uid, None)
    _save_accounts()
    print(f"[SOCIAL] Hard-disconnected {platform} for user {uid}; removed={{platforms: {len(removed or {})}}}")
    return {"platform": platform, "status": "disconnected"}
