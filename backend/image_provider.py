"""AI image provider: which service draws images, and how the last attempt went.

Chosen in backend/.env, so switching needs no code change:
  IMAGE_PROVIDER  pollinations | none            (default: pollinations)
  IMAGE_API_KEY   optional Pollinations secret key (sk_...)

Without a key, requests go to Pollinations' anonymous free tier
(image.pollinations.ai), which allows one image every 45 seconds per server IP
and answers HTTP 402 FREE_LIMIT past that. With a key, requests go to the keyed
API (gen.pollinations.ai) and are billed to that key's Pollen balance.

Every failure keeps the provider's real answer: the raw response is logged, the
reason given to the caller quotes it, and status() reports it so the UI can
switch AI generation off until the provider can be used again.
"""
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from PIL import UnidentifiedImageError

import watermark
from config import IMAGE_API_KEY, IMAGE_PROVIDER

logger = logging.getLogger("brandora")

PROVIDERS = ("pollinations", "none")
FREE_URL = "https://image.pollinations.ai/prompt/"   # anonymous free tier
KEYED_URL = "https://gen.pollinations.ai/image/"     # needs IMAGE_API_KEY (Bearer)
TIMEOUT = 120.0
RAW_LOG_LIMIT = 2000
LOGGED_HEADERS = ("content-type", "retry-after", "x-auth-status", "x-model-used", "x-request-id", "x-cache")
# How long AI generation stays off after a failure that came without a
# Retry-After: longer for a key or billing problem (it will not clear by
# itself) than for an outage or a network error.
COOLDOWN_ACCOUNT = 600
COOLDOWN_OTHER = 120
# Height of the free tier's "pollinations.ai" badge band at the bottom, as a
# fraction of the image width (measured at 512 and 768 px: its top sits 4% of
# the width up; the rest is breathing room).
PROVIDER_BADGE_BAND = 0.05

_state = {"last_success_at": None, "last_failure": None, "blocked_until": 0.0}


class ImageProviderError(Exception):
    """No image was made. `reason` is the full, user-facing reason; `headline` a short one."""

    def __init__(self, reason: str, *, headline: str = "", status: int | None = None, code: str = "", unavailable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.headline = headline or reason
        self.status = status
        self.code = code
        self.unavailable = unavailable  # no provider is configured, so nothing was attempted

    @property
    def http_status(self) -> int:
        # Never 402: the frontend treats 402 as "your plan's quota is used up".
        return 503 if self.unavailable else 502


def problem() -> str:
    """Why no image can be requested at all ('' when a provider is configured)."""
    if IMAGE_PROVIDER == "none":
        return "No image provider is set up (IMAGE_PROVIDER=none in backend/.env)."
    if IMAGE_PROVIDER not in PROVIDERS:
        return f'IMAGE_PROVIDER="{IMAGE_PROVIDER}" is not a supported image provider. Use pollinations or none.'
    return ""


def keyed() -> bool:
    return bool(IMAGE_API_KEY)


def describe() -> str:
    """One line for the startup log. Never includes the key."""
    why = problem()
    if why:
        return why
    if keyed():
        return "Pollinations with IMAGE_API_KEY (gen.pollinations.ai, billed to the key's Pollen balance)"
    return "Pollinations anonymous free tier (1 image every 45 seconds per server IP; set IMAGE_API_KEY to lift it)"


def _iso(ts: float | None):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def status() -> dict:
    """What the UI needs to decide whether to offer AI generation, and why not."""
    why = problem()
    now = time.time()
    failure = _state["last_failure"]
    blocked = not why and _state["blocked_until"] > now
    return {
        "provider": IMAGE_PROVIDER,
        "configured": not why,
        "tier": None if why else ("key" if keyed() else "free"),
        "available": not why and not blocked,
        "headline": why or (failure["headline"] if blocked else ""),
        "reason": why or (failure["reason"] if blocked else ""),
        "retry_at": _iso(_state["blocked_until"]) if blocked else None,
        "last_failure": failure,
        "last_success_at": _iso(_state["last_success_at"]),
    }


def _retry_after(response) -> int | None:
    try:
        value = int(float(response.headers.get("retry-after", "")))
        return value if value > 0 else None
    except ValueError:
        return None


def _error_body(response) -> tuple[str, str]:
    """(code, message) from a Pollinations JSON error, or ('', text)."""
    try:
        data = response.json()
    except ValueError:
        return "", response.text.strip()[:300]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("code") or ""), str(err.get("message") or "")
    if isinstance(err, str):
        return "", err
    return "", str(data.get("message") or "") if isinstance(data, dict) else ""


def _headline(status: int, code: str) -> str:
    if code == "FREE_LIMIT":
        return "Pollinations' free limit (one image every 45 seconds) was hit."
    if status == 401:
        return "Pollinations did not accept the API key (IMAGE_API_KEY)." if keyed() else "Pollinations now requires an API key for this request."
    if status == 402:
        return "The Pollinations key has no Pollen left." if keyed() else "Pollinations asked for payment."
    if status == 403:
        return "Pollinations refused the request (forbidden)."
    if status == 429:
        return "Pollinations is rate-limiting this server."
    if status >= 500:
        return f"Pollinations is having problems (HTTP {status})."
    return f"Pollinations returned HTTP {status}."


def _fail(reason: str, headline: str, *, status: int | None = None, code: str = "", retry_after: int | None = None) -> ImageProviderError:
    now = time.time()
    if retry_after:
        cooldown = retry_after
    elif status in (401, 402, 403):
        cooldown = COOLDOWN_ACCOUNT
    else:
        cooldown = COOLDOWN_OTHER
    _state["blocked_until"] = now + cooldown
    _state["last_failure"] = {
        "at": _iso(now), "reason": reason, "headline": headline,
        "status": status, "code": code, "retry_after": retry_after,
    }
    return ImageProviderError(reason, headline=headline, status=status, code=code)


async def generate(prompt: str, width: int, height: int, model: str = "") -> tuple[bytes, str]:
    """Draw one image. Returns (bytes, mime type) or raises ImageProviderError."""
    why = problem()
    if why:
        raise ImageProviderError(why, unavailable=True)

    use_key = keyed()
    url = (KEYED_URL if use_key else FREE_URL) + quote(" ".join((prompt or "").split()), safe="")
    params = {"width": width, "height": height}
    if model:
        params["model"] = model
    if not use_key:
        params["nologo"] = "true"
    headers = {"Authorization": f"Bearer {IMAGE_API_KEY}"} if use_key else {}
    tier = "key" if use_key else "free tier"
    print(f"[IMAGE] Pollinations ({tier}) request: GET {url} {params}")

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException as e:
        logger.warning("[IMAGE] Pollinations (%s) timed out after %ss: %r", tier, int(TIMEOUT), e)
        raise _fail(f"Pollinations did not answer within {int(TIMEOUT)} seconds.", "Pollinations did not answer in time.")
    except httpx.HTTPError as e:
        logger.warning("[IMAGE] Pollinations (%s) request failed: %r", tier, e)
        detail = str(e) or e.__class__.__name__
        raise _fail(f"Could not reach Pollinations: {detail}", "Pollinations could not be reached.")

    ms = int((time.monotonic() - started) * 1000)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    logged = {h: response.headers[h] for h in LOGGED_HEADERS if h in response.headers}

    if response.status_code == 200 and content_type.startswith("image/") and response.content:
        print(f"[IMAGE] Pollinations ({tier}) -> 200 {content_type}, {len(response.content)} bytes in {ms} ms")
        # Every generated image carries the site watermark; none is handed out without it.
        # The free tier stamps its own "pollinations.ai" badge bottom-right (it says so
        # with an X-Pollinations-Logo header, and ignores nologo): sit above it, not on it.
        badge = PROVIDER_BADGE_BAND if "x-pollinations-logo" in response.headers else 0.0
        try:
            data, content_type = watermark.apply(response.content, keep_clear_bottom=badge)
        except (UnidentifiedImageError, OSError) as e:
            logger.warning("[IMAGE] Pollinations (%s) returned an unreadable image: %r", tier, e)
            raise _fail(f"Pollinations returned an image that could not be read ({e}).",
                        "Pollinations returned an unreadable image.", status=200)
        except Exception as e:
            logger.error("[IMAGE] Watermarking failed: %r", e, exc_info=True)
            raise ImageProviderError(f"The image was made but the watermark could not be added: {e}")
        _state["last_success_at"] = time.time()
        _state["last_failure"] = None
        _state["blocked_until"] = 0.0
        return data, content_type

    # Not an image: keep exactly what came back, so the cause is visible later.
    raw = "" if content_type.startswith("image/") else response.text[:RAW_LOG_LIMIT]
    line = f"[IMAGE] Pollinations ({tier}) -> HTTP {response.status_code} in {ms} ms, headers={logged}, body={raw!r}"
    print(line)
    logger.warning(line)

    if response.status_code == 200:
        raise _fail(f"Pollinations answered without an image (content-type {content_type or 'missing'}).",
                    "Pollinations answered without an image.", status=200)

    code, message = _error_body(response)
    retry_after = _retry_after(response)
    headline = _headline(response.status_code, code)
    label = f"HTTP {response.status_code}" + (f" {code}" if code else "")
    reason = f"Pollinations refused the image ({label})" + (f": {message}" if message else ".")
    if response.status_code == 401 and use_key:
        reason += " Check IMAGE_API_KEY in backend/.env."
    raise _fail(reason, headline, status=response.status_code, code=code, retry_after=retry_after)
