"""Instagram publishing through the Graph API (Business/Creator account linked to a Facebook Page).

    await publish(account, caption, media_url, media_type)
        -> {"status": "success", "post_id": "..."}
        |  {"status": "error", "message": "<what went wrong + how to fix>", "meta": {<Meta error>}}

Never raises: every failure, including Meta's exact error, comes back as an
"error" result so the dashboard and the scheduler can show it.

Flow (Meta Content Publishing API):
  0. GET  /me/permissions                     token valid + required scopes granted
  1. POST /{ig-user-id}/media                 create the media container
  2. GET  /{container-id}?fields=status_code  wait until FINISHED
  3. POST /{ig-user-id}/media_publish         publish the container

Instagram never accepts a multipart upload, and this backend is not reachable
from the internet without a tunnel, so local files reach Meta without one:
  image  uploaded as an UNPUBLISHED photo on the linked Facebook Page; its Meta
         CDN URL is passed as image_url, and the staged photo is deleted after
  video  sent straight to Meta with a resumable Reels upload (rupload.facebook.com)
External https media URLs are passed through unchanged.

Every call uses the Page Access Token of the Page the IG account is linked to.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx

import media_rules
from config import GRAPH_BASE, RUPLOAD_BASE

GRAPH = GRAPH_BASE
REQUIRED_SCOPES = ("instagram_basic", "instagram_content_publish", "pages_read_engagement", "pages_show_list")
# Staging an image on the Page is a (hidden) Page photo upload.
IMAGE_STAGING_SCOPE = "pages_manage_posts"
CAPTION_LIMIT = 2200
POLL_SECONDS = 10
READY_TIMEOUT = {"image": 90, "video": 600}  # Reels often take minutes to process
# On Windows the whole body is handed to the OS at once, so the read timeout
# also bounds how long the upload itself may take. Matches Facebook's 900 s.
RUPLOAD_TIMEOUT = httpx.Timeout(60.0, write=600.0, read=900.0)
PUBLISH_ATTEMPTS = 3

# Plain-language fixes for the Meta error codes users actually hit.
_CODE_HINTS = {
    190: "The Facebook login behind Instagram expired or was revoked. Reconnect Facebook in Channels.",
    10: "A required permission is missing. Reconnect Facebook and approve every Instagram permission.",
    200: "A required permission is missing. Reconnect Facebook and approve every Instagram permission.",
    4: "Meta's rate limit was reached. Wait a few minutes and try again.",
    17: "Meta's rate limit was reached. Wait a few minutes and try again.",
    32: "Meta's rate limit was reached. Wait a few minutes and try again.",
    613: "Meta's rate limit was reached. Wait a few minutes and try again.",
    9004: "Instagram could not download the media file. Re-upload it and try again.",
    36003: "The image aspect ratio is not supported (allowed: 4:5 to 1.91:1).",
    36001: "The image resolution is not supported.",
}
_SUBCODE_HINTS = {
    2207026: "The video format is not supported. Use MP4/MOV with H.264 video and AAC audio, 3 s to 15 min.",
    2207042: "This Instagram account reached its 24-hour publishing limit. Try again tomorrow.",
    2207052: "Instagram could not download the media file. Re-upload it and try again.",
}
_TRANSIENT_CODES = {9007, 2}  # container not ready yet / temporary Meta issue


class IGPublishError(Exception):
    def __init__(self, message: str, meta: dict | None = None, code: int | None = None):
        super().__init__(message)
        self.meta = meta or {}
        self.code = code


def _log(msg: str) -> None:
    print(f"[INSTAGRAM] {time.strftime('%H:%M:%S')} {msg}", flush=True)


# --------------------------------------------------------------------------
# Meta responses
# --------------------------------------------------------------------------
def _meta_error(err: dict, action: str) -> IGPublishError:
    code, subcode = err.get("code"), err.get("error_subcode")
    meta_text = err.get("error_user_msg") or err.get("message") or "Unknown error"
    hint = _SUBCODE_HINTS.get(subcode) or _CODE_HINTS.get(code) or ""
    ref = f"code {code}" + (f"/{subcode}" if subcode else "")
    message = f"{action} failed: {meta_text} ({ref})." + (f" {hint}" if hint else "")
    _log(f"{action} META ERROR {json.dumps(err)}")
    return IGPublishError(message, meta=err, code=code)


def _body(resp: httpx.Response, action: str) -> dict:
    """Parsed JSON body, or IGPublishError carrying Meta's exact error."""
    try:
        body = resp.json()
    except ValueError:
        raise IGPublishError(f"{action} failed: Meta returned HTTP {resp.status_code} {resp.text[:200]}")
    if not isinstance(body, dict):
        raise IGPublishError(f"{action} failed: unexpected response {str(body)[:200]}")
    if "error" in body:
        raise _meta_error(body["error"] or {}, action)
    if resp.status_code != 200:
        raise IGPublishError(f"{action} failed: HTTP {resp.status_code} {json.dumps(body)[:200]}")
    return body


# --------------------------------------------------------------------------
# Account, token and permissions
# --------------------------------------------------------------------------
async def _resolve_target(http: httpx.AsyncClient, account: dict) -> tuple[str, str, str]:
    """(ig_user_id, page_id, page_token) for the Page the IG account is linked to.

    Instagram only accepts the token of that exact Page: never the user token,
    never another Page's token.
    """
    ig_id = account.get("instagram_business_id")
    pages = account.get("pages") or []
    page = next((p for p in pages if ig_id and p.get("instagram_business_id") == ig_id), None)
    if not page:
        page = next((p for p in pages if p.get("instagram_business_id")), None)
    if page:
        ig_id = ig_id or page["instagram_business_id"]
        page_id, page_token = page.get("id"), page.get("access_token")
    else:
        page_id, page_token = account.get("page_id"), account.get("page_access_token")

    if not ig_id and page_id and page_token:
        # Self-heal connections saved before the IG account was linked to the Page.
        resp = await http.get(f"{GRAPH}/{page_id}",
                              params={"fields": "instagram_business_account", "access_token": page_token})
        ig_id = (_body(resp, "Instagram account lookup").get("instagram_business_account") or {}).get("id")

    if not ig_id:
        raise IGPublishError(
            "No Instagram Business/Creator account is linked to your Facebook Page. In the Instagram app, "
            "switch to a Professional account, link it to the Page, then reconnect Facebook."
        )
    if not (page_id and page_token):
        raise IGPublishError("No Page Access Token for the Instagram-linked Page. Reconnect Facebook.")
    return ig_id, page_id, page_token


async def _check_permissions(http: httpx.AsyncClient, user_token: str, need_staging: bool) -> None:
    """Fail fast with a clear message when the token is dead or a scope was not granted."""
    if not user_token:
        return  # legacy record with only a Page token: let the publish calls speak
    try:
        resp = await http.get(f"{GRAPH}/me/permissions", params={"access_token": user_token})
    except httpx.HTTPError as e:
        _log(f"permission check skipped (network): {e}")
        return
    body = _body(resp, "Instagram token check")
    granted = {p.get("permission") for p in body.get("data") or [] if p.get("status") == "granted"}
    needed = REQUIRED_SCOPES + ((IMAGE_STAGING_SCOPE,) if need_staging else ())
    missing = [s for s in needed if s not in granted]
    if missing:
        raise IGPublishError(
            f"Instagram publishing needs these permissions: {', '.join(missing)}. "
            "Reconnect Facebook in Channels and approve all of them."
        )


# --------------------------------------------------------------------------
# Getting the media to Meta
# --------------------------------------------------------------------------
async def _stage_image(http: httpx.AsyncClient, page_id: str, page_token: str, path: str) -> tuple[str, str]:
    """Upload an unpublished Page photo; return (photo_id, largest Meta CDN url)."""
    with open(path, "rb") as f:
        data = f.read()
    resp = await http.post(
        f"{GRAPH}/{page_id}/photos",
        data={"published": "false", "access_token": page_token},
        files={"source": (os.path.basename(path), data, "image/jpeg")},
    )
    photo_id = _body(resp, "Instagram image staging").get("id")
    if not photo_id:
        raise IGPublishError("Instagram image staging failed: Meta returned no photo id.")
    resp = await http.get(f"{GRAPH}/{photo_id}", params={"fields": "images", "access_token": page_token})
    images = _body(resp, "Instagram image staging").get("images") or []
    if not images:
        await _delete_staged(http, photo_id, page_token)
        raise IGPublishError("Instagram image staging failed: Meta returned no image URL.")
    return photo_id, max(images, key=lambda i: i.get("width", 0))["source"]


async def _delete_staged(http: httpx.AsyncClient, photo_id: str | None, page_token: str) -> None:
    if not photo_id:
        return
    try:
        await http.delete(f"{GRAPH}/{photo_id}", params={"access_token": page_token})
    except Exception as e:  # cosmetic: an unpublished photo is invisible to followers
        _log(f"could not delete staged photo {photo_id}: {e}")


async def _create_container(http: httpx.AsyncClient, ig_id: str, token: str, caption: str,
                            media_type: str, image_url: str | None = None,
                            video_url: str | None = None, video_path: str | None = None) -> str:
    if media_type != "video":
        resp = await http.post(f"{GRAPH}/{ig_id}/media",
                               data={"image_url": image_url, "caption": caption, "access_token": token})
        return _container_id(_body(resp, "Instagram image container"))

    if video_url:
        resp = await http.post(f"{GRAPH}/{ig_id}/media", data={
            "media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": token,
        })
        return _container_id(_body(resp, "Instagram video container"))

    resp = await http.post(f"{GRAPH}/{ig_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "access_token": token,
    })
    body = _body(resp, "Instagram video container")
    container_id = _container_id(body)
    upload_uri = body.get("uri") or f"{RUPLOAD_BASE}/{container_id}"
    with open(video_path, "rb") as f:
        data = f.read()
    _log(f"uploading {media_rules.human(len(data))} video to container {container_id}: POST {upload_uri} "
         f"({'uri from Meta' if body.get('uri') else 'RUPLOAD_BASE fallback'})")
    started = time.monotonic()
    try:
        resp = await http.post(
            upload_uri,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))},
            content=data,
            timeout=RUPLOAD_TIMEOUT,
        )
    except httpx.HTTPError as e:
        _log(f"rupload gave up after {time.monotonic() - started:.0f}s: {type(e).__name__} "
             f"(write timeout {RUPLOAD_TIMEOUT.write:.0f}s, read timeout {RUPLOAD_TIMEOUT.read:.0f}s)")
        raise
    secs = time.monotonic() - started
    _log(f"rupload answered HTTP {resp.status_code} after {secs:.0f}s "
         f"({len(data) / 1048576 / max(secs, 0.001):.2f} MB/s average, including Meta's reply time)")
    result = _body(resp, "Instagram video upload")
    if result.get("success") is False:
        raise IGPublishError(f"Instagram video upload failed: {result.get('message') or json.dumps(result)[:200]}")
    return container_id


def _container_id(body: dict) -> str:
    if not body.get("id"):
        raise IGPublishError(f"Instagram did not return a container id: {json.dumps(body)[:200]}")
    return body["id"]


# --------------------------------------------------------------------------
# Wait + publish
# --------------------------------------------------------------------------
async def _wait_until_ready(http: httpx.AsyncClient, container_id: str, token: str, media_type: str) -> None:
    kind = "video" if media_type == "video" else "image"
    deadline = READY_TIMEOUT[kind]
    waited, network_errors = 0, 0
    while waited < deadline:
        await asyncio.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        try:
            resp = await http.get(f"{GRAPH}/{container_id}",
                                  params={"fields": "status_code,status", "access_token": token})
        except httpx.HTTPError as e:
            network_errors += 1
            _log(f"container {container_id} poll at {waited}s: {type(e).__name__} (network error {network_errors}/5)")
            if network_errors >= 5:
                raise IGPublishError(f"Lost contact with Instagram while it processed the {kind}: {e}")
            continue
        body = _body(resp, f"Instagram {kind} processing")
        status_code = body.get("status_code")
        _log(f"container {container_id} poll at {waited}s/{deadline}s: {status_code} ({body.get('status') or ''})")
        if status_code in ("FINISHED", "PUBLISHED"):
            _log(f"container {container_id} ready after {waited}s")
            return
        if status_code == "ERROR":
            # `status` carries Meta's reason, e.g. "Error: ... 2207026".
            reason = body.get("status") or "no reason given"
            _log(f"container {container_id} ERROR: {reason}")
            hint = next((h for sub, h in _SUBCODE_HINTS.items() if str(sub) in reason), "")
            raise IGPublishError(f"Instagram could not process the {kind}: {reason}." + (f" {hint}" if hint else ""),
                                 meta=body)
        if status_code == "EXPIRED":
            raise IGPublishError(f"The Instagram {kind} container expired before it was published. Try again.")
    raise IGPublishError(f"Instagram was still processing the {kind} after {deadline}s. Try again shortly.")


async def _publish_container(http: httpx.AsyncClient, ig_id: str, token: str, container_id: str) -> str:
    for attempt in range(1, PUBLISH_ATTEMPTS + 1):
        resp = await http.post(f"{GRAPH}/{ig_id}/media_publish",
                               data={"creation_id": container_id, "access_token": token})
        try:
            media_id = _body(resp, "Instagram publish").get("id")
            if not media_id:
                raise IGPublishError("Instagram publish failed: Meta returned no media id.")
            return media_id
        except IGPublishError as e:
            if e.code in _TRANSIENT_CODES and attempt < PUBLISH_ATTEMPTS:
                _log(f"publish attempt {attempt} not ready yet; retrying in 5s")
                await asyncio.sleep(5)
                continue
            raise


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
async def publish(account: dict, caption: str, media_url: str | None, media_type: str | None) -> dict:
    if not media_url:
        return {"status": "error", "message": "Instagram requires an image or a video. Attach one and try again."}
    media_type = "video" if media_type == "video" else "image"
    caption = (caption or "")[:CAPTION_LIMIT]

    local_path = media_rules.local_path_for(media_url)
    if not local_path and media_rules.is_private_url(media_url):
        return {"status": "error", "message": "The media file was not found on the server. Please re-upload it."}
    problem = media_rules.check_for_platform("instagram", local_path, media_type)
    if problem:
        return {"status": "error", "message": problem}

    staged_photo_id = None
    page_token = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, write=600.0)) as http:
        try:
            ig_id, page_id, page_token = await _resolve_target(http, account)
            await _check_permissions(http, account.get("access_token", ""),
                                     need_staging=bool(local_path) and media_type == "image")
            _log(f"publish start ig_id={ig_id} type={media_type} source={'local' if local_path else 'url'}")

            if media_type == "image":
                image_url = media_url
                if local_path:
                    # JPEG, 4:5..1.91:1, 320-1440 px wide, <= 8 MB.
                    fitted = media_rules.prepare_instagram_image(local_path)
                    staged_photo_id, image_url = await _stage_image(http, page_id, page_token, fitted)
                container_id = await _create_container(http, ig_id, page_token, caption, media_type,
                                                       image_url=image_url)
            else:
                container_id = await _create_container(
                    http, ig_id, page_token, caption, media_type,
                    video_url=None if local_path else media_url, video_path=local_path,
                )

            _log(f"container {container_id} created; waiting for Instagram to process it")
            await _wait_until_ready(http, container_id, page_token, media_type)
            post_id = await _publish_container(http, ig_id, page_token, container_id)
            _log(f"published media {post_id}")
            return {"status": "success", "post_id": post_id}
        except IGPublishError as e:
            _log(f"publish FAILED: {e}")
            return {"status": "error", "message": str(e), "meta": e.meta}
        except httpx.HTTPError as e:
            _log(f"publish FAILED (network): {type(e).__name__}: {e}")
            return {"status": "error", "message": f"Could not reach Instagram ({type(e).__name__}). Check the connection and try again."}
        except Exception as e:  # e.g. an unreadable image file
            _log(f"publish FAILED (unexpected): {type(e).__name__}: {e}")
            return {"status": "error", "message": f"Instagram publishing failed: {e}"}
        finally:
            await _delete_staged(http, staged_photo_id, page_token)
