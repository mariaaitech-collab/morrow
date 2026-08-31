from pydantic import BaseModel, EmailStr, constr
from typing import Optional


class UserCreate(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=50)
    email: EmailStr
    # Enforce a sane, length-bounded password; never stored in plaintext.
    password: constr(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: constr(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: constr(strip_whitespace=True, min_length=1, max_length=512)
    new_password: constr(min_length=8, max_length=128)


class SocialAccount(BaseModel):
    platform: str
    account_name: str
    connected: bool
    auth_url: Optional[str] = None
