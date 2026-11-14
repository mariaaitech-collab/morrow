"""TikTok API client for BrandAura (Login Kit OAuth + Content Posting API).

Credentials come exclusively from the .env file via config.py:
    TIKTOK_CLIENT_KEY      (TikTok calls the app id the "Client Key")
    TIKTOK_CLIENT_SECRET
    TIKTOK_REDIRECT_URI
    TIKTOK_SCOPES          (optional, comma separated)

Usage:
    from tiktok_client import tiktok

    tiktok.is_configured()                       -> bool
    tiktok.authorize_url(state=..., code_challenge=...) -> str
    await tiktok.exchange_code(code, code_verifier)     -> dict
    await tiktok.refresh(refresh_token)                 -> dict
    await tiktok.refresh_if_needed(account)             -> bool (mutates account)
    await tiktok.revoke(access_token)                   -> dict
    await tiktok.user_info(access_token)                -> dict
    await tiktok.creator_info(access_token)             -> dict
    await tiktok.publish_video(...)                     -> publish_id (init + upload)
    await tiktok.start_video_upload(...)                -> dict (init only, fast)
    await tiktok.upload_video(upload)                   -> None (the slow byte upload)
    await tiktok.publish_status(...)                    -> dict
    tiktok.interpret_publish_status(body)               -> (outcome, status, message)
    await tiktok.publish_and_wait(...)                  -> dict
    await tiktok.reply_to_comment(...)                  -> dict  (TikTok API for Business)
    await tiktok.check_connection()                     -> dict  (live connectivity probe)

Response envelope notes (the source of most historic bugs):
  * v2 Open API success bodies ALWAYS contain ``"error": {"code": "ok"}``.
    Only a code other than "ok" is a failure.
  * The OAuth token endpoint returns a FLAT body; on failure ``error`` is a
    plain string with an ``error_description``.
  * The Business API returns ``{"code": 0, "message": "OK", "data": {...}}``.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI,
    TIKTOK_SCOPES,
)

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
API_BASE = "https://open.tiktokapis.com/v2"
USER_INFO_URL = f"{API_BASE}/user/info/"
CREATOR_INFO_URL = f"{API_BASE}/post/publish/creator_info/query/"
PUBLISH_INIT_URL = f"{API_BASE}/post/publish/video/init/"
PUBLISH_STATUS_URL = f"{API_BASE}/post/publish/status/fetch/"
BUSINESS_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"
BUSINESS_COMMENT_REPLY_URL = f"{BUSINESS_API_BASE}/business/comment/reply/create/"

# The backend route that handles TikTok's redirect (routers/auth.py).
# TIKTOK_REDIRECT_URI must point at it.
CALLBACK_ROUTE = "/api/auth/tiktok/callback"

# Values that must never reach a log line.
_SENSITIVE_PARAMS = {"client_secret", "code", "code_verifier", "refresh_token", "access_token"}


def _redacted(params: dict) -> dict:
    return {k: ("***redacted***" if k in _SENSITIVE_PARAMS else v) for k, v in params.items()}


# Must list only scopes added to the app in the TikTok portal; requesting any
# other scope makes the authorize page fail with a "scope" error.
DEFAULT_SCOPES = "user.info.basic,video.upload,video.publish"
TIMEOUT = 30.0
PUBLISH_TIMEOUT = 300.0

# Refresh the access token this many seconds before it actually expires.
TOKEN_REFRESH_MARGIN = 300

# Chunking rules from the Content Posting API "Media Transfer Guide":
#   * a video <= 64 MB may be sent as ONE chunk (chunk_size == video_size);
#   * otherwise every chunk is 5-64 MB, total_chunk_count = floor(size/chunk)
#     and the final chunk absorbs the trailing bytes (up to 128 MB).
MIN_CHUNK_SIZE = 5 * 1024 * 1024
MAX_CHUNK_SIZE = 64 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024
MAX_CHUNK_COUNT = 1000

# TikTok only accepts MP4, MOV and WebM containers.
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}
SUPPORTED_VIDEO_EXTENSIONS = tuple(VIDEO_MIME_TYPES)

TITLE_MAX_CHARS = 2200


def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for the S256 PKCE flow.

    TikTok's Login Kit REQUIRES PKCE: without `code_challenge` the authorize
    page fails with "Something went wrong ... code_challenge".
    The verifier is a high-entropy random string (43-128 chars, per RFC 7636)
    and the challenge is its base64url-encoded SHA-256 (no padding).
    """
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def plan_chunks(video_size: int) -> tuple[int, int]:
    """Return ``(chunk_size, total_chunk_count)`` that TikTok will accept."""
    if video_size <= 0:
        raise TikTokError("The video file is empty.")
    if video_size <= MAX_CHUNK_SIZE:
        return video_size, 1
    chunk_size = DEFAULT_CHUNK_SIZE
    count = video_size // chunk_size
    if count > MAX_CHUNK_COUNT:
        raise TikTokError("The video is too large for TikTok's upload limits.")
    return chunk_size, count


def token_record(token_data: dict) -> dict:
    """Normalize a TikTok token response into what we persist per account."""
    now = int(time.time())
    expires_in = int(token_data.get("expires_in") or 0)
    refresh_expires_in = int(token_data.get("refresh_expires_in") or 0)
    return {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "open_id": token_data.get("open_id", ""),
        "scope": token_data.get("scope", ""),
        "expires_at": now + expires_in if expires_in else None,
        "refresh_expires_at": now + refresh_expires_in if refresh_expires_in else None,
    }


class TikTokError(RuntimeError):
    """Raised when TikTok rejects a request or is unreachable."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class TikTokClient:
    """Thin, dependency-light wrapper around the TikTok v2 Open API."""

    def __init__(
        self,
        client_key: str = TIKTOK_CLIENT_KEY,
        client_secret: str = TIKTOK_CLIENT_SECRET,
        redirect_uri: str = TIKTOK_REDIRECT_URI,
        scopes: str = TIKTOK_SCOPES or DEFAULT_SCOPES,
    ):
        self.client_key = (client_key or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.redirect_uri = (redirect_uri or "").strip()
        # TikTok expects a comma-separated list without spaces.
        self.scopes = ",".join(s.strip() for s in (scopes or DEFAULT_SCOPES).split(",") if s.strip())

    # -- config -----------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret and self.redirect_uri)

    def masked_key(self) -> str:
        if not self.client_key:
            return ""
        return f"{self.client_key[:4]}...{self.client_key[-4:]}"

    def _require_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("TIKTOK_CLIENT_KEY", self.client_key),
                ("TIKTOK_CLIENT_SECRET", self.client_secret),
                ("TIKTOK_REDIRECT_URI", self.redirect_uri),
            )
            if not value
        ]
        if missing:
            raise TikTokError("Missing TikTok credentials in .env: " + ", ".join(missing))

    def config_warnings(self) -> list[str]:
        """Problems that will make TikTok reject the login, checked at startup."""
        missing = [
            name
            for name, value in (
                ("TIKTOK_CLIENT_KEY", self.client_key),
                ("TIKTOK_CLIENT_SECRET", self.client_secret),
                ("TIKTOK_REDIRECT_URI", self.redirect_uri),
            )
            if not value
        ]
        if missing:
            return ["TikTok connect is disabled: " + ", ".join(missing) + " not set in .env"]
        problems = []
        uri = urlparse(self.redirect_uri)
        if uri.scheme != "https":
            problems.append(
                f"TIKTOK_REDIRECT_URI={self.redirect_uri} is not https; TikTok only accepts https "
                "redirect URIs, so it cannot match the TikTok portal"
            )
        if not uri.path.endswith(CALLBACK_ROUTE):
            problems.append(
                f"TIKTOK_REDIRECT_URI path is {uri.path or '/'} but this backend handles the "
                f"callback at {CALLBACK_ROUTE}"
            )
        if uri.query or uri.fragment:
            problems.append("TIKTOK_REDIRECT_URI must not contain a query string or #fragment")
        return problems

    # -- OAuth ------------------------------------------------------------
    def authorize_url(
        self,
        state: str = "",
        scopes: str | None = None,
        code_challenge: str = "",
    ) -> str:
        """Build the Login Kit authorize URL.

        `code_challenge` is REQUIRED by TikTok. Pass the S256 challenge from
        `generate_pkce()` or the authorize page errors out.
        """
        self._require_config()
        if not code_challenge:
            raise TikTokError("TikTok requires a PKCE code_challenge on the authorize URL.")
        params = {
            "client_key": self.client_key,
            "response_type": "code",
            "scope": scopes or self.scopes,
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if state:
            params["state"] = state
        # The authorize URL carries no secrets; redaction is a guard in case
        # one is ever added to `params`.
        print(f"[TIKTOK] Authorize URL: {AUTHORIZE_URL}?{urlencode(_redacted(params))}")
        return AUTHORIZE_URL + "?" + urlencode(params)

    def pkce_authorize_url(self, state: str = "", scopes: str | None = None) -> tuple[str, str]:
        """Authorize URL + the matching `code_verifier` to keep for the exchange."""
        verifier, challenge = generate_pkce()
        return self.authorize_url(state=state, scopes=scopes, code_challenge=challenge), verifier

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        self._require_config()
        if not code_verifier:
            raise TikTokError("Missing PKCE code_verifier for the TikTok token exchange.")
        data = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }
        print(f"[TIKTOK] Token exchange POST {TOKEN_URL} (form-encoded): {_redacted(data)}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(TOKEN_URL, data=data, headers=_form_headers())
        body = self._parse(resp, "token exchange")
        if not body.get("access_token"):
            raise TikTokError("TikTok token exchange returned no access_token", payload=body)
        return body

    async def refresh(self, refresh_token: str) -> dict:
        self._require_config()
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(
                TOKEN_URL,
                headers=_form_headers(),
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        body = self._parse(resp, "token refresh")
        if not body.get("access_token"):
            raise TikTokError("TikTok token refresh returned no access_token", payload=body)
        return body

    async def refresh_if_needed(self, account: dict) -> bool:
        """Refresh `account` in place when its access token is (nearly) expired.

        Returns True when the account was changed and must be persisted.
        TikTok access tokens live 24 hours; refresh tokens live 365 days.
        Accounts saved before expiry tracking existed carry no `expires_at`,
        so they are refreshed once to learn their real expiry.
        """
        refresh_token = account.get("refresh_token")
        if not refresh_token:
            return False
        expires_at = account.get("expires_at")
        if expires_at and time.time() < float(expires_at) - TOKEN_REFRESH_MARGIN:
            return False
        refresh_expires_at = account.get("refresh_expires_at")
        if refresh_expires_at and time.time() >= float(refresh_expires_at):
            raise TikTokError("Your TikTok session has expired. Reconnect your TikTok account.")

        body = await self.refresh(refresh_token)
        record = token_record(body)
        account.update({k: v for k, v in record.items() if v not in (None, "")})
        return True

    async def revoke(self, access_token: str) -> dict:
        self._require_config()
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(
                REVOKE_URL,
                headers=_form_headers(),
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "token": access_token,
                },
            )
        return self._parse(resp, "token revoke")

    # -- read APIs --------------------------------------------------------
    async def user_info(self, access_token: str, fields: str = "open_id,union_id,display_name,avatar_url") -> dict:
        # v2 requires the token in the Authorization header, NOT the query.
        if "user.info.profile" in self.scopes and "username" not in fields:
            fields += ",username"
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.get(
                USER_INFO_URL,
                params={"fields": fields},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        return self._parse(resp, "user info")

    async def creator_info(self, access_token: str) -> dict:
        """Query the creator's posting capabilities (privacy options, limits).

        TikTok requires this call before a Direct Post. Its
        `privacy_level_options` tells us which privacy levels are allowed.
        Unaudited apps can only post SELF_ONLY.
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(CREATOR_INFO_URL, headers=_bearer(access_token), json={})
        return self._parse(resp, "creator info")

    @staticmethod
    def choose_privacy_level(creator: dict, preferred: str = "PUBLIC_TO_EVERYONE") -> str:
        options = ((creator or {}).get("data") or {}).get("privacy_level_options") or []
        if not options or preferred in options:
            return preferred
        if "SELF_ONLY" in options:
            return "SELF_ONLY"
        return options[0]

    # -- content posting API ---------------------------------------------
    async def publish_video(
        self,
        access_token: str,
        video_path: str,
        title: str = "",
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
    ) -> str:
        """Direct-post a local video file. Returns the TikTok `publish_id`.

        STEP 1  POST /post/publish/video/init/  -> publish_id + signed upload_url
        STEP 2  PUT  upload_url, one request per chunk with Content-Range.
        The caller is responsible for polling `publish_status()`.
        """
        upload = await self.start_video_upload(
            access_token, video_path, title=title, privacy_level=privacy_level,
            disable_duet=disable_duet, disable_comment=disable_comment, disable_stitch=disable_stitch,
        )
        await self.upload_video(upload)
        return upload["publish_id"]

    async def start_video_upload(
        self,
        access_token: str,
        video_path: str,
        title: str = "",
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
    ) -> dict:
        """STEP 1 only (fast): register the post with TikTok.

        Returns the `publish_id` plus everything `upload_video()` needs, so the
        slow byte upload can run separately (e.g. in a background task).
        """
        self._require_config()
        ext = os.path.splitext(video_path)[1].lower()
        mime = VIDEO_MIME_TYPES.get(ext)
        if not mime:
            raise TikTokError(
                f"TikTok only accepts {', '.join(SUPPORTED_VIDEO_EXTENSIONS)} videos (got '{ext or 'unknown'}')."
            )

        video_size = os.path.getsize(video_path)
        chunk_size, chunk_count = plan_chunks(video_size)

        payload = {
            "post_info": {
                "title": (title or "").strip()[:TITLE_MAX_CHARS],
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_comment": disable_comment,
                "disable_stitch": disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": chunk_count,
            },
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            init_resp = await http.post(PUBLISH_INIT_URL, headers=_bearer(access_token), json=payload)
        init_data = self._parse(init_resp, "upload init")

        data = init_data.get("data") or {}
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")
        if not upload_url:
            raise TikTokError("TikTok init response missing upload_url", payload=init_data)
        if not publish_id:
            raise TikTokError("TikTok init response missing publish_id", payload=init_data)
        return {
            "publish_id": publish_id,
            "upload_url": upload_url,
            "video_path": video_path,
            "video_size": video_size,
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "mime": mime,
        }

    async def upload_video(self, upload: dict) -> None:
        """STEP 2 (slow): PUT the bytes to the signed upload_url, chunk by chunk.

        `upload` is the dict returned by `start_video_upload()`. TikTok's
        upload_url stays valid for one hour.
        """
        upload_url, video_path, mime = upload["upload_url"], upload["video_path"], upload["mime"]
        video_size, chunk_size, chunk_count = upload["video_size"], upload["chunk_size"], upload["chunk_count"]
        # Long read/write allowance per chunk, but fail fast if TikTok is unreachable.
        async with httpx.AsyncClient(timeout=httpx.Timeout(PUBLISH_TIMEOUT, connect=TIMEOUT)) as http:
            with open(video_path, "rb") as fh:
                for index in range(chunk_count):
                    start = index * chunk_size
                    # The final chunk carries every remaining byte.
                    end = video_size - 1 if index == chunk_count - 1 else start + chunk_size - 1
                    fh.seek(start)
                    chunk = fh.read(end - start + 1)
                    upload_resp = await http.put(
                        upload_url,
                        headers={
                            "Content-Type": mime,
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {start}-{end}/{video_size}",
                        },
                        content=chunk,
                    )
                    if upload_resp.status_code not in (200, 201, 206):
                        raise TikTokError(
                            f"TikTok video upload rejected (chunk {index + 1}/{chunk_count}): "
                            f"HTTP {upload_resp.status_code} {upload_resp.text[:400]}",
                            status_code=upload_resp.status_code,
                        )

    @staticmethod
    def interpret_publish_status(body: dict) -> tuple[str, str, str]:
        """Map a publish-status body to ``(outcome, tiktok_status, message)``.

        outcome is "success", "error" or "processing". PUBLISH_COMPLETE is the
        end state of a Direct Post; SEND_TO_USER_INBOX is the end state of an
        inbox upload (the creator finishes the post in the TikTok app).
        """
        data = (body or {}).get("data") or {}
        status = (data.get("status") or "").upper()
        if status == "PUBLISH_COMPLETE":
            return "success", status, "TikTok video published."
        if status == "SEND_TO_USER_INBOX":
            return "success", status, "Video sent to your TikTok inbox. Open TikTok to finish posting it."
        if status == "FAILED":
            return "error", status, f"TikTok failed to publish the video: {data.get('fail_reason') or 'unknown reason'}"
        if status == "PROCESSING_UPLOAD":
            return "processing", status, "TikTok is receiving the video…"
        return "processing", status or "PROCESSING", "TikTok is processing the video…"

    async def publish_status(self, access_token: str, publish_id: str) -> dict:
        """Poll a publish job. Returns the raw TikTok response body."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(
                PUBLISH_STATUS_URL,
                headers=_bearer(access_token),
                json={"publish_id": publish_id},
            )
        return self._parse(resp, "publish status fetch")

    async def publish_and_wait(
        self,
        access_token: str,
        video_path: str,
        title: str = "",
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        poll_seconds: float = 3.0,
        max_polls: int = 60,
    ) -> dict:
        """publish_video + poll until PUBLISH_COMPLETE / FAILED."""
        publish_id = await self.publish_video(access_token, video_path, title=title, privacy_level=privacy_level)
        last_status = ""
        for _ in range(max_polls):
            await asyncio.sleep(poll_seconds)
            body = await self.publish_status(access_token, publish_id)
            data = body.get("data") or {}
            last_status = (data.get("status") or "").upper()
            if last_status == "PUBLISH_COMPLETE":
                return {"publish_id": publish_id, "status": last_status, "privacy_level": privacy_level}
            if last_status == "FAILED":
                raise TikTokError(
                    f"TikTok failed to publish the video: {data.get('fail_reason') or 'unknown reason'}",
                    payload=body,
                )
        raise TikTokError(
            f"TikTok publish timed out after {max_polls} polls (last status: {last_status or 'unknown'}).",
            payload={"publish_id": publish_id, "status": last_status},
        )

    # -- engagement (TikTok API for Business) ------------------------------
    async def reply_to_comment(
        self, access_token: str, business_id: str, video_id: str, comment_id: str, text: str
    ) -> dict:
        """Reply to a comment on a TikTok Business account video.

        Requires a TikTok API for Business access token with the comment
        management scope. Login Kit tokens are rejected by this endpoint.
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(
                BUSINESS_COMMENT_REPLY_URL,
                headers={"Access-Token": access_token, "Content-Type": "application/json"},
                json={
                    "business_id": business_id,
                    "video_id": video_id,
                    "comment_id": comment_id,
                    "text": text[:150],
                },
            )
        return self._parse(resp, "comment reply")

    # -- diagnostics ------------------------------------------------------
    async def check_connection(self) -> dict:
        """Live reachability probe. Never raises; always returns a report."""
        report: dict[str, Any] = {
            "configured": self.is_configured(),
            "client_key_masked": self.masked_key(),
            "redirect_uri": self.redirect_uri,
            "scopes": self.scopes,
            "api_host_reachable": False,
            "http_status": None,
            "latency_ms": None,
            "ok": False,
            "detail": "",
        }
        if not report["configured"]:
            report["detail"] = "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_REDIRECT_URI missing in .env"
            return report

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as http:
                # A client_credentials grant validates the key/secret pair
                # without any user involvement.
                resp = await http.post(
                    TOKEN_URL,
                    headers=_form_headers(),
                    data={
                        "client_key": self.client_key,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                    },
                )
            report["api_host_reachable"] = True
            report["http_status"] = resp.status_code
            report["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
            try:
                body = resp.json()
            except Exception:
                body = {}
            if body.get("access_token"):
                report["ok"] = True
                report["detail"] = "TikTok Open API reachable and client key/secret accepted."
            else:
                err = body.get("error_description") or body.get("error") or f"HTTP {resp.status_code}"
                report["detail"] = f"TikTok rejected the client credentials: {err}"
        except Exception as exc:  # network/DNS/TLS problems
            report["detail"] = f"Could not reach TikTok Open API: {exc}"
        return report

    # -- internals --------------------------------------------------------
    @staticmethod
    def _parse(resp: httpx.Response, action: str) -> dict:
        try:
            data = resp.json()
        except Exception:
            raise TikTokError(
                f"TikTok {action} returned non-JSON ({resp.status_code}): {resp.text[:200]}",
                status_code=resp.status_code,
            )
        if not isinstance(data, dict):
            raise TikTokError(f"TikTok {action} returned an unexpected body", status_code=resp.status_code, payload=data)

        failed = False
        message = ""
        err = data.get("error")
        if isinstance(err, dict):
            # v2 Open API: {"error": {"code": "ok", ...}} on SUCCESS.
            code = err.get("code")
            if code not in (None, "", "ok", 0):
                failed = True
                message = err.get("message") or str(code)
        elif isinstance(err, str) and err:
            # OAuth endpoints: {"error": "invalid_grant", "error_description": "..."}
            failed = True
            message = data.get("error_description") or err

        biz_code = data.get("code")
        if isinstance(biz_code, int) and biz_code != 0:
            # Business API envelope.
            failed = True
            message = message or data.get("message") or f"code {biz_code}"

        if resp.status_code >= 400 or failed:
            raise TikTokError(
                f"TikTok {action} failed: {message or resp.text[:300]}",
                status_code=resp.status_code,
                payload=data,
            )
        return data


def _bearer(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _form_headers() -> dict:
    return {"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"}


# Shared, ready-to-use client instance.
tiktok = TikTokClient()
