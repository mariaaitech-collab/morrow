"""Firestore-backed authentication for BrandAura.

Contracts kept compatible with the existing frontend:
  POST /api/auth/register {username,email,password} -> {access_token,token_type,username}
  POST /api/auth/login    {email,password}          -> {access_token,token_type,username}
New:
  GET  /api/auth/me       (Bearer)                  -> {id,username,email,created_at}
  POST /api/auth/forgot-password {email}
  POST /api/auth/reset-password  {token,new_password}

NOTE: auth events are intentionally NOT recorded in activity history —
history exclusively tracks SaaS usage.
"""
import traceback
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt

import firebase_db
from config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_DAYS, utc_now, RESET_TOKEN_MINUTES, ADMIN_EMAIL
from models import UserCreate, UserLogin, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from security import pwd_context, verify_password, login_rate_limit, forgot_rate_limit, reset_rate_limit, signup_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _public(user: dict) -> dict:
    from deps import compute_subscription
    from deps import _coerce_dt
    created = _coerce_dt(user.get("created_at"))
    sub = compute_subscription(user)
    profile = user.get("profile") or {}
    return {
        "id": user["id"],
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "created_at": created.isoformat() if created else None,
        "plan": sub["plan"],
        "subscribed": sub["subscribed"],
        "is_pro": sub["is_pro"],
        "is_trialing": sub["is_trialing"],
        "is_unlimited": sub.get("is_unlimited", False),
        "trial_ends_at": sub["trial_ends_at"],
        "subscription_ends_at": sub["subscription_ends_at"],
        "days_remaining": sub["days_remaining"],
        "access_active": sub["access_active"],
        "free_tokens": sub["free_tokens"],
        "is_admin": bool(user.get("is_admin")) or (user.get("email", "") or "").lower() == ADMIN_EMAIL,
        "profile": {
            "business_name": profile.get("business_name", ""),
            "business_type": profile.get("business_type", ""),
            "industry": profile.get("industry", ""),
            "bio": profile.get("bio", ""),
            "website": profile.get("website", ""),
            "location": profile.get("location", ""),
        },
    }


@router.post("/signup", response_model=TokenResponse)
@router.post("/register", response_model=TokenResponse)
async def register(user: UserCreate, _: None = Depends(signup_rate_limit)):
    email = user.email.strip().lower()
    username = user.username.strip()
    if not email or not username:
        raise HTTPException(status_code=400, detail="Username and email are required")

    # Explicit, accurate pre-check so we never misreport a real failure as a
    # duplicate email.
    if await firebase_db.user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered")

    now = utc_now()
    doc = {
        "username": username,
        "email": email,
        "password_hash": pwd_context.hash(user.password),
        "created_at": now,
        # 1-Month Free Trial architecture
        "trial_ends_at": now + timedelta(days=30),
        "subscribed": False,
        "plan": "trial",
        "subscription_ends_at": None,
        # Freemium token system: new accounts start with a free-token allowance
        # for core actions (AI content, image generation, auto-posts).
        "free_tokens": 3,
        # Admin account (manual Pro approval) is keyed off the configured admin email.
        "is_admin": email == ADMIN_EMAIL,
    }
    try:
        created = await _create_account(
            firebase_db.db.transaction(),
            firebase_db.user_emails.document(firebase_db.email_key(email)),
            firebase_db.users.document(),
            doc,
        )
    except Exception as e:
        # Never mask unexpected DB errors as a duplicate-email 400.
        print("Registration insert error:", e)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")
    if not created:
        # Only reachable on a true email race; username is intentionally not unique.
        raise HTTPException(status_code=400, detail="Email already registered")

    token = create_access_token({"sub": email, "username": username})
    return TokenResponse(access_token=token, username=username, is_admin=email == ADMIN_EMAIL)


@firebase_db.async_transactional
async def _create_account(transaction, email_ref, user_ref, doc: dict) -> bool:
    """Write the user together with its `user_emails` claim, so two sign-ups with
    the same address can't both succeed. A claim whose account was deleted is reused."""
    claim = await email_ref.get(transaction=transaction)
    if claim.exists:
        owner_id = (claim.to_dict() or {}).get("user_id")
        if firebase_db.valid_id(owner_id) and (
            await firebase_db.users.document(owner_id).get(transaction=transaction)
        ).exists:
            return False
    transaction.set(email_ref, {"email": doc["email"], "user_id": user_ref.id, "created_at": doc["created_at"]})
    transaction.create(user_ref, doc)
    return True


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin, request: Request, _: None = Depends(login_rate_limit)):
    email = user.email.strip().lower()
    db_user = await firebase_db.user_by_email(email)

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify against the current field, then fall back to the legacy `password`
    # field so pre-merge users can still sign in (upgraded transparently).
    ok = False
    for field in ("password_hash", "password"):
        stored = db_user.get(field)
        if stored:
            ok = verify_password(user.password, stored)
            if ok:
                break

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Transparent upgrade to password_hash
    if not db_user.get("password_hash") and db_user.get("password"):
        await firebase_db.users.document(db_user["id"]).update({"password_hash": pwd_context.hash(user.password)})

    # Developer testing override: top up tokens + unlock for this exact email.
    from deps import apply_dev_override
    db_user = await apply_dev_override(db_user)

    token = create_access_token({"sub": email, "username": db_user["username"]})
    is_admin = bool(db_user.get("is_admin")) or (db_user.get("email", "") or "").lower() == ADMIN_EMAIL
    return TokenResponse(access_token=token, username=db_user["username"], is_admin=is_admin)


@router.get("/me")
async def me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")

    email = payload.get("sub")
    db_user = await firebase_db.user_by_email(email) if email else None
    if not db_user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    from deps import apply_dev_override
    db_user = await apply_dev_override(db_user)
    return _public(db_user)


# ---------------------------------------------------------------------------
# Password recovery (SMTP email delivery)
# ---------------------------------------------------------------------------
import hashlib
import secrets
import time

from config import SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_PORT, FRONTEND_URL

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)
# In local/dev (FRONTEND_URL points at localhost) we surface the reset link in
# the API response so the flow works without a configured mail server. This is
# never exposed in production (real domains).
DEV_MODE = urlparse(FRONTEND_URL).hostname in ("localhost", "127.0.0.1", "::1")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _build_reset_email_html(reset_link: str) -> str:
    # Email clients ignore CSS variables, so the Morrow light palette is inlined
    # here (values mirror frontend/src/styles/tokens.css).
    logo_url = f"{FRONTEND_URL.rstrip('/')}/logo.png"
    return """
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#FAF9F7;font-family:Inter,'Segoe UI',Arial,sans-serif;color:#14132B;">
      <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
        <tr><td align="center">
          <table width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background:#FFFFFF;border:1px solid #E4E2EE;border-radius:12px;overflow:hidden;">

            <tr><td style="padding:28px 32px 20px;border-bottom:1px solid #E4E2EE;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;"><img src="LOGO_PLACEHOLDER" width="36" height="36" alt="Morrow" style="display:block;border-radius:10px;"></td>
                <td style="padding-left:12px;">
                  <div style="font-size:20px;font-weight:600;color:#14132B;line-height:1.1;">Morrow</div>
                  <div style="font-size:13px;color:#6B6890;line-height:1.3;">The market of tomorrow</div>
                </td>
              </tr></table>
            </td></tr>

            <tr><td style="padding:28px 32px 8px;">
              <h1 style="margin:0 0 12px;font-size:20px;font-weight:600;color:#14132B;">Reset your password</h1>
              <p style="margin:0;color:#14132B;font-size:15px;line-height:1.6;">
                We received a request to reset the password for your Morrow account.
                Use the button below to choose a new one.
              </p>
            </td></tr>

            <tr><td style="padding:20px 32px;">
              <a href="LINK_PLACEHOLDER" target="_blank"
                 style="display:inline-block;background:#0F766E;color:#FFFFFF;text-decoration:none;
                        font-weight:500;font-size:15px;line-height:36px;height:36px;padding:0 18px;border-radius:8px;">
                Reset password
              </a>
            </td></tr>

            <tr><td style="padding:0 32px 20px;">
              <p style="margin:0;color:#6B6890;font-size:13px;line-height:1.6;">
                If the button doesn't work, paste this link into your browser:
              </p>
              <p style="margin:6px 0 0;font-size:13px;word-break:break-all;">
                <a href="LINK_PLACEHOLDER" style="color:#0F766E;">LINK_PLACEHOLDER</a>
              </p>
            </td></tr>

            <tr><td style="padding:16px 32px 24px;border-top:1px solid #E4E2EE;">
              <p style="margin:0;color:#6B6890;font-size:13px;line-height:1.6;">
                This link expires in MINUTES_PLACEHOLDER minutes. If you didn't request it, you can ignore this email.
              </p>
              <p style="margin:10px 0 0;color:#6B6890;font-size:13px;">
                &copy; 2026 Morrow. The market of tomorrow.
              </p>
            </td></tr>

          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """.replace("LOGO_PLACEHOLDER", logo_url).replace("MINUTES_PLACEHOLDER", str(RESET_TOKEN_MINUTES)).replace("LINK_PLACEHOLDER", reset_link)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request, _: None = Depends(forgot_rate_limit)):
    """Always generic so accounts can't be probed."""
    email = str(body.email).strip().lower()
    resp = {"message": "If that email is registered, a reset link has been sent."}

    try:
        user = await firebase_db.user_by_email(email)
        if not user:
            return resp

        # Secure, URL-safe, unguessable token with a 15-minute expiry. Only its
        # hash is stored, as the document id.
        token = secrets.token_urlsafe(32)
        await firebase_db.password_resets.document(_hash_token(token)).set({
            "user_id": user["id"],
            "token_hash": _hash_token(token),
            "expires_at": utc_now() + timedelta(minutes=RESET_TOKEN_MINUTES),
            "used": False,
            "created_at": utc_now(),
        })

        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"

        # Only attempt delivery when SMTP is actually configured; otherwise the
        # request must not crash. In dev we surface the link server-side.
        if EMAIL_ENABLED:
            try:
                import smtplib
                import asyncio
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                msg = MIMEMultipart("alternative")
                msg["Subject"] = "Morrow — Reset your password"
                msg["From"] = SMTP_FROM or SMTP_USER
                msg["To"] = email
                msg.attach(MIMEText(_build_reset_email_html(reset_link), "html", "utf-8"))

                def _send():
                    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_FROM or SMTP_USER, [email], msg.as_string())
                    server.quit()

                await asyncio.to_thread(_send)
            except Exception as e:
                # Log the raw exception server-side ONLY — never expose it to the client.
                # Return the generic success regardless so we never leak mail-infra
                # failures (and never trigger a client-side "Something went wrong").
                print(f"RESET ERROR: {e}")
                traceback.print_exc()
        if DEV_MODE:
            # Local/dev: email infra is rarely configured, so surface the link
            # directly so the reset flow stays usable without a mail server.
            resp["dev_reset_link"] = reset_link
            resp["dev_reset_token"] = token
            print(f"[DEV] Password reset link for {email}: {reset_link}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"RESET ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Unable to process the reset request.")

    return resp


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, _: None = Depends(reset_rate_limit)):
    # 1. Extract inputs
    token = (body.token or "").strip()
    new_password = body.new_password or ""

    # 2. Validate inputs
    if not token:
        raise HTTPException(status_code=400, detail="A reset token is required.")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    # 3. Validate the token, then 4. persist the new hash (passlib bcrypt). Both
    # happen in one transaction, so a link can never be redeemed twice.
    try:
        reset_ref = firebase_db.password_resets.document(_hash_token(token))
        known = await firebase_db.get(reset_ref)
        if not known or known.get("used"):  # don't spend a bcrypt hash on a dead link
            raise HTTPException(status_code=400, detail="This reset link is invalid or has already been used.")
        pw_hash = pwd_context.hash(new_password)
        await _redeem_reset(firebase_db.db.transaction(), reset_ref, pw_hash)
    except HTTPException:
        raise
    except Exception as e:
        print(f"RESET ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="We couldn't update your password. Please try again later.")

    return {"message": "Password updated successfully. You can now log in with your new password."}


@firebase_db.async_transactional
async def _redeem_reset(transaction, reset_ref, pw_hash: str) -> None:
    snap = await reset_ref.get(transaction=transaction)
    doc = snap.to_dict() if snap.exists else None
    if not doc or doc.get("used"):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has already been used.")

    expires_at = doc.get("expires_at")
    if expires_at is not None:
        now = utc_now()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=now.tzinfo)
        if expires_at < now:
            raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")

    user_id = doc.get("user_id")
    user_ref = firebase_db.users.document(user_id) if firebase_db.valid_id(user_id) else None
    if user_ref is None or not (await user_ref.get(transaction=transaction)).exists:
        raise HTTPException(status_code=400, detail="This account no longer exists.")
    transaction.update(user_ref, {"password_hash": pw_hash})
    transaction.update(reset_ref, {"used": True})


# ---------------------------------------------------------------------------
# TikTok OAuth (server-side callback)
# ---------------------------------------------------------------------------
# Unlike FB/LinkedIn/Instagram (whose callback bounces through the frontend
# Callback page so it can attach the JWT), TikTok's registered redirect_uri
# points straight back to this backend.
#
# Session handling: the connecting user is identified by an opaque, single-use
# `state` nonce. The nonce, the user id and the PKCE code_verifier live in the
# Firestore `oauth_states` collection (10 minutes, TTL on expires_at). The user's JWT
# is NEVER placed in the URL, so it cannot leak to TikTok, proxies or browser
# history, and the flow survives restarts and multiple workers.
#
# Browser binding: the nonce is also set in an HttpOnly cookie on the browser
# that started the flow, and the callback only accepts a `state` that matches
# it. Without this, someone could send a victim an authorize link minted for
# THEIR Morrow account, and the victim's TikTok would be attached to it.
from urllib.parse import urlencode, urlparse
from fastapi import Response
from fastapi.responses import RedirectResponse

from deps import get_current_user
from tiktok_client import TikTokError, generate_pkce, token_record, tiktok

OAUTH_STATE_TTL_SECONDS = 600
STATE_COOKIE = "tiktok_oauth_state"


def _state_cookie_args() -> dict:
    """Cookie attributes, shared by set and delete so the delete always matches.

    The path is the redirect URI's own path, so the cookie is only ever sent
    to the callback, and is right even behind a proxy that rewrites paths.
    """
    uri = urlparse(tiktok.redirect_uri)
    return {"path": uri.path or "/", "secure": uri.scheme == "https", "httponly": True, "samesite": "lax"}


async def create_tiktok_authorization(user: dict, response: Response) -> dict:
    """Mint a PKCE pair + state nonce for `user` and return the authorize URL.

    Also sets the state cookie on `response`, which must be the response the
    user's browser receives.
    """
    if not tiktok.is_configured():
        raise HTTPException(
            status_code=500,
            detail="TikTok is not configured. Add TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI to the .env file.",
        )
    code_verifier, code_challenge = generate_pkce()
    nonce = secrets.token_urlsafe(32)
    now = utc_now()
    await firebase_db.oauth_states.document(nonce).create({
        "provider": "tiktok",
        "user_id": user["id"],
        "code_verifier": code_verifier,
        "created_at": now,
        "expires_at": now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
    })
    try:
        auth_url = tiktok.authorize_url(state=nonce, code_challenge=code_challenge)
    except TikTokError as e:
        raise HTTPException(status_code=500, detail=str(e))
    response.set_cookie(STATE_COOKIE, nonce, max_age=OAUTH_STATE_TTL_SECONDS, **_state_cookie_args())
    return {"platform": "tiktok", "auth_url": auth_url, "status": "ready", "pkce": "S256"}


async def create_oauth_state(user: dict, provider: str) -> str:
    """Mint a single-use CSRF `state` nonce for an OAuth connect flow.

    Stored server-side (10-minute TTL) and bound to the connecting user, so the
    callback can both verify the flow started here and know who it belongs to
    without any credential travelling in the redirect URL.
    """
    nonce = secrets.token_urlsafe(32)
    now = utc_now()
    await firebase_db.oauth_states.document(nonce).create({
        "provider": provider,
        "user_id": user["id"],
        "created_at": now,
        "expires_at": now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
    })
    return nonce


async def consume_oauth_state(nonce: str, provider: str):
    """Atomically pop a state document. Returns None when unknown/expired/replayed."""
    if not nonce or len(nonce) > 128 or not firebase_db.valid_id(nonce):
        return None
    doc = await _pop_state(firebase_db.db.transaction(), firebase_db.oauth_states.document(nonce), provider)
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=utc_now().tzinfo)
        if expires_at < utc_now():
            return None
    return doc


async def _consume_tiktok_state(nonce: str):
    return await consume_oauth_state(nonce, "tiktok")


@firebase_db.async_transactional
async def _pop_state(transaction, ref, provider: str):
    """Read and delete a state document in one step (single use)."""
    snap = await ref.get(transaction=transaction)
    doc = snap.to_dict() if snap.exists else None
    if not doc or doc.get("provider") != provider:
        return None
    transaction.delete(ref)
    return doc


def _dashboard_url(**params) -> str:
    return f"{FRONTEND_URL}/dashboard?{urlencode({k: v for k, v in params.items() if v is not None})}"


@router.get("/tiktok/login")
async def tiktok_login(response: Response, user: dict = Depends(get_current_user)):
    return await create_tiktok_authorization(user, response)


@router.get("/tiktok/status")
async def tiktok_status(user: dict = Depends(get_current_user)):
    """Live diagnostic for the TikTok connection (auth required)."""
    report = await tiktok.check_connection()
    report["pkce_method"] = "S256"
    return report


@router.get("/tiktok/callback")
async def tiktok_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    def finish(url: str):
        # Every outcome ends the attempt, so the state cookie is always cleared.
        resp = RedirectResponse(url, status_code=302)
        resp.delete_cookie(STATE_COOKIE, **_state_cookie_args())
        return resp

    def fail(reason: str):
        return finish(_dashboard_url(connection_success="false", platform="tiktok", error=reason))

    # The user can cancel on TikTok's consent screen; TikTok then redirects
    # with ?error=access_denied instead of a code.
    if error:
        print(f"[AUTH] TikTok authorization returned error={error} ({error_description})")
        await _consume_tiktok_state(state)
        return fail(error[:60])
    if not code:
        print("[AUTH] TikTok callback had neither a code nor an error")
        await _consume_tiktok_state(state)
        return fail("no_code")

    # Browser binding: this browser must be the one that started the flow.
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if not (cookie_state and state and secrets.compare_digest(cookie_state.encode(), state.encode())):
        print(
            "[AUTH] TikTok callback rejected: state does not match this browser's "
            + ("cookie" if cookie_state else "cookie (no state cookie was sent)")
        )
        await _consume_tiktok_state(state)
        return fail("state_mismatch")

    # CSRF + PKCE: the state must be one WE issued, unexpired and unused.
    state_doc = await _consume_tiktok_state(state)
    if not state_doc:
        print("[AUTH] TikTok callback rejected: unknown, expired or replayed state")
        return fail("invalid_state")

    db_user = await firebase_db.get_by_id(firebase_db.users, state_doc.get("user_id"))
    if not db_user:
        return fail("not_authenticated")

    try:
        token_data = await tiktok.exchange_code(code, code_verifier=state_doc["code_verifier"])
    except TikTokError as e:
        print(f"[AUTH] TikTok token exchange rejected: {e}")
        return fail("exchange_failed")
    except Exception as e:
        print(f"[AUTH] TikTok token exchange error: {e}")
        return fail("exchange_failed")

    account = token_record(token_data)
    account["account_name"] = "TikTok user"

    # Pull the display name so the dashboard can show WHO is connected.
    try:
        user_data = await tiktok.user_info(account["access_token"])
        user_obj = (user_data.get("data") or {}).get("user") or {}
        account["account_name"] = user_obj.get("display_name") or user_obj.get("username") or account["account_name"]
        account["username"] = user_obj.get("username", "")
        account["avatar_url"] = user_obj.get("avatar_url", "")
        if user_obj.get("open_id"):
            account["open_id"] = user_obj["open_id"]
    except TikTokError as e:
        print(f"[AUTH] TikTok user info fetch failed (continuing): {e}")

    from routers.social import save_user_account
    save_user_account(db_user["id"], "tiktok", account)
    print(f"[AUTH] Saved TikTok account for {db_user.get('email')} ({account['account_name']})")

    return finish(_dashboard_url(connection_success="true", platform="tiktok"))
