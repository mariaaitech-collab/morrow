"""Publishing diagnostics for Facebook, Instagram, LinkedIn and TikTok.

    .venv\\Scripts\\python.exe diagnose_publishing.py

Read-only except for ONE harmless step: an UNPUBLISHED Instagram media
container is created from a test image served through the public tunnel, to
prove Meta can download BrandAura's media. It is never published and Meta
expires it automatically after 24 hours. Tokens are never printed.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import media_rules  # noqa: E402
import firebase_db  # noqa: E402
from config import FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, GRAPH_BASE  # noqa: E402
from tiktok_client import TikTokError, tiktok  # noqa: E402

GRAPH = GRAPH_BASE
REPORT: list[tuple[str, str, str, str]] = []  # (section, status, check, detail/fix)


def add(section, status, check, detail=""):
    REPORT.append((section, status, check, detail))


async def graph_get(http, path, token, **params):
    r = await http.get(f"{GRAPH}/{path}", params={**params, "access_token": token})
    try:
        return r.json()
    except Exception:
        return {"error": {"message": f"HTTP {r.status_code}"}}


# ---------------------------------------------------------------------------
async def check_environment():
    sec = "Environment"
    try:
        import PIL
        add(sec, "OK", "Pillow (image conversion)", f"version {PIL.__version__}")
    except ImportError:
        add(sec, "FAIL", "Pillow (image conversion)", "Fix: .venv\\Scripts\\python.exe -m pip install Pillow")
    base = media_rules.public_base_url()
    if not base:
        add(sec, "FAIL", "PUBLIC_BACKEND_URL", "Not a public https URL. Fix: set PUBLIC_BACKEND_URL in backend/.env to the backend's public https URL")
    else:
        try:
            r = httpx.get(base + "/api/health", timeout=20)
            add(sec, "OK" if r.status_code == 200 else "FAIL", "Public backend URL", f"{base} -> HTTP {r.status_code}")
        except Exception as e:
            add(sec, "FAIL", "Public backend URL", f"{base} unreachable ({e}). Fix: check PUBLIC_BACKEND_URL and that the backend is running")
    os.makedirs(media_rules.UPLOAD_DIR, exist_ok=True)
    add(sec, "OK" if os.access(media_rules.UPLOAD_DIR, os.W_OK) else "FAIL", "Uploads folder writable", media_rules.UPLOAD_DIR)
    import shutil
    if shutil.which("ffprobe"):
        add(sec, "OK", "ffprobe", "video codec/duration can be inspected")
    else:
        add(sec, "WARN", "ffprobe not installed", "Video codec and duration are not pre-checked; the platform's own error is shown instead")


async def check_meta(http, label, fb, ig_connected):
    sec_fb, sec_ig = f"Facebook ({label})", f"Instagram ({label})"
    user_token = fb.get("access_token", "")
    perms = await graph_get(http, "me/permissions", user_token)
    if "error" in perms:
        add(sec_fb, "FAIL", "User token", f"{perms['error'].get('message', '')[:120]}. Fix: Disconnect + Connect Facebook in BrandAura")
        return
    granted = {p["permission"] for p in perms.get("data", []) if p.get("status") == "granted"}
    me = await graph_get(http, "me", user_token, fields="name")
    add(sec_fb, "OK", "User token valid", f"as {me.get('name', '?')}")
    debug = await graph_get(http, "debug_token", f"{FACEBOOK_CLIENT_ID}|{FACEBOOK_CLIENT_SECRET}", input_token=user_token)
    exp = (debug.get("data") or {}).get("data_access_expires_at") or (debug.get("data") or {}).get("expires_at")
    if exp:
        import datetime as dt
        add(sec_fb, "OK", "Token expiry", dt.datetime.fromtimestamp(exp).strftime("%Y-%m-%d"))
    need_fb = ["pages_show_list", "pages_read_engagement", "pages_manage_posts"]
    missing = [p for p in need_fb if p not in granted]
    add(sec_fb, "FAIL" if missing else "OK", "Publishing permissions",
        f"missing {', '.join(missing)}. Fix: reconnect Facebook and approve all" if missing else ", ".join(need_fb))

    pages = fb.get("pages") or []
    if not pages:
        add(sec_fb, "FAIL", "Pages", "No Pages stored. Fix: reconnect Facebook and select your Pages")
    # Your role on each Page ("tasks") is listed on the USER's Page list.
    roles = await graph_get(http, "me/accounts", user_token, fields="id,tasks")
    tasks_by_page = {p.get("id"): p.get("tasks") or [] for p in roles.get("data", [])}
    for pg in pages:
        info = await graph_get(http, pg["id"], pg.get("access_token", ""), fields="name")
        if "error" in info:
            add(sec_fb, "FAIL", f"Page '{pg.get('name')}'", f"{info['error'].get('message', '')[:120]}. Fix: reconnect Facebook")
            continue
        tasks = tasks_by_page.get(pg["id"], [])
        can_post = "CREATE_CONTENT" in tasks or "MANAGE" in tasks
        add(sec_fb, "OK" if can_post else "FAIL", f"Page '{info.get('name')}'",
            "token valid, can create posts" if can_post else f"your role lacks CREATE_CONTENT (tasks: {tasks})")

    # ---- Instagram ----
    ig_id = fb.get("instagram_business_id") or next((p.get("instagram_business_id") for p in pages if p.get("instagram_business_id")), None)
    if not ig_id:
        add(sec_ig, "FAIL", "Business/Creator account", "No Instagram professional account is linked to any Page. Fix: in Instagram app, switch to Professional and link it to the Page, then reconnect")
        return
    ig_page = next((p for p in pages if p.get("instagram_business_id") == ig_id), None) or (pages[0] if pages else {})
    page_token = ig_page.get("access_token", "")
    add(sec_ig, "OK" if ig_connected else "WARN", "Instagram channel in BrandAura",
        "connected" if ig_connected else "not connected separately; publishing uses the Facebook connection")
    ig = await graph_get(http, ig_id, page_token, fields="username,name,media_count,followers_count")
    if "error" in ig:
        add(sec_ig, "FAIL", "Business/Creator account", f"{ig['error'].get('message', '')[:140]}")
        return
    add(sec_ig, "OK", "Business/Creator account linked", f"@{ig.get('username')} via Page '{ig_page.get('name')}' (id {ig_id})")
    need_ig = ["instagram_basic", "instagram_content_publish"]
    missing = [p for p in need_ig if p not in granted]
    add(sec_ig, "FAIL" if missing else "OK", "Publishing permissions",
        f"missing {', '.join(missing)}. Fix: reconnect and approve Instagram access" if missing else ", ".join(need_ig))
    quota = await graph_get(http, f"{ig_id}/content_publishing_limit", page_token, fields="quota_usage,config")
    q = (quota.get("data") or [{}])[0]
    if q:
        total = (q.get("config") or {}).get("quota_total", 100)
        used = q.get("quota_usage", 0)
        add(sec_ig, "OK" if used < total else "FAIL", "24h publishing quota", f"{used}/{total} used")

    # End-to-end media fetch test (unpublished container).
    base = media_rules.public_base_url()
    if not base:
        add(sec_ig, "FAIL", "Media download test", "skipped: no public tunnel URL")
        return
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1080, 1080), (255, 79, 154))
    ImageDraw.Draw(img).text((420, 520), "BrandAura test", fill=(255, 255, 255))
    test_path = os.path.join(media_rules.UPLOAD_DIR, "brandaura_diagnostic_test.jpg")
    img.save(test_path, format="JPEG", quality=90)
    test_url = f"{base}/uploads/brandaura_diagnostic_test.jpg"
    try:
        r = await http.post(f"{GRAPH}/{ig_id}/media", data={"image_url": test_url, "caption": "diagnostic (not published)", "access_token": page_token})
        body = r.json()
        if "id" not in body:
            err = body.get("error") or {}
            add(sec_ig, "FAIL", "Media download test", f"Meta could not fetch {test_url}: {err.get('error_user_msg') or err.get('message')}")
            return
        status = ""
        for _ in range(10):
            await asyncio.sleep(2)
            st = await graph_get(http, body["id"], page_token, fields="status_code,status")
            status = st.get("status_code", "")
            if status in ("FINISHED", "ERROR", "EXPIRED"):
                break
        add(sec_ig, "OK" if status == "FINISHED" else "FAIL", "Media download test",
            "Meta downloaded a test image through the tunnel (container left UNPUBLISHED)" if status == "FINISHED"
            else f"container status {status or 'unknown'}")
    finally:
        try:
            os.remove(test_path)
        except OSError:
            pass


async def check_linkedin(http, label, acct):
    sec = f"LinkedIn ({label})"
    if not acct.get("provider_account_id"):
        add(sec, "FAIL", "Profile id", "missing. Fix: reconnect LinkedIn")
    r = await http.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {acct.get('access_token', '')}"})
    if r.status_code == 200:
        name = r.json().get("name", "?")
        add(sec, "OK", "Access token valid", f"as {name}")
        if acct.get("provider_account_id") and r.json().get("sub") != acct.get("provider_account_id"):
            add(sec, "FAIL", "Profile id matches token", "stored id differs from the token's owner. Fix: reconnect LinkedIn")
    else:
        add(sec, "FAIL", "Access token", f"HTTP {r.status_code} (tokens expire after 60 days). Fix: Disconnect + Connect LinkedIn")
    if "undefined" in (acct.get("account_name") or ""):
        add(sec, "WARN", "Display name", f"stored as '{acct.get('account_name')}' (cosmetic; reconnecting refreshes it)")


async def check_tiktok(label, acct):
    sec = f"TikTok ({label})"
    from routers.social import save_user_account
    try:
        if await tiktok.refresh_if_needed(acct):
            add(sec, "OK", "Access token", "was expired; refreshed")
        info = await tiktok.user_info(acct["access_token"])
        user = (info.get("data") or {}).get("user") or {}
        add(sec, "OK", "Access token valid", f"as {user.get('display_name', '?')}")
        creator = await tiktok.creator_info(acct["access_token"])
        opts = (creator.get("data") or {}).get("privacy_level_options") or []
        public = "PUBLIC_TO_EVERYONE" in opts
        add(sec, "OK" if public else "WARN", "Posting visibility",
            ", ".join(opts) if public else f"only {', '.join(opts) or 'SELF_ONLY'}: an unaudited app posts privately until TikTok approves it")
    except TikTokError as e:
        add(sec, "FAIL", "TikTok API", f"{str(e)[:160]}. Fix: reconnect TikTok")


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    await check_environment()
    accounts = json.load(open(os.path.join(HERE, "connected_accounts.json"), encoding="utf-8"))

    seen = {"facebook": False, "instagram": False, "linkedin": False, "tiktok": False}
    async with httpx.AsyncClient(timeout=30) as http:
        for uid, platforms in accounts.items():
            try:
                u = await firebase_db.get_by_id(firebase_db.users, uid)
            except Exception:
                u = None
            label = (u or {}).get("email") or f"user {uid[-6:]}"
            if platforms.get("facebook"):
                seen["facebook"] = seen["instagram"] = True
                await check_meta(http, label, platforms["facebook"], "instagram" in platforms)
            if platforms.get("linkedin"):
                seen["linkedin"] = True
                await check_linkedin(http, label, platforms["linkedin"])
            if platforms.get("tiktok"):
                seen["tiktok"] = True
                await check_tiktok(label, platforms["tiktok"])

    report = await tiktok.check_connection()
    add("TikTok (app)", "OK" if report["ok"] else "FAIL", "Client key/secret", report["detail"])
    for platform, ok in seen.items():
        if not ok:
            add(platform.title() if platform != "linkedin" else "LinkedIn", "WARN", "Account connected",
                "no account connected in BrandAura. Fix: Dashboard > Channels > Connect")

    print("\n" + "=" * 86)
    print("  BRANDAURA PUBLISHING DIAGNOSTIC REPORT")
    print("=" * 86)
    current = None
    for section, status, check, detail in REPORT:
        if section != current:
            print(f"\n{section}")
            current = section
        print(f"  [{status:^4}] {check}" + (f": {detail}" if detail else ""))
    fails = sum(1 for r in REPORT if r[1] == "FAIL")
    warns = sum(1 for r in REPORT if r[1] == "WARN")
    print("\n" + "=" * 86)
    print(f"  {fails} failure(s), {warns} warning(s)")
    print("=" * 86)


if __name__ == "__main__":
    asyncio.run(main())
