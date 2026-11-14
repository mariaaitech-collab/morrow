"""Guided webhook setup for Meta (Page + Instagram), LinkedIn and TikTok.

    .venv\\Scripts\\python.exe setup_webhooks.py                  # all portals, isolated profile
    .venv\\Scripts\\python.exe setup_webhooks.py meta tiktok      # only some portals
    .venv\\Scripts\\python.exe setup_webhooks.py meta tiktok --use-my-profile
    .venv\\Scripts\\python.exe setup_webhooks.py --use-my-profile "Profile 1" --keep-profile
    .venv\\Scripts\\python.exe setup_webhooks.py --cdp http://127.0.0.1:9222

Browser modes
  default           a dedicated, empty Chrome profile (log in once; it persists).
  --use-my-profile  reuse YOUR logged-in Chrome profile. Chrome 136+ ignores
                    remote debugging on its default "User Data" folder, so with
                    all normal Chrome windows CLOSED the script copies that
                    profile + "Local State" (caches skipped) to a private folder,
                    starts real Chrome on the copy with --remote-debugging-port=9222
                    and attaches over CDP. The copy holds session cookies, so it is
                    DELETED when the run ends unless --keep-profile is given.
                    Default profile folder: "Profile 1".
  --cdp URL         attach to a Chrome you started yourself with
                    --remote-debugging-port (it must use a non-default --user-data-dir).

For every portal the script:

  1. opens the developer portal and PAUSES;
  2. you log in yourself, pass any security checks and open the app;
  3. you give permission. Any ONE of these resumes the script:
       * click "Continue" in the BrandAura panel inside the browser,
       * type  allowed  or  continue  in this terminal (interactive runs),
       * write "continue" into the signal file printed at start-up;
     "Skip" / typing  skip  leaves that portal untouched;
  4. only then does it fill the callback URL / verify token and save.

The script never sees or stores your passwords. Values come from backend/.env:
PUBLIC_BACKEND_URL, META_WEBHOOK_VERIFY_TOKEN, FACEBOOK_CLIENT_ID/SECRET.

Meta: after the dashboard step the app's subscriptions are checked through the
official Graph API (/{app-id}/subscriptions) and completed there if any UI
click missed, so the result does not depend on the dashboard layout.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time
from queue import Empty, Queue

import httpx
from dotenv import dotenv_values
from playwright.async_api import Error as PWError
from playwright.async_api import async_playwright

from config import GRAPH_BASE

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dotenv_values(os.path.join(HERE, ".env"))
PUBLIC_URL = (ENV.get("PUBLIC_BACKEND_URL") or "").rstrip("/")
VERIFY_TOKEN = ENV.get("META_WEBHOOK_VERIFY_TOKEN") or ""
FB_APP_ID = ENV.get("FACEBOOK_CLIENT_ID") or ""
FB_APP_SECRET = ENV.get("FACEBOOK_CLIENT_SECRET") or ""
LINKEDIN_CLIENT_ID = ENV.get("LINKEDIN_CLIENT_ID") or ""
TIKTOK_CLIENT_KEY = ENV.get("TIKTOK_CLIENT_KEY") or ""

WORK_DIR = os.path.join(os.getenv("LOCALAPPDATA") or HERE, "BrandAura", "webhook-setup")
PROFILE_DIR = os.path.join(WORK_DIR, "chrome-profile")
SIGNAL_FILE = os.path.join(WORK_DIR, "continue.signal")
GRAPH = GRAPH_BASE
GATE_TIMEOUT = 30 * 60

META_OBJECTS = [
    # (api object, dashboard label, callback path, fields)
    ("page", "Page", "/api/webhooks/facebook", ["feed", "messages"]),
    ("instagram", "Instagram", "/api/webhooks/instagram", ["comments", "messages"]),
]

RESULTS: dict[str, str] = {}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def mask(value: str) -> str:
    return value[:4] + "…" if value else "(missing)"


# ---------------------------------------------------------------------------
# Permission gate: browser panel button, terminal input or signal file
# ---------------------------------------------------------------------------
class Gate:
    def __init__(self) -> None:
        self.state = {"visible": True, "waiting": False, "title": "BrandAura webhook setup", "message": "Starting…"}
        self._choice: str | None = None
        self._stdin: Queue[str] = Queue()
        if sys.stdin and sys.stdin.isatty():
            threading.Thread(target=self._read_stdin, daemon=True).start()

    def _read_stdin(self) -> None:
        for line in sys.stdin:
            self._stdin.put(line.strip().lower())

    def status(self, title: str, message: str) -> None:
        self.state = {"visible": True, "waiting": False, "title": title, "message": message}
        log(f"{title}: {message}")

    def signal(self, choice: str) -> None:
        if self.state.get("waiting") and choice in ("continue", "skip"):
            self._choice = choice

    async def wait(self, title: str, message: str) -> str:
        """Block until the user allows ('continue') or skips. Returns the choice."""
        self.state = {"visible": True, "waiting": True, "title": title, "message": message}
        self._choice = None
        try:
            os.remove(SIGNAL_FILE)
        except FileNotFoundError:
            pass
        print("\n" + "=" * 78, flush=True)
        print(f"WAITING FOR YOUR PERMISSION: {title}", flush=True)
        print(message, flush=True)
        print("Resume with ANY of: the 'Continue' button in the browser panel,", flush=True)
        print("typing 'allowed' / 'continue' here, or 'skip' to leave this portal untouched.", flush=True)
        print(f"(signal file: {SIGNAL_FILE})", flush=True)
        print("=" * 78, flush=True)
        deadline = time.time() + GATE_TIMEOUT
        while self._choice is None:
            if time.time() > deadline:
                self._choice = "skip"
                break
            try:
                text = self._stdin.get_nowait()
                if text in ("allowed", "allow", "continue", "yes", "y"):
                    self._choice = "continue"
                elif text == "skip":
                    self._choice = "skip"
            except Empty:
                pass
            if os.path.exists(SIGNAL_FILE):
                try:
                    text = open(SIGNAL_FILE, encoding="utf-8").read().strip().lower()
                    os.remove(SIGNAL_FILE)
                except OSError:
                    text = ""
                if text in ("allowed", "continue", "skip"):
                    self._choice = "skip" if text == "skip" else "continue"
            await asyncio.sleep(0.4)
        self.state = {**self.state, "waiting": False, "message": "Permission received." if self._choice == "continue" else "Skipped."}
        log(f"{title}: user chose '{self._choice}'")
        return self._choice


# The panel is plain DOM (no innerHTML) so it works under strict CSP/Trusted Types.
OVERLAY_JS = r"""
(() => {
  if (window.top !== window) return;
  const mount = () => {
    if (!document.body || document.getElementById('__brandaura_gate')) return;
    const box = document.createElement('div');
    box.id = '__brandaura_gate';
    Object.assign(box.style, {position: 'fixed', zIndex: '2147483647', right: '18px', bottom: '18px',
      width: '340px', maxWidth: 'calc(100vw - 36px)', background: '#15151e', color: '#f5f2fc',
      border: '2px solid #ff4f9a', borderRadius: '14px', padding: '14px 16px',
      font: '13px/1.45 system-ui, -apple-system, Segoe UI, sans-serif',
      boxShadow: '0 20px 50px rgba(0,0,0,.45)', display: 'none'});
    const title = document.createElement('div');
    Object.assign(title.style, {fontWeight: '700', marginBottom: '6px', color: '#ffd7e6'});
    const msg = document.createElement('div');
    Object.assign(msg.style, {whiteSpace: 'pre-wrap', color: '#e5e0ef'});
    const row = document.createElement('div');
    Object.assign(row.style, {display: 'none', gap: '8px', marginTop: '12px'});
    const mk = (label, primary) => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = label;
      Object.assign(b.style, {flex: '1', padding: '8px 10px', borderRadius: '9px', cursor: 'pointer',
        font: '600 13px system-ui, sans-serif', border: primary ? '0' : '1px solid rgba(255,255,255,.25)',
        background: primary ? '#ff4f9a' : 'transparent', color: '#fff'});
      return b;
    };
    const go = mk('Continue (allowed)', true);
    const skip = mk('Skip', false);
    go.addEventListener('click', () => window.brandauraSignal('continue'));
    skip.addEventListener('click', () => window.brandauraSignal('skip'));
    row.append(go, skip);
    const hide = document.createElement('button');
    hide.type = 'button'; hide.textContent = '–'; hide.title = 'Minimise';
    Object.assign(hide.style, {position: 'absolute', top: '6px', right: '10px', background: 'none',
      border: '0', color: '#a49daf', cursor: 'pointer', fontSize: '16px'});
    let minimised = false;
    hide.addEventListener('click', () => { minimised = !minimised; msg.style.display = minimised ? 'none' : 'block'; });
    box.append(hide, title, msg, row);
    document.body.appendChild(box);
    const tick = async () => {
      try {
        const s = await window.brandauraState();
        box.style.display = s.visible ? 'block' : 'none';
        title.textContent = 'BrandAura · ' + s.title;
        msg.textContent = s.message;
        row.style.display = s.waiting ? 'flex' : 'none';
        box.style.borderColor = s.waiting ? '#fdcb6e' : '#ff4f9a';
      } catch (e) { /* binding not ready yet */ }
    };
    setInterval(tick, 800); tick();
  };
  document.addEventListener('DOMContentLoaded', mount);
  setInterval(mount, 1500);
})();
"""


# ---------------------------------------------------------------------------
# Locator helpers (tolerant of portal redesigns)
# ---------------------------------------------------------------------------
async def find(page, factories, timeout: float = 10.0):
    """Return the first VISIBLE element produced by any factory(frame) in any frame."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for frame in page.frames:
            for make in factories:
                try:
                    loc = make(frame)
                    count = await loc.count()
                    for i in range(min(count, 5)):
                        el = loc.nth(i)
                        if await el.is_visible():
                            return el
                except PWError:
                    continue
        await asyncio.sleep(0.4)
    return None


def by_label(rx):
    return [lambda f: f.get_by_label(rx), lambda f: f.get_by_placeholder(rx)]


def button(rx):
    return [lambda f: f.get_by_role("button", name=rx), lambda f: f.get_by_role("link", name=rx)]


async def fill(page, factories, value: str, what: str) -> bool:
    el = await find(page, factories)
    if not el:
        log(f"  could not find the {what} field")
        return False
    current = ""
    try:
        current = await el.input_value()
    except PWError:
        pass
    if current.strip() == value:
        log(f"  {what} already set")
        return True
    await el.click()
    await el.fill(value)
    log(f"  filled {what}")
    return True


async def click(page, factories, what: str, timeout: float = 10.0) -> bool:
    el = await find(page, factories, timeout)
    if not el:
        log(f"  could not find '{what}'")
        return False
    await el.scroll_into_view_if_needed()
    await el.click()
    log(f"  clicked '{what}'")
    return True


async def snapshot(page, name: str) -> None:
    path = os.path.join(WORK_DIR, f"{name}.png")
    try:
        await page.screenshot(path=path, full_page=False)
        log(f"  screenshot saved: {path}")
    except PWError:
        pass


# ---------------------------------------------------------------------------
# Meta (Facebook Page + Instagram)
# ---------------------------------------------------------------------------
def _app_token() -> str:
    return f"{FB_APP_ID}|{FB_APP_SECRET}"


async def meta_subscriptions() -> dict:
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(f"{GRAPH}/{FB_APP_ID}/subscriptions", params={"access_token": _app_token()})
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message"))
    return {s.get("object"): s for s in body.get("data", [])}


def _active_fields(sub: dict) -> set[str]:
    return {f.get("name") for f in (sub or {}).get("fields", []) if f.get("name")}


async def meta_api_subscribe(obj: str, callback: str, fields: list[str]) -> str:
    async with httpx.AsyncClient(timeout=40) as http:
        r = await http.post(
            f"{GRAPH}/{FB_APP_ID}/subscriptions",
            data={
                "object": obj,
                "callback_url": callback,
                "fields": ",".join(fields),
                "verify_token": VERIFY_TOKEN,
                "include_values": "true",
                "access_token": _app_token(),
            },
        )
    body = r.json()
    if body.get("success"):
        return "ok"
    return (body.get("error") or {}).get("message") or r.text[:200]


async def meta_ui_object(page, label: str, callback: str, fields: list[str]) -> bool:
    """Best-effort dashboard automation for one webhook object."""
    await page.goto(f"https://developers.facebook.com/apps/{FB_APP_ID}/webhooks/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3500)

    # 1. Pick the product/object (native <select> or a custom dropdown).
    picked = False
    select = await find(page, [lambda f: f.locator("select")], timeout=4)
    if select:
        try:
            await select.select_option(label=label)
            picked = True
        except PWError:
            pass
    if not picked:
        opener = await find(page, [lambda f: f.get_by_role("combobox"),
                                   lambda f: f.get_by_role("button", name=re.compile(r"^(User|Page|Instagram|Permissions|Application|Select)", re.I))],
                            timeout=6)
        if opener:
            await opener.click()
            option = await find(page, [lambda f: f.get_by_role("option", name=re.compile(rf"^{label}$", re.I)),
                                       lambda f: f.get_by_role("menuitem", name=re.compile(rf"^{label}$", re.I)),
                                       lambda f: f.get_by_text(re.compile(rf"^{label}$"), exact=True)], timeout=5)
            if option:
                await option.click()
                picked = True
    log(f"  object '{label}' selected: {picked}")
    if not picked:
        return False
    await page.wait_for_timeout(1500)

    # 2. Open the subscription dialog.
    if not await click(page, button(re.compile(r"(subscribe to this object|edit subscription)", re.I)), "Subscribe to this object"):
        return False
    await page.wait_for_timeout(1200)

    # 3. Callback URL + verify token, then Verify and save.
    ok = await fill(page, by_label(re.compile(r"callback url", re.I)), callback, "Callback URL")
    ok = await fill(page, by_label(re.compile(r"verify token", re.I)), VERIFY_TOKEN, "Verify token") and ok
    if not ok:
        return False
    if not await click(page, button(re.compile(r"verify and save|^save$", re.I)), "Verify and save"):
        return False
    await page.wait_for_timeout(6000)
    err = await find(page, [lambda f: f.get_by_text(re.compile(r"(couldn.t be validated|could not be validated|error)", re.I))], timeout=2)
    if err:
        log(f"  dashboard reported: {(await err.inner_text())[:160]}")
        return False

    # 4. Subscribe the fields (each field row has its own Subscribe control).
    for field in fields:
        row = await find(page, [lambda f, fld=field: f.locator("tr", has=f.get_by_text(fld, exact=True))], timeout=4)
        if not row:
            log(f"  field row '{field}' not found")
            continue
        sub_btn = row.get_by_role("button", name=re.compile(r"^subscribe$", re.I))
        if await sub_btn.count():
            await sub_btn.first.click()
            log(f"  subscribed field '{field}'")
            await page.wait_for_timeout(800)
        else:
            log(f"  field '{field}' already subscribed (or control not found)")
    return True


async def run_meta(page, gate: Gate) -> None:
    portal = "Meta (Facebook + Instagram)"
    if not (FB_APP_ID and FB_APP_SECRET and VERIFY_TOKEN):
        RESULTS[portal] = "skipped: FACEBOOK_CLIENT_ID / SECRET / META_WEBHOOK_VERIFY_TOKEN missing in .env"
        return
    await page.goto("https://developers.facebook.com/apps/", wait_until="domcontentloaded")
    choice = await gate.wait(
        portal,
        f"1. Check you are logged in to Meta for Developers (log in only if asked).\n2. Pass any security checks.\n"
        f"3. Open your app (App ID {mask(FB_APP_ID)}).\nThen click Continue to let me set up the Page and Instagram webhooks.",
    )
    if choice != "continue":
        RESULTS[portal] = "skipped by you"
        return

    outcomes = []
    for obj, label, path, fields in META_OBJECTS:
        callback = PUBLIC_URL + path
        gate.status(portal, f"Setting up the {label} webhook…\n{callback}")
        try:
            ui_ok = await meta_ui_object(page, label, callback, fields)
        except PWError as e:
            log(f"  dashboard automation error: {str(e)[:200]}")
            ui_ok = False
        if not ui_ok:
            await snapshot(page, f"meta-{obj}")

        # Verify (and if needed complete) through the official API.
        try:
            subs = await meta_subscriptions()
            sub = subs.get(obj) or {}
            complete = sub.get("callback_url") == callback and sub.get("active") and set(fields) <= _active_fields(sub)
            if complete:
                outcomes.append(f"{label}: subscribed via dashboard ({', '.join(fields)})")
                continue
            log(f"  {label}: completing through the Graph API")
            res = await meta_api_subscribe(obj, callback, fields)
            if res != "ok":
                # Retry with only the fields Meta accepts for this app.
                for f in fields:
                    single = await meta_api_subscribe(obj, callback, [f])
                    log(f"    field {f}: {single}")
            subs = await meta_subscriptions()
            got = _active_fields(subs.get(obj))
            if subs.get(obj, {}).get("callback_url") == callback and got:
                missing = [f for f in fields if f not in got]
                outcomes.append(f"{label}: subscribed ({', '.join(sorted(got))})" + (f", NOT {', '.join(missing)}" if missing else ""))
            else:
                outcomes.append(f"{label}: FAILED ({res})")
        except Exception as e:
            outcomes.append(f"{label}: FAILED to verify ({e})")

    await page.goto(f"https://developers.facebook.com/apps/{FB_APP_ID}/webhooks/", wait_until="domcontentloaded")
    RESULTS[portal] = "; ".join(outcomes)
    gate.status(portal, RESULTS[portal])


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------
async def run_linkedin(page, gate: Gate) -> None:
    portal = "LinkedIn"
    callback = PUBLIC_URL + "/api/webhooks/linkedin"
    await page.goto("https://www.linkedin.com/developers/apps", wait_until="domcontentloaded")
    choice = await gate.wait(
        portal,
        f"1. Log in to LinkedIn in this window and pass any checks.\n"
        f"2. Open your app (Client ID {mask(LINKEDIN_CLIENT_ID)}) so its page is showing.\n"
        f"Then click Continue to let me add the webhook:\n{callback}",
    )
    if choice != "continue":
        RESULTS[portal] = "skipped by you"
        return

    match = re.search(r"/developers/apps/(\d+)", page.url)
    if not match:
        choice = await gate.wait(portal, "I can't see an app page yet. Open your app in the LinkedIn Developer Portal, then click Continue.")
        match = re.search(r"/developers/apps/(\d+)", page.url) if choice == "continue" else None
    if not match:
        RESULTS[portal] = "skipped: no app page was open"
        return
    app_id = match.group(1)
    gate.status(portal, "Opening the Webhooks tab…")
    await page.goto(f"https://www.linkedin.com/developers/apps/{app_id}/webhooks", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    if "/webhooks" not in page.url or not await find(page, [lambda f: f.get_by_text(re.compile(r"webhook", re.I))], timeout=5):
        await snapshot(page, "linkedin")
        RESULTS[portal] = ("no Webhooks tab on this app. LinkedIn only offers webhooks to apps approved for the "
                           "Community Management API (organization pages).")
        gate.status(portal, RESULTS[portal])
        await page.wait_for_timeout(4000)
        return

    await click(page, button(re.compile(r"(add|create|new) webhook|add endpoint", re.I)), "Add webhook", timeout=4)
    filled = await fill(page, by_label(re.compile(r"(webhook|endpoint|callback).*(url)?|https://", re.I)), callback, "Webhook URL")
    saved = filled and await click(page, button(re.compile(r"^(save|add|create|verify|submit)", re.I)), "Save")
    await page.wait_for_timeout(5000)
    err = await find(page, [lambda f: f.get_by_text(re.compile(r"(failed|invalid|could not|error)", re.I))], timeout=2)
    if saved and not err:
        RESULTS[portal] = f"webhook saved: {callback}"
    else:
        await snapshot(page, "linkedin")
        detail = (await err.inner_text())[:160] if err else "a field or button could not be found"
        choice = await gate.wait(portal, f"Automatic save did not complete ({detail}).\nPaste this URL manually and save:\n{callback}\nClick Continue when done.")
        RESULTS[portal] = "completed manually" if choice == "continue" else f"not completed: {detail}"
    gate.status(portal, RESULTS[portal])


# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------
async def run_tiktok(page, gate: Gate) -> None:
    portal = "TikTok"
    callback = PUBLIC_URL + "/api/webhooks/tiktok"
    await page.goto("https://developers.tiktok.com/apps/", wait_until="domcontentloaded")
    choice = await gate.wait(
        portal,
        f"1. Check you are logged in to TikTok for Developers (log in only if asked) and pass any checks.\n"
        f"2. Open your app (Client key {mask(TIKTOK_CLIENT_KEY)}) on its configuration page.\n"
        f"Then click Continue to let me set the webhook callback:\n{callback}",
    )
    if choice != "continue":
        RESULTS[portal] = "skipped by you"
        return

    gate.status(portal, "Looking for the Webhooks section…")
    section = await find(page, [lambda f: f.get_by_text(re.compile(r"^webhooks?$", re.I))], timeout=8)
    if section:
        await section.scroll_into_view_if_needed()
        try:
            await section.click()
        except PWError:
            pass
    filled = await fill(page, by_label(re.compile(r"callback url", re.I)), callback, "Callback URL")
    tested = filled and await click(page, button(re.compile(r"test url", re.I)), "Test URL", timeout=4)
    if tested:
        await page.wait_for_timeout(4000)
    saved = filled and await click(page, button(re.compile(r"^(save|apply changes|submit)", re.I)), "Save", timeout=6)
    await page.wait_for_timeout(4000)
    if filled and saved:
        RESULTS[portal] = f"callback saved: {callback}" + (" (URL test sent)" if tested else "")
    else:
        await snapshot(page, "tiktok")
        choice = await gate.wait(portal, f"I could not finish this automatically.\nPaste this Callback URL in the Webhooks section and save:\n{callback}\nClick Continue when done.")
        RESULTS[portal] = "completed manually" if choice == "continue" else "not completed"
    gate.status(portal, RESULTS[portal])


# ---------------------------------------------------------------------------
# Browser modes
# ---------------------------------------------------------------------------
CHROME_EXE_CANDIDATES = [
    os.path.join(os.getenv("PROGRAMFILES", r"C:\Program Files"), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.getenv("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]
CHROME_USER_DATA = os.path.join(os.getenv("LOCALAPPDATA", ""), r"Google\Chrome\User Data")
PROFILE_COPY_DIR = os.path.join(WORK_DIR, "my-profile-copy")
CDP_PORT = 9222
# Large, regenerable folders that are not needed to stay logged in.
SKIP_DIRS = [
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "GrShaderCache", "GraphiteDawnCache", "ShaderCache", "Media Cache", "Service Worker",
    "File System", "blob_storage", "optimization_guide_model_store", "Safe Browsing",
]


def chrome_exe() -> str:
    for path in CHROME_EXE_CANDIDATES:
        if os.path.exists(path):
            return path
    sys.exit("Google Chrome was not found.")


def normal_chrome_running() -> bool:
    """True while Chrome runs on the DEFAULT User Data folder (its files are locked then).

    Only top-level browser processes count (child processes carry --type=...).
    Chromes started with their own --user-data-dir (like this script's) are ignored.
    """
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | ForEach-Object { $_.CommandLine }"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.strip() and "--type=" not in line and "--user-data-dir" not in line:
            return True
    return False


def copy_profile(profile: str) -> None:
    import shutil
    import subprocess

    src = os.path.join(CHROME_USER_DATA, profile)
    if not os.path.isdir(src):
        sys.exit(f"Chrome profile folder not found: {src}")
    shutil.rmtree(PROFILE_COPY_DIR, ignore_errors=True)
    os.makedirs(PROFILE_COPY_DIR, exist_ok=True)
    # "Local State" holds the key that decrypts the profile's cookies.
    shutil.copy2(os.path.join(CHROME_USER_DATA, "Local State"), os.path.join(PROFILE_COPY_DIR, "Local State"))
    log(f"Copying your Chrome profile '{profile}' (caches skipped)…")
    result = subprocess.run(
        ["robocopy", src, os.path.join(PROFILE_COPY_DIR, profile), "/E", "/R:1", "/W:1",
         "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", *SKIP_DIRS],
        capture_output=True, text=True,
    )
    if result.returncode >= 8:  # robocopy: 0-7 mean success
        sys.exit(f"Copying the profile failed (robocopy {result.returncode}): {result.stdout[-400:]}")
    log("Profile copy ready")


def remove_profile_copy() -> None:
    import shutil

    for _ in range(6):
        shutil.rmtree(PROFILE_COPY_DIR, ignore_errors=True)
        if not os.path.exists(PROFILE_COPY_DIR):
            log("Deleted the temporary profile copy (no extra copy of your cookies is left on disk)")
            return
        time.sleep(1)
    log(f"Could not fully delete {PROFILE_COPY_DIR}; please delete it manually.")


def launch_debug_chrome(profile: str):
    import subprocess

    proc = subprocess.Popen([
        chrome_exe(),
        f"--user-data-dir={PROFILE_COPY_DIR}",
        f"--profile-directory={profile}",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run", "--no-default-browser-check", "--start-maximized",
        "about:blank",
    ])
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1).raise_for_status()
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    sys.exit("Chrome started but its debugging port did not open.")


async def report_sessions(context) -> None:
    """Log WHETHER you are logged in (cookie names only, never values)."""
    checks = {
        "Facebook": ("https://www.facebook.com", {"c_user", "xs"}),
        "TikTok": ("https://www.tiktok.com", {"sessionid", "sid_tt", "sessionid_ss"}),
    }
    for name, (url, wanted) in checks.items():
        try:
            names = {c["name"] for c in await context.cookies([url])}
            log(f"  {name} session in this browser: {'yes' if names & wanted else 'NOT found'}")
        except PWError:
            pass


# ---------------------------------------------------------------------------
async def main(selected: list[str], mode: str = "isolated", profile: str = "",
               cdp_url: str = "", keep_profile: bool = False) -> None:
    if not PUBLIC_URL.startswith("https://"):
        sys.exit("PUBLIC_BACKEND_URL in backend/.env must be a public https URL; webhooks cannot reach localhost.")
    os.makedirs(WORK_DIR, exist_ok=True)
    try:
        httpx.get(PUBLIC_URL + "/api/health", timeout=15).raise_for_status()
        log(f"Public backend reachable: {PUBLIC_URL}")
    except Exception as e:
        sys.exit(f"{PUBLIC_URL} is not reachable ({e}). Check PUBLIC_BACKEND_URL and start the backend first.")

    chrome_proc = None
    if mode == "my-profile":
        if normal_chrome_running():
            sys.exit("CHROME_STILL_OPEN: close ALL normal Chrome windows (also quit it from the system tray), then run again.")
        copy_profile(profile)
        chrome_proc = launch_debug_chrome(profile)
        cdp_url = f"http://127.0.0.1:{CDP_PORT}"

    gate = Gate()
    async with async_playwright() as pw:
        browser = None
        try:
            if cdp_url:
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                log(f"Attached to Chrome over CDP ({cdp_url})")
            else:
                context = await pw.chromium.launch_persistent_context(
                    PROFILE_DIR, channel="chrome", headless=False, no_viewport=True, args=["--start-maximized"],
                )
        except Exception:
            if chrome_proc:
                chrome_proc.terminate()
                if not keep_profile:
                    time.sleep(2)
                    remove_profile_copy()
            raise
        await context.expose_binding("brandauraState", lambda source: gate.state)
        await context.expose_binding("brandauraSignal", lambda source, choice: gate.signal(choice))
        await context.add_init_script(OVERLAY_JS)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.bring_to_front()
        await report_sessions(context)
        log("BROWSER_OPEN")

        runners = {"meta": run_meta, "linkedin": run_linkedin, "tiktok": run_tiktok}
        try:
            for name in selected:
                try:
                    await runners[name](page, gate)
                except PWError as e:
                    if "closed" in str(e).lower():
                        raise
                    RESULTS[name] = f"error: {str(e)[:200]}"
                    log(RESULTS[name])
            summary = "\n".join(f"{k}: {v}" for k, v in RESULTS.items())
            print("\n" + "=" * 78 + "\nSUMMARY\n" + summary + "\n" + "=" * 78, flush=True)
            await gate.wait("Finished", summary + "\n\nClick Continue to close this browser window.")
        except PWError as e:
            log(f"Browser closed or crashed: {str(e)[:120]}")
        finally:
            try:
                if browser:
                    await browser.close()
                else:
                    await context.close()
            except Exception:
                pass

    if chrome_proc:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=10)
        except Exception:
            pass
        time.sleep(2)
        if keep_profile:
            log(f"Kept the profile copy at {PROFILE_COPY_DIR} (contains session cookies)")
        else:
            remove_profile_copy()
    log("DONE")


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Guided webhook setup for Meta, LinkedIn and TikTok.")
    parser.add_argument("portals", nargs="*", help="meta, linkedin and/or tiktok (default: all)")
    parser.add_argument("--use-my-profile", nargs="?", const="Profile 1", default=None, metavar="PROFILE_DIR",
                        help='reuse your logged-in Chrome profile folder (default "Profile 1"); close Chrome first')
    parser.add_argument("--cdp", default="", metavar="URL", help="attach to an already running debug Chrome")
    parser.add_argument("--keep-profile", action="store_true", help="keep the temporary profile copy afterwards")
    args = parser.parse_args()
    if args.use_my_profile and args.use_my_profile.lower() in ("meta", "linkedin", "tiktok"):
        # "--use-my-profile meta tiktok": the flag swallowed a portal name.
        args.portals = [args.use_my_profile] + list(args.portals)
        args.use_my_profile = "Profile 1"
    portals = [p.lower() for p in args.portals] or ["meta", "linkedin", "tiktok"]
    bad = [p for p in portals if p not in ("meta", "linkedin", "tiktok")]
    if bad:
        parser.error(f"unknown portal(s): {', '.join(bad)}. Use meta, linkedin, tiktok.")
    mode = "my-profile" if args.use_my_profile else ("cdp" if args.cdp else "isolated")
    asyncio.run(main(portals, mode, args.use_my_profile or "", args.cdp, args.keep_profile))
