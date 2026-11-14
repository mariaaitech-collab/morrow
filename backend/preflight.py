"""BrandAura preflight checklist (never prints secret values).

    .venv\\Scripts\\python.exe preflight.py

Checks .env keys, connected accounts + live Meta permissions, the ngrok
tunnel, and whether the backend / frontend dev servers are up.
"""
from __future__ import annotations

import json
import os
import sys

import httpx
from dotenv import dotenv_values

from config import GRAPH_BASE

HERE = os.path.dirname(os.path.abspath(__file__))
OK, WARN, MISS = "[ OK ]", "[WARN]", "[MISS]"
ENGAGEMENT_PERMS = [
    "pages_manage_engagement", "pages_read_user_content", "pages_manage_metadata",
    "pages_messaging", "instagram_manage_comments", "instagram_manage_messages",
]


def line(tag, label, detail=""):
    print(f"  {tag} {label}" + (f"  - {detail}" if detail else ""))


def check_env(env: dict) -> None:
    print("\nEnvironment (backend/.env)")
    required = {
        "SECRET_KEY": "JWT signing key",
        "GEMINI_API_KEY": "Content Studio captions + strategy",
        "FACEBOOK_CLIENT_ID": "Meta app id (Facebook + Instagram)",
        "FACEBOOK_CLIENT_SECRET": "Meta app secret, also signs webhooks",
        "TIKTOK_CLIENT_KEY": "TikTok client key",
        "TIKTOK_CLIENT_SECRET": "TikTok client secret",
        "META_WEBHOOK_VERIFY_TOKEN": "Paste the same value in Meta App Dashboard > Webhooks",
    }
    for key, why in required.items():
        line(OK if env.get(key) else MISS, key, "" if env.get(key) else why)
    if env.get("FIRESTORE_EMULATOR_HOST"):
        line(OK, "FIRESTORE_EMULATOR_HOST", f"using the local emulator at {env['FIRESTORE_EMULATOR_HOST']}")
    else:
        project_id = (env.get("FIREBASE_PROJECT_ID") or env.get("GOOGLE_CLOUD_PROJECT")
                      or "morrow-2916d")
        line(OK, "Firestore project", project_id)
        line(OK, "Firestore credentials", "Application Default Credentials")
    url = env.get("PUBLIC_BACKEND_URL") or "http://localhost:8000"
    if url.startswith("https://"):
        line(OK, "PUBLIC_BACKEND_URL", url)
    else:
        line(WARN, "PUBLIC_BACKEND_URL", f"{url} is not public HTTPS; platforms cannot deliver webhooks to it")


def check_accounts() -> None:
    print("\nConnected accounts (connected_accounts.json)")
    try:
        data = json.load(open(os.path.join(HERE, "connected_accounts.json"), encoding="utf-8"))
    except Exception as e:
        line(MISS, "connected_accounts.json", str(e))
        return
    for uid, platforms in data.items():
        if not platforms:
            continue
        for platform, acct in platforms.items():
            label = f"user {uid[-6:]} {platform} ({acct.get('account_name', '?')})"
            if platform != "facebook":
                line(OK if acct.get("access_token") else MISS, label, "token stored")
                continue
            try:
                r = httpx.get(f"{GRAPH_BASE}/me/permissions",
                              params={"access_token": acct.get("access_token", "")}, timeout=15)
                body = r.json()
            except Exception as e:
                line(WARN, label, f"could not reach Meta: {e}")
                continue
            if "error" in body:
                line(MISS, label, "token invalidated by Facebook. Disconnect and reconnect Facebook")
                continue
            granted = {p["permission"] for p in body.get("data", []) if p.get("status") == "granted"}
            missing = [p for p in ENGAGEMENT_PERMS if p not in granted]
            ig = "IG linked" if acct.get("instagram_business_id") else "no IG business account"
            if missing:
                line(WARN, label, f"token valid, {ig}, but missing {', '.join(missing)}. Reconnect Facebook")
            else:
                line(OK, label, f"token valid, {ig}, comment/DM permissions granted")


def check_tunnel() -> str | None:
    print("\nPublic tunnel")
    try:
        tunnels = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=1.5).json().get("tunnels") or []
        for t in tunnels:
            if t.get("public_url", "").startswith("https://"):
                line(OK, "ngrok tunnel", f"{t['public_url']} -> {(t.get('config') or {}).get('addr')}")
                return t["public_url"]
        line(WARN, "ngrok", "running but no https tunnel found")
    except Exception:
        line(MISS, "ngrok", "not running. Install ngrok, run: ngrok http 8000")
    return None


def check_servers() -> None:
    print("\nServers")
    for label, url in (("Backend  http://localhost:8000", "http://127.0.0.1:8000/api/health"),
                       ("Frontend http://localhost:5173", "http://127.0.0.1:5173/")):
        try:
            r = httpx.get(url, timeout=3)
            line(OK if r.status_code < 500 else WARN, label, f"HTTP {r.status_code}")
        except Exception:
            line(MISS, label, "not running")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = dotenv_values(os.path.join(HERE, ".env"))
    print("BrandAura preflight")
    check_env(env)
    check_accounts()
    public = check_tunnel()
    check_servers()
    base = (env.get("PUBLIC_BACKEND_URL") if (env.get("PUBLIC_BACKEND_URL") or "").startswith("https://") else public)
    print("\nWebhook callback URLs" + ("" if base else " (need a public https URL first)"))
    for p in ("facebook", "instagram", "linkedin", "tiktok"):
        print(f"  {p:9} {(base or 'https://<tunnel>')}/api/webhooks/{p}")
