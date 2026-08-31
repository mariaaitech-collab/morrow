"""MongoDB-backed authentication for BrandAura.

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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pymongo.errors import DuplicateKeyError

import mongodb
from config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_DAYS, utc_now, RESET_TOKEN_MINUTES, ADMIN_EMAIL
from models import UserCreate, UserLogin, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from security import pwd_context, verify_password, login_rate_limit, forgot_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _public(user: dict) -> dict:
    from deps import compute_subscription
    created = user.get("created_at")
    sub = compute_subscription(user)
    return {
        "id": str(user["_id"]),
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "created_at": created.isoformat() if created else None,
        "plan": sub["plan"],
        "subscribed": sub["subscribed"],
        "is_pro": sub["is_pro"],
        "is_trialing": sub["is_trialing"],
        "trial_ends_at": sub["trial_ends_at"],
        "subscription_ends_at": sub["subscription_ends_at"],
        "days_remaining": sub["days_remaining"],
        "access_active": sub["access_active"],
        "is_admin": bool(user.get("is_admin")) or (user.get("email", "") or "").lower() == ADMIN_EMAIL,
    }


@router.post("/signup", response_model=TokenResponse)
@router.post("/register", response_model=TokenResponse)
async def register(user: UserCreate):
    email = user.email.strip().lower()
    username = user.username.strip()
    if not email or not username:
        raise HTTPException(status_code=400, detail="Username and email are required")

    # Explicit, accurate pre-check so we never misreport a real failure as a
    # duplicate email.
    if await mongodb.users.find_one({"email": email}):
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
        # Admin account (manual Pro approval) is keyed off the configured admin email.
        "is_admin": email == ADMIN_EMAIL,
    }
    try:
        result = await mongodb.users.insert_one(doc)
    except DuplicateKeyError:
        # Only reachable on a true email race; username is intentionally not unique.
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        # Never mask unexpected DB errors as a duplicate-email 400.
        print("Registration insert error:", e)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

    token = create_access_token({"sub": email, "username": username})
    _ = result.inserted_id
    return TokenResponse(access_token=token, username=username, is_admin=email == ADMIN_EMAIL)


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin, request: Request, _: None = Depends(login_rate_limit)):
    email = user.email.strip().lower()
    db_user = await mongodb.users.find_one({"email": email})

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
        await mongodb.users.update_one(
            {"_id": db_user["_id"]},
            {"$set": {"password_hash": pwd_context.hash(user.password)}},
        )

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
    db_user = await mongodb.users.find_one({"email": email}) if email else None
    if not db_user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return _public(db_user)


# ---------------------------------------------------------------------------
# Password recovery (SMTP email delivery)
# ---------------------------------------------------------------------------
import hashlib
import secrets

from config import SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_PORT, FRONTEND_URL

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)
# In local/dev (FRONTEND_URL points at localhost) we surface the reset link in
# the API response so the flow works without a configured mail server. This is
# never exposed in production (real domains).
DEV_MODE = "localhost" in FRONTEND_URL


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _build_reset_email_html(reset_link: str) -> str:
    return """
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#0a1e2b;font-family:'Segoe UI',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
        <tr><td align="center">
          <table width="480" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#123346,#0f2d3d);border-radius:20px;border:1px solid rgba(255,255,255,0.1);overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,0.4);">

            <tr><td style="padding:36px 40px 20px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="background:linear-gradient(135deg,#00B894,#0a7c91);width:38px;height:38px;border-radius:10px;text-align:center;vertical-align:middle;font-weight:800;font-size:16px;color:#fff;">B</td>
                <td style="padding-left:12px;font-size:20px;font-weight:700;color:#eaf5f5;">Brand<span style="color:#00B894;">Aura</span></td>
              </tr></table>
            </td></tr>

            <tr><td style="padding:8px 40px 0;">
              <div style="width:100%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.1),transparent);"></div>
            </td></tr>

            <tr><td style="padding:30px 40px 10px;">
              <h1 style="margin:0 0 14px;font-size:22px;font-weight:700;color:#eaf5f5;">Reset your password</h1>
              <p style="margin:0;color:#9db8c2;font-size:15px;line-height:1.7;">
                We received a request to reset the password for your BrandAura account.
                Click the button below to set a new password.
              </p>
            </td></tr>

            <tr><td style="padding:26px 40px;">
              <a href="LINK_PLACEHOLDER" target="_blank"
                 style="display:inline-block;background:linear-gradient(135deg,#00B894,#00a884);color:#fff;
                        text-decoration:none;font-weight:600;font-size:15px;
                        padding:14px 32px;border-radius:12px;
                        box-shadow:0 8px 24px rgba(0,184,148,0.3);
                        letter-spacing:0.02em;">
                Reset My Password
              </a>
            </td></tr>

            <tr><td style="padding:0 40px 12px;">
              <p style="margin:0;color:#6a8a99;font-size:13px;line-height:1.6;">
                If the button doesn't work, copy and paste this link into your browser:
              </p>
              <p style="margin:8px 0 0;color:#00B894;font-size:12px;word-break:break-all;">LINK_PLACEHOLDER</p>
            </td></tr>

            <tr><td style="padding:16px 40px;">
              <div style="width:100%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.08),transparent);"></div>
            </td></tr>

            <tr><td style="padding:14px 40px 30px;">
              <p style="margin:0;color:#556a75;font-size:12px;line-height:1.6;">
                This link expires in 30 minutes. If you didn't request this, you can safely ignore this email.
              </p>
              <p style="margin:12px 0 0;color:#3d5560;font-size:11px;">
                &copy; 2026 BrandAura. Your Brand's Future.
              </p>
            </td></tr>

          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """.replace("LINK_PLACEHOLDER", reset_link)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request, _: None = Depends(forgot_rate_limit)):
    """Always generic so accounts can't be probed."""
    email = str(body.email).strip().lower()
    resp = {"message": "If that email is registered, a reset link has been sent."}

    try:
        user = await mongodb.users.find_one({"email": email})
        if not user:
            return resp

        # Secure, URL-safe, unguessable token with a 15-minute expiry.
        token = secrets.token_urlsafe(32)
        await mongodb.password_resets.insert_one({
            "user_id": user["_id"],
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
                msg["Subject"] = "BrandAura — Reset your password"
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
async def reset_password(body: ResetPasswordRequest):
    # 1. Extract inputs
    token = (body.token or "").strip()
    new_password = body.new_password or ""

    # 2. Validate inputs
    if not token:
        raise HTTPException(status_code=400, detail="A reset token is required.")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    # 3. Validate the token
    try:
        doc = await mongodb.password_resets.find_one({"token_hash": _hash_token(token)})
        if not doc or doc.get("used"):
            raise HTTPException(status_code=400, detail="This reset link is invalid or has already been used.")

        expires_at = doc.get("expires_at")
        if expires_at is not None:
            now = utc_now()
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if expires_at < now:
                raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")

        # 4. Hash (passlib bcrypt) and persist — strict error handling
        pw_hash = pwd_context.hash(new_password)
        result = await mongodb.users.update_one(
            {"_id": doc["user_id"]},
            {"$set": {"password_hash": pw_hash}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=400, detail="This account no longer exists.")
        await mongodb.password_resets.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
    except HTTPException:
        raise
    except Exception as e:
        print(f"RESET ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="We couldn't update your password. Please try again later.")

    return {"message": "Password updated successfully. You can now log in with your new password."}