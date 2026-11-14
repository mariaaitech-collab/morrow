"""Point Meta's app-level webhook subscriptions at PUBLIC_BACKEND_URL.

    .venv\\Scripts\\python.exe meta_webhooks.py            # sync to PUBLIC_BACKEND_URL
    .venv\\Scripts\\python.exe meta_webhooks.py --status   # show what Meta has on file

Run it after the backend's public https URL changes (e.g. a new deployment
domain). Meta keeps delivering to the old URL otherwise, which silently drops
every comment/DM webhook. This re-registers each subscription (same fields, same
verify token) with the new callback URL via POST /{app-id}/subscriptions. Meta
immediately verifies the URL with a GET handshake, so the backend must be
running and publicly reachable; it cannot work while the app is localhost-only.
"""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import dotenv_values

from config import GRAPH_BASE

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = GRAPH_BASE
CALLBACK_PATHS = {"page": "/api/webhooks/facebook", "instagram": "/api/webhooks/instagram"}
DEFAULT_FIELDS = {"page": ["feed", "messages"], "instagram": ["comments", "messages"]}


def _env() -> dict:
    return dotenv_values(os.path.join(HERE, ".env"))


def _app(env: dict) -> tuple[str, str]:
    app_id = env.get("FACEBOOK_CLIENT_ID") or ""
    secret = env.get("META_APP_SECRET") or env.get("FACEBOOK_CLIENT_SECRET") or ""
    if not (app_id and secret):
        raise RuntimeError("FACEBOOK_CLIENT_ID / FACEBOOK_CLIENT_SECRET missing in .env")
    return app_id, f"{app_id}|{secret}"


def current_subscriptions() -> dict:
    env = _env()
    app_id, token = _app(env)
    body = httpx.get(f"{GRAPH}/{app_id}/subscriptions", params={"access_token": token}, timeout=20).json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message"))
    return {s["object"]: s for s in body.get("data", [])}


def sync(base_url: str | None = None, log=print) -> list[str]:
    """Point every page/instagram subscription at `base_url`. Returns result lines."""
    env = _env()
    base = (base_url or env.get("PUBLIC_BACKEND_URL") or "").rstrip("/")
    verify = env.get("META_WEBHOOK_VERIFY_TOKEN") or ""
    if not base.startswith("https://"):
        raise RuntimeError("PUBLIC_BACKEND_URL is not a public https URL")
    if not verify:
        raise RuntimeError("META_WEBHOOK_VERIFY_TOKEN missing in .env")
    app_id, token = _app(env)
    subs = current_subscriptions()
    results = []
    for obj, path in CALLBACK_PATHS.items():
        target = base + path
        existing = subs.get(obj) or {}
        fields = [f["name"] for f in existing.get("fields", [])] or DEFAULT_FIELDS[obj]
        for needed in DEFAULT_FIELDS[obj]:
            if needed not in fields:
                fields.append(needed)
        if existing.get("callback_url") == target and existing.get("active"):
            results.append(f"{obj}: already {target}")
            continue
        r = httpx.post(
            f"{GRAPH}/{app_id}/subscriptions",
            data={
                "object": obj,
                "callback_url": target,
                "fields": ",".join(fields),
                "verify_token": verify,
                "include_values": "true",
                "access_token": token,
            },
            timeout=60,
        )
        body = r.json()
        if body.get("success"):
            results.append(f"{obj}: {existing.get('callback_url') or '(none)'} -> {target}")
        else:
            results.append(f"{obj}: FAILED {(body.get('error') or {}).get('message') or r.text[:200]}")
    for line in results:
        log(f"[META] {line}")
    return results


if __name__ == "__main__":
    if "--status" in sys.argv:
        for obj, s in current_subscriptions().items():
            print(f"{obj:10} active={s.get('active')} {s.get('callback_url')}")
    else:
        sync()
