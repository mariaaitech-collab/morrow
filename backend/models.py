from pydantic import BaseModel, EmailStr, Field, constr
from typing import Literal, Optional


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


class UserProfileUpdate(BaseModel):
    business_name: constr(strip_whitespace=True, max_length=120) = ""
    business_type: constr(strip_whitespace=True, max_length=80) = ""
    industry: constr(strip_whitespace=True, max_length=80) = ""
    bio: constr(strip_whitespace=True, max_length=300) = ""
    website: constr(strip_whitespace=True, max_length=200) = ""
    location: constr(strip_whitespace=True, max_length=100) = ""


# ---------------------------------------------------------------------------
# Auto-Responder: reply rules (rule_matcher.py)
# ---------------------------------------------------------------------------
ResponderPlatform = Literal["facebook", "instagram", "linkedin", "tiktok"]
ReplyLanguage = Literal["any", "en", "ur", "ur-Arab"]
Keyword = constr(strip_whitespace=True, min_length=1, max_length=60)
Phrase = constr(strip_whitespace=True, min_length=1, max_length=300)


class RuleAnswer(BaseModel):
    text: constr(strip_whitespace=True, min_length=1, max_length=1000)
    lang: ReplyLanguage = "any"


class ReplyRule(BaseModel):
    id: constr(strip_whitespace=True, max_length=40) = ""
    name: constr(strip_whitespace=True, min_length=1, max_length=80)
    enabled: bool = True
    # One keyword hit of any length is enough (Greeting, Praise).
    single_keyword: bool = False
    keywords: list[Keyword] = Field(default_factory=list, max_length=80)
    phrases: list[Phrase] = Field(default_factory=list, max_length=80)
    answers: list[RuleAnswer] = Field(min_length=1, max_length=20)
    # Empty = every platform.
    platforms: list[ResponderPlatform] = Field(default_factory=list)
    source: Literal["", "default", "faq", "custom"] = ""
    # smart: keywords + trigger phrases, misspellings tolerated (rule_matcher).
    # exact / contains / starts_with: the comment equals / contains / starts with
    # one of the keywords or phrases (whole words, case and emoji ignored).
    match_type: Literal["smart", "exact", "contains", "starts_with"] = "smart"
    # When several rules match, the highest priority wins; then the most specific.
    priority: int = Field(0, ge=0, le=100)
    # Rule-level override: a comment this rule answers always waits for review.
    force_review: bool = False


class FallbackSettings(BaseModel):
    # On: unmatched comments get one of these replies. Off: they wait for you.
    enabled: bool = True
    answers: list[RuleAnswer] = Field(default_factory=list, max_length=20)


class AutoReplySettings(BaseModel):
    # Master switch. Nothing is ever posted automatically while this is off.
    enabled: bool = False
    reply_to_comments: bool = True
    reply_to_dms: bool = True
    # When true, EVERY reply waits in "Needs your attention" (no auto-posting).
    review_all: bool = False
    platforms: dict[ResponderPlatform, bool] = Field(
        default_factory=lambda: {"facebook": True, "instagram": True, "linkedin": True, "tiktok": True}
    )


class BrandPersonaUpdate(BaseModel):
    rules: list[ReplyRule] = Field(default_factory=list, max_length=100)
    fallback: FallbackSettings = Field(default_factory=FallbackSettings)
    # Any of these in a comment sends it to "Needs your attention", whatever matched.
    escalation_keywords: list[Keyword] = Field(default_factory=list, max_length=80)
    auto_reply: AutoReplySettings = Field(default_factory=AutoReplySettings)


class PersonaPreviewRequest(BaseModel):
    text: constr(strip_whitespace=True, min_length=1, max_length=2000)
    kind: Literal["comment", "dm"] = "comment"
    platform: ResponderPlatform = "instagram"
    author_name: constr(strip_whitespace=True, max_length=80) = "Customer"


class PersonaTestRequest(PersonaPreviewRequest):
    # Unsaved rules from the editor; the saved persona is used when omitted.
    persona: Optional[BrandPersonaUpdate] = None
    # Which connected channel to test against (its mode applies); "" = the
    # platform's first channel.
    channel_key: constr(strip_whitespace=True, max_length=200) = ""


# ---------------------------------------------------------------------------
# Auto-Responder: reply modes (responder_service.py)
# ---------------------------------------------------------------------------
ReplyMode = Literal["instant", "review"]
NoMatchAction = Literal["queue", "fallback", "ignore"]


class WorkspaceModeUpdate(BaseModel):
    # Only the fields sent are changed.
    mode: Optional[ReplyMode] = None
    no_match_action: Optional[NoMatchAction] = None
    paused: Optional[bool] = None


class ChannelModeUpdate(BaseModel):
    # "inherit" removes the channel's override (the workspace default applies).
    mode: Literal["inherit", "instant", "review"]


class AlwaysReviewUpdate(BaseModel):
    platform: ResponderPlatform
    author_id: constr(strip_whitespace=True, min_length=1, max_length=200)
    name: constr(strip_whitespace=True, max_length=120) = ""
    on: bool = True


class SimulateEventRequest(PersonaPreviewRequest):
    post_id: constr(strip_whitespace=True, max_length=200) = ""


class ApprovalDecision(BaseModel):
    # Optional edited text for "Accept"; required text for a manual reply.
    reply_text: Optional[constr(strip_whitespace=True, max_length=2000)] = None


class ReplyEditRequest(BaseModel):
    reply_text: constr(strip_whitespace=True, min_length=1, max_length=2000)
