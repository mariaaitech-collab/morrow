from fastapi import APIRouter, HTTPException
from typing import List
import httpx
import json
import os
from models import SocialAccount
from config import (
    FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, FACEBOOK_REDIRECT_URI,
    LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI,
    INSTAGRAM_CLIENT_ID, INSTAGRAM_CLIENT_SECRET, INSTAGRAM_REDIRECT_URI,
)

router = APIRouter(prefix="/api/social", tags=["social"])

TOKENS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "connected_accounts.json")

connected_accounts = {}


def _load_accounts():
    global connected_accounts
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r") as f:
                connected_accounts = json.load(f)
            print(f"[SOCIAL] Loaded {len(connected_accounts)} accounts from disk")
        except Exception as e:
            print(f"[SOCIAL] Failed to load accounts: {e}")
            connected_accounts = {}


def _save_accounts():
    try:
        with open(TOKENS_FILE, "w") as f:
            json.dump(connected_accounts, f, indent=2)
        print(f"[SOCIAL] Saved {len(connected_accounts)} accounts to disk")
    except Exception as e:
        print(f"[SOCIAL] Failed to save accounts: {e}")


_load_accounts()

PLATFORM_CONFIGS = {
    "facebook": {
        "auth_url_template": "https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&scope=pages_manage_posts,pages_read_engagement&response_type=code",
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
        "auth_url_template": "https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={redirect_uri}&scope=pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish&response_type=code",
        "client_id": INSTAGRAM_CLIENT_ID,
        "client_secret": INSTAGRAM_CLIENT_SECRET,
        "redirect_uri": INSTAGRAM_REDIRECT_URI,
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
    },
}


@router.get("/accounts", response_model=List[SocialAccount])
def get_accounts():
    accounts = []
    for platform, info in PLATFORM_CONFIGS.items():
        is_connected = platform in connected_accounts
        accounts.append(SocialAccount(
            platform=platform,
            account_name=connected_accounts.get(platform, {}).get("account_name", ""),
            connected=is_connected,
            auth_url=None if is_connected else info["auth_url_template"].format(
                client_id=info["client_id"],
                redirect_uri=info["redirect_uri"],
            ),
        ))
    return accounts


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
    data = resp.json()
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


@router.get("/callback/{platform}")
async def auth_callback(platform: str, code: str = ""):
    print(f"[SOCIAL] Callback for {platform}, code={'YES' if code else 'NO'}")
    if platform not in PLATFORM_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not supported")
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    try:
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
            if "name" in me_data:
                account_name = me_data["name"]

            pages = await _fetch_fb_pages(long_lived_token)
            print(f"[SOCIAL] Found {len(pages)} pages")

            if pages:
                first_page = pages[0]
                page_id = first_page.get("id")
                page_token = first_page.get("access_token")
                ig_info = first_page.get("instagram_business_account")
                if ig_info:
                    ig_business_id = ig_info.get("id")
                    print(f"[SOCIAL] Instagram Business Account ID: {ig_business_id}")

            connected_accounts[platform] = {
                "account_name": account_name,
                "access_token": long_lived_token,
                "page_id": page_id,
                "page_access_token": page_token,
                "instagram_business_id": ig_business_id,
            }

        elif platform == "linkedin":
            connected_accounts[platform] = {
                "account_name": account_name,
                "access_token": user_token,
            }

        _save_accounts()
        print(f"[SOCIAL] Saved {platform} account with page_id={page_id}, ig_id={ig_business_id}")

        return {"platform": platform, "status": "connected", "account_name": account_name}

    except Exception as e:
        print(f"[SOCIAL] Error for {platform}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to authorize {platform}: {str(e)}")


@router.delete("/disconnect/{platform}")
def disconnect_platform(platform: str):
    if platform not in connected_accounts:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not connected")
    del connected_accounts[platform]
    _save_accounts()
    return {"platform": platform, "status": "disconnected"}
