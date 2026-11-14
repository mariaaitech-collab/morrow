"""Auto-Responder pipeline: ingest -> screen -> match a rule -> reply now, hold, or ignore.

Event lifecycle (responder_events.status):

    received ──► processing ──► auto_replied ──► (edit: new reply in place) ──► auto_replied
                     │                 └──────► (delete) ──► reply_deleted
                     │
                     ├────────► pending_approval ──► sending ──► approved_sent / manual_sent
                     │          ("Needs your attention")  └──► failed ──► (retry)
                     │                 └─► declined
                     │
                     ├────────► ignored                      (no rule matched, user chose "ignore")
                     ├────────► liked                        (emoji-only comment, Instant mode)
                     └────────► skipped / failed

Two reply modes (reply_mode_settings, see "Reply modes" below):
    instant  a comment a rule answers is posted at once, no human step
    review   every comment waits in "Needs your attention" with a suggested reply
The mode is resolved per comment: a rule marked "always review" (force_review)
-> the channel's setting -> the workspace default.

Routing, in order (evaluate(), then the safety limits in process_event()):
    emoji only                                   -> like it (Instant only) and stop
    offensive or sensitive word (local_screen)   -> hold
    a blocklist keyword (escalation_keywords)    -> hold
    an account on the always-review list         -> hold
    Review mode for this channel / workspace     -> hold
    "Pause all auto-replies" on (kill switch)    -> hold
    the matched rule is set to always review     -> hold
    no rule matched                              -> the no-match action: hold (default),
                                                    post the fallback reply, or ignore
    otherwise                                    -> post the matched rule's answer now
    ...but a 3rd+ reply to the same person within an hour, or the workspace's
    hourly cap (RESPONDER_HOURLY_REPLY_LIMIT), holds it instead.
Held comments keep their ready reply as the suggestion. The kill switch is read
again right before posting, so pausing also stops replies already in flight.
Each event records mode_used, mode_source, decision (auto_posted | queued |
declined | ignored) and decision_reason, shown in Activity.

No model is called anywhere here. Webhook handlers call `ingest_event()` +
`process_event()` from a background task, so the platform's HTTP request is
never delayed by the outgoing reply. Status transitions run in Firestore
transactions that check the current status, and each inbound message has a
fixed document id, so a double-click or a webhook retry can never post the
same reply twice.
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

import firebase_db
from firebase_db import FieldFilter
import rule_matcher
from ai_responder import local_screen
from config import RESPONDER_ALL_PLATFORMS, RESPONDER_HOURLY_REPLY_LIMIT, RESPONDER_PLATFORMS, utc_now
from emoji_utils import is_emoji_only
from platform_replies import (
    LikeUnsupported,
    ReplyError,
    change_support,
    delete_reply,
    replace_reply,
    send_like,
    send_reply,
)

SEND_RETRY_DELAYS = (0, 2, 6)  # seconds; transient platform errors are retried
AUTO_ACTOR = "Auto-responder"
POSTED = ("auto_replied", "approved_sent", "manual_sent")
MATCH_OUTCOMES = ("matched", "fallback", "no_match")
REPLY_LOCK_SECONDS = 120

# Keep references so background tasks are not garbage-collected mid-flight.
_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _http_error(status: int, detail: str):
    from fastapi import HTTPException

    return HTTPException(status_code=status, detail=detail)


def _ref(event_id: str):
    if not firebase_db.valid_id(event_id):
        raise _http_error(404, "Item not found.")
    return firebase_db.responder_events.document(event_id)


@firebase_db.async_transactional
async def _transition(transaction, ref, user_id: str | None, statuses, fields: dict):
    """Apply `fields` only if the event is in one of `statuses` (and owned by
    `user_id` when given). Returns (updated event or None, event as it was or None)."""
    snap = await ref.get(transaction=transaction)
    current = firebase_db.as_dict(snap)
    if current is None or (user_id is not None and current.get("user_id") != user_id):
        return None, None
    if current.get("status") not in statuses:
        return None, current
    transaction.update(ref, fields)
    return {**current, **fields}, current


# --------------------------------------------------------------------------
# Persona: rules, fallback, escalation keywords, switches
# --------------------------------------------------------------------------
PERSONA_FIELDS = ("rules", "fallback", "escalation_keywords", "auto_reply")


def _default_rules() -> list[dict]:
    return [{**r, "source": "default"} for r in rule_matcher.default_rules()]


def default_persona() -> dict:
    from models import BrandPersonaUpdate

    persona = BrandPersonaUpdate().model_dump()
    persona["rules"] = _default_rules()
    persona["fallback"] = rule_matcher.default_fallback()
    persona["escalation_keywords"] = rule_matcher.default_escalation_keywords()
    return persona


@firebase_db.async_transactional
async def _migrate(transaction, ref) -> tuple[dict, int | None]:
    """First load after the switch to rules: each FAQ becomes a rule (listed
    first, so it wins ties), followed by the default rules.

    The original `faqs` list is left in the document untouched, as a backup.
    Returns the persona and how many FAQs were migrated (None if another
    request had already done it).
    """
    doc = (await ref.get(transaction=transaction)).to_dict() or {}
    if "rules" in doc:
        return doc, None
    faqs = doc.get("faqs") or []
    now = utc_now()
    update = {
        "rules": rule_matcher.migrate_faqs(faqs) + _default_rules(),
        "fallback": rule_matcher.default_fallback(),
        "escalation_keywords": rule_matcher.default_escalation_keywords(),
        "rules_migrated_at": now,
        "updated_at": now,
    }
    transaction.update(ref, update)
    return {**doc, **update}, len(faqs)


def _persona_ref(user_id: str):
    return firebase_db.brand_personas.document(user_id)


async def get_persona(user_id: str, user: dict | None = None) -> dict:
    """The workspace's rules and settings (the defaults if it never saved any)."""
    doc = await firebase_db.get(_persona_ref(user_id))
    base = default_persona()
    if not doc:
        return base
    if "rules" not in doc:
        doc, migrated = await _migrate(firebase_db.db.transaction(), _persona_ref(user_id))
        if migrated is not None:
            print(f"[RESPONDER] persona {user_id}: {migrated} FAQ(s) migrated to rules")
    merged = {**base, **{k: doc[k] for k in PERSONA_FIELDS if doc.get(k) is not None}}
    merged["fallback"] = {**base["fallback"], **(doc.get("fallback") or {})}
    merged["auto_reply"] = {**base["auto_reply"], **(doc.get("auto_reply") or {})}
    merged["auto_reply"]["platforms"] = {
        **base["auto_reply"]["platforms"], **((doc.get("auto_reply") or {}).get("platforms") or {})
    }
    return merged


# --------------------------------------------------------------------------
# Reply modes: workspace default -> channel override -> rule override
# --------------------------------------------------------------------------
# reply_mode_settings rows (one per scope):
#   workspace  {user_id, scope: "workspace", scope_id: user_id, mode, no_match_action,
#               paused, always_review_accounts: [...], updated_at, updated_by}
#   channel    {user_id, scope: "channel", scope_id: "<platform>:<account id>", platform,
#               mode, no_match_action: None (= the workspace's), updated_at, updated_by}
# The rule-level override is the rule's own force_review flag (persona rules).
MODES = ("instant", "review")
NO_MATCH_ACTIONS = ("queue", "fallback", "ignore")
DEFAULT_NO_MATCH_ACTION = "queue"  # the safest: a generic reply is never posted unless chosen
PER_AUTHOR_HOURLY_LIMIT = 2        # a 3rd automatic reply to one person within an hour waits
MAX_ALWAYS_REVIEW_ACCOUNTS = 500
DECISIONS = {"auto_reply": "auto_posted", "review": "queued", "ignore": "ignored"}


def _workspace_settings_ref(user_id: str):
    return firebase_db.reply_mode_settings.document(f"{user_id}--workspace")


def _channel_settings_ref(user_id: str, channel_key: str):
    return firebase_db.reply_mode_settings.document(f"{user_id}--channel--{channel_key}")


def platform_enabled(platform: str | None) -> bool:
    """Whether the AI Responder handles this platform (RESPONDER_PLATFORMS)."""
    return platform in RESPONDER_PLATFORMS


def platform_off_reason(platform: str | None) -> str:
    name = PLATFORM_LABELS.get(platform or "", (platform or "this platform").title())
    return (f"Auto-replies are not available for {name} yet "
            f"(RESPONDER_PLATFORMS={','.join(RESPONDER_PLATFORMS) or 'none'})")


PLATFORM_LABELS = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "tiktok": "TikTok"}


def platform_config() -> dict:
    """What the AI Responder page needs to know: which platforms are on, which are coming."""
    return {
        "platforms": list(RESPONDER_PLATFORMS),
        "coming_soon": [p for p in RESPONDER_ALL_PLATFORMS if p not in RESPONDER_PLATFORMS],
    }


def list_channels(user_id: str, all_platforms: bool = False) -> list[dict]:
    """Every connected account a comment can arrive on, keyed the way events are.

    Key "<platform>:<id>" where id is what webhooks put in account_ref (Facebook
    Page id, Instagram business id, TikTok open_id). LinkedIn comments carry an
    organization id the connected account does not store, so LinkedIn is one
    platform-wide channel, "linkedin:*".

    Only platforms in RESPONDER_PLATFORMS are listed unless `all_platforms`.
    """
    from routers.social import get_user_accounts

    own = get_user_accounts(user_id)
    channels: list[dict] = []

    def add(platform: str, ref, name: str) -> None:
        key = f"{platform}:{ref}"
        if not any(c["key"] == key for c in channels):
            channels.append({"key": key, "platform": platform, "name": name,
                             "account_ref": None if ref == "*" else str(ref)})

    fb, ig = own.get("facebook") or {}, own.get("instagram") or {}
    for page in fb.get("pages") or []:
        if page.get("id"):
            add("facebook", page["id"], page.get("name") or "Facebook Page")
    ig_pages = [p for acct in (ig, fb) for p in acct.get("pages") or [] if p.get("instagram_business_id")]
    ig_ids = {str(p["instagram_business_id"]) for p in ig_pages}
    for page in ig_pages:
        name = (ig.get("account_name") if len(ig_ids) == 1 and ig.get("account_name")
                else f"Instagram ({page.get('name') or 'linked account'})")
        add("instagram", page["instagram_business_id"], name)
    for acct in (ig, fb):
        if acct.get("instagram_business_id"):
            add("instagram", acct["instagram_business_id"], ig.get("account_name") or "Instagram")
    tiktok = own.get("tiktok") or {}
    if tiktok.get("access_token"):
        add("tiktok", tiktok.get("open_id") or "*", tiktok.get("account_name") or "TikTok")
    linkedin = own.get("linkedin") or {}
    if linkedin.get("access_token"):
        add("linkedin", "*", linkedin.get("account_name") or "LinkedIn")
    return channels if all_platforms else [c for c in channels if platform_enabled(c["platform"])]


def channel_key_for(event: dict, settings: dict | None = None) -> str:
    """The channel an event arrived on: its exact account, else the platform-wide channel."""
    platform, ref = event.get("platform"), event.get("account_ref")
    exact, wildcard = (f"{platform}:{ref}" if ref else ""), f"{platform}:*"
    if settings is not None:
        if exact and exact in settings["channels"]:
            return exact
        if wildcard in settings["channels"]:
            return wildcard
    return exact or wildcard


def _workspace_defaults(doc: dict) -> dict:
    return {
        **doc,
        "mode": doc.get("mode") if doc.get("mode") in MODES else "instant",
        "no_match_action": doc.get("no_match_action") if doc.get("no_match_action") in NO_MATCH_ACTIONS
        else DEFAULT_NO_MATCH_ACTION,
        "paused": bool(doc.get("paused")),
        "always_review_accounts": doc.get("always_review_accounts") or [],
    }


async def _create_workspace_settings(user_id: str, persona: dict | None) -> dict:
    """First use: the mode comes from the old "Review every reply" switch; the
    no-match action starts at the safest choice (the review queue)."""
    persona = persona or await get_persona(user_id)
    now = utc_now()
    doc = {
        "user_id": user_id, "scope": "workspace", "scope_id": user_id,
        "mode": "review" if (persona.get("auto_reply") or {}).get("review_all") else "instant",
        "no_match_action": DEFAULT_NO_MATCH_ACTION, "paused": False, "always_review_accounts": [],
        "updated_at": now, "updated_by": "Set up from your previous settings",
    }
    ref = _workspace_settings_ref(user_id)
    try:
        await ref.create(doc)
        return {"id": ref.id, **doc}
    except firebase_db.AlreadyExists:
        return await firebase_db.get(ref) or {"id": ref.id, **doc}


async def get_mode_settings(user_id: str, persona: dict | None = None) -> dict:
    """{"workspace": {...}, "channels": {channel_key: row}} (the workspace row is created on first use)."""
    rows = await firebase_db.fetch(
        firebase_db.reply_mode_settings.where(filter=FieldFilter("user_id", "==", user_id))
    )
    workspace = next((r for r in rows if r.get("scope") == "workspace"), None)
    if workspace is None:
        workspace = await _create_workspace_settings(user_id, persona)
    channels = {r["scope_id"]: r for r in rows if r.get("scope") == "channel" and r.get("scope_id")}
    return {"workspace": _workspace_defaults(workspace), "channels": channels}


def resolve_mode(settings: dict, event: dict) -> tuple[str, str, str]:
    """(mode, where it came from: "channel" | "workspace", channel key) for one event."""
    key = channel_key_for(event, settings)
    row = settings["channels"].get(key) or {}
    if row.get("mode") in MODES:
        return row["mode"], "channel", key
    return settings["workspace"]["mode"], "workspace", key


def always_review_name(workspace: dict, event: dict) -> str:
    """The author's name if they are on the always-review list, else ""."""
    author = event.get("author") or {}
    author_id = str(author.get("id") or "")
    if not author_id:
        return ""
    for entry in workspace.get("always_review_accounts") or []:
        if entry.get("platform") == event.get("platform") and str(entry.get("author_id")) == author_id:
            return entry.get("name") or author.get("name") or "This account"
    return ""


def mode_context(settings: dict, event: dict) -> dict:
    """Everything evaluate() needs to know about modes for one event."""
    mode, source, key = resolve_mode(settings, event)
    workspace = settings["workspace"]
    return {
        "mode": mode, "mode_source": source, "channel_key": key,
        "no_match_action": workspace["no_match_action"],
        "paused": workspace["paused"],
        "always_review_author": always_review_name(workspace, event),
    }


async def update_workspace_settings(user_id: str, fields: dict, actor: str) -> None:
    allowed = {k: v for k, v in fields.items() if k in ("mode", "no_match_action", "paused")}
    if not allowed:
        return
    await get_mode_settings(user_id)  # make sure the row exists
    await _workspace_settings_ref(user_id).update({**allowed, "updated_at": utc_now(), "updated_by": actor})
    print(f"[RESPONDER] {user_id}: workspace reply settings {allowed} by {actor}")


async def set_channel_mode(user_id: str, channel_key: str, mode: str, actor: str) -> None:
    """mode "inherit" removes the override, so the workspace default applies."""
    ref = _channel_settings_ref(user_id, channel_key)
    if mode == "inherit":
        await ref.delete()
    else:
        await ref.set({
            "user_id": user_id, "scope": "channel", "scope_id": channel_key,
            "platform": channel_key.split(":", 1)[0], "mode": mode, "no_match_action": None,
            "updated_at": utc_now(), "updated_by": actor,
        })
    print(f"[RESPONDER] {user_id}: channel {channel_key} mode -> {mode} by {actor}")


@firebase_db.async_transactional
async def _write_always_review(transaction, ref, platform: str, author_id: str, name: str, on: bool,
                               actor: str, now) -> list[dict]:
    doc = firebase_db.as_dict(await ref.get(transaction=transaction)) or {}
    accounts = [a for a in doc.get("always_review_accounts") or []
                if not (a.get("platform") == platform and str(a.get("author_id")) == author_id)]
    if on:
        if len(accounts) >= MAX_ALWAYS_REVIEW_ACCOUNTS:
            raise _http_error(400, f"The always-review list is full ({MAX_ALWAYS_REVIEW_ACCOUNTS} accounts).")
        accounts.append({"platform": platform, "author_id": author_id, "name": name, "added_at": now, "added_by": actor})
    transaction.update(ref, {"always_review_accounts": accounts, "updated_at": now, "updated_by": actor})
    return accounts


async def set_always_review(user_id: str, platform: str, author_id: str, name: str, on: bool, actor: str) -> list[dict]:
    await get_mode_settings(user_id)  # make sure the row exists
    return await _write_always_review(firebase_db.db.transaction(), _workspace_settings_ref(user_id),
                                      platform, str(author_id), name, on, actor, utc_now())


async def _paused_now(user_id: str) -> bool:
    doc = await firebase_db.get(_workspace_settings_ref(user_id))
    return bool(doc and doc.get("paused"))


def serialize_workspace(workspace: dict) -> dict:
    return {
        "mode": workspace["mode"],
        "no_match_action": workspace["no_match_action"],
        "paused": workspace["paused"],
        "always_review_accounts": [{**a, "added_at": _iso(a.get("added_at"))} for a in workspace["always_review_accounts"]],
        "updated_at": _iso(workspace.get("updated_at")),
        "updated_by": workspace.get("updated_by", ""),
    }


# --------------------------------------------------------------------------
# The decision (pure, instant; also drives the test box)
# --------------------------------------------------------------------------
def _default_context(persona: dict) -> dict:
    review_all = bool((persona.get("auto_reply") or {}).get("review_all"))
    return {"mode": "review" if review_all else "instant", "mode_source": "workspace", "channel_key": "",
            "no_match_action": DEFAULT_NO_MATCH_ACTION, "paused": False, "always_review_author": ""}


def evaluate(persona: dict, text: str, platform: str | None = None, rng=None, ctx: dict | None = None) -> dict:
    """What should happen to one comment: "auto_reply", "review" or "ignore", and why.

    `ctx` is mode_context() for the event; without it the persona's old
    "Review every reply" switch decides the mode (no channel overrides).
    """
    ctx = {**_default_context(persona), **(ctx or {})}
    screen = local_screen(text)
    blocked = rule_matcher.find_keywords(persona.get("escalation_keywords") or [], text)
    rules = persona.get("rules") or []
    # The fallback is always drafted (it is the suggestion for a held comment);
    # whether it may be POSTED is the no-match action's decision, below.
    fallback = {**(persona.get("fallback") or {}), "enabled": True}
    result = rule_matcher.respond(rules, fallback, text, platform, rng=rng)
    rule = next((r for r in rules if r.get("id") == result["rule_id"]), None) if result["outcome"] == "matched" else None
    where = "for this channel" if ctx["mode_source"] == "channel" else "(workspace default)"

    # The user's own blocklist is named before the built-in sensitive-word
    # screen (both hold the comment), since it is the more specific reason.
    if screen["flagged"]:
        action, reason = "review", "Offensive or inappropriate message"
    elif blocked:
        action, reason = "review", f"Blocklist keyword: {', '.join(blocked)}"
    elif screen["sensitive"]:
        action, reason = "review", f"Sensitive topic: {', '.join(screen['sensitive_terms'])}"
    elif ctx["always_review_author"]:
        action, reason = "review", f"{ctx['always_review_author']} is on your always-review list"
    elif ctx["mode"] == "review":
        action, reason = "review", f"Review mode is on {where}"
    elif ctx["paused"]:
        action, reason = "review", "Auto-replies are paused"
    elif rule and rule.get("force_review"):
        action, reason = "review", f"Rule “{result['rule_name']}” is set to always review"
    elif rule is None:
        choice = ctx["no_match_action"]
        if choice == "fallback" and result["reply"]:
            action, reason = "auto_reply", "No rule matched: posted your fallback reply (your no-match setting)"
        elif choice == "fallback":
            action, reason = "review", "No rule matched, and no fallback reply is written"
        elif choice == "ignore":
            action, reason = "ignore", "No rule matched: ignored (your no-match setting)"
        else:
            action, reason = "review", "No rule matched"
    else:
        action, reason = "auto_reply", f"Matched rule “{result['rule_name']}”"
    return {
        "action": action, "reason": reason, "decision": DECISIONS[action],
        "screen": screen, "escalated": blocked,
        "mode": ctx["mode"], "mode_source": ctx["mode_source"], "channel_key": ctx["channel_key"],
        "no_match_action": ctx["no_match_action"], "paused": ctx["paused"],
        "force_review": bool(rule and rule.get("force_review")),
        **result,
    }


def _analysis(verdict: dict) -> dict:
    """What is stored on the event about the decision."""
    return {
        "local_screen": verdict["screen"],
        "escalation_terms": verdict["escalated"],
        "match": {k: verdict[k] for k in ("outcome", "rule_id", "rule_name", "score", "method",
                                          "keywords", "fuzzy_keywords", "phrase", "lang")},
        "scored": [{k: s[k] for k in ("rule_id", "rule_name", "score", "passed", "keywords")}
                   for s in verdict["scored"][:3]],
    }


# --------------------------------------------------------------------------
# Serialization helpers
# --------------------------------------------------------------------------
def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _decision(doc: dict) -> str | None:
    """auto_posted | queued | declined | ignored. Events from before reply modes
    have no `decision` field, so it is read from their status."""
    if doc.get("decision"):
        return doc["decision"]
    status = doc.get("status")
    if status in ("auto_replied", "reply_deleted"):
        return "auto_posted"
    if status in ("pending_approval", "failed", "sending", "approved_sent", "manual_sent"):
        return "queued"
    if status == "declined":
        return "declined"
    if status in ("skipped", "liked", "ignored"):
        return "ignored"
    return None


def serialize_event(doc: dict) -> dict:
    analysis = doc.get("analysis") or {}
    screen = analysis.get("local_screen") or {}
    match = analysis.get("match") or {}
    status = doc.get("status")
    blocked = ""
    if status in POSTED:
        blocked = change_support(doc) or (
            "" if doc.get("simulated") or (doc.get("reply_result") or {}).get("reply_id")
            else "The id of the posted reply was not recorded, so it can't be changed on the platform."
        )
    return {
        "id": doc["id"],
        "platform": doc.get("platform"),
        "kind": doc.get("kind"),
        "text": doc.get("text", ""),
        "author": doc.get("author") or {},
        "post_id": doc.get("post_id"),
        "status": status,
        "decision_reason": doc.get("decision_reason", ""),
        "analysis": {
            "is_offensive": bool(screen.get("flagged") or analysis.get("is_offensive")),
            "is_sensitive": bool(screen.get("sensitive") or analysis.get("is_sensitive")),
            "flagged_terms": screen.get("offensive_terms") or [],
            "sensitive_terms": screen.get("sensitive_terms") or [],
            "escalation_terms": analysis.get("escalation_terms") or [],
            "outcome": match.get("outcome") or doc.get("match_outcome"),
            "rule_name": match.get("rule_name", ""),
            "method": match.get("method", ""),
            "keywords": match.get("keywords") or [],
        },
        "rule_id": doc.get("rule_id"),
        "rule_score": doc.get("rule_score"),
        "match_outcome": doc.get("match_outcome"),
        "mode_used": doc.get("mode_used"),
        "mode_source": doc.get("mode_source"),
        "channel_key": doc.get("channel_key"),
        "decision": _decision(doc),
        "routing": doc.get("routing") or None,
        "text_missing": bool(doc.get("text_missing")),
        "suggested_reply": doc.get("suggested_reply", ""),
        "final_reply": doc.get("final_reply", ""),
        "error": doc.get("error", ""),
        "simulated": bool(doc.get("simulated")),
        "can_change": status in POSTED and not blocked,
        "change_blocked": blocked,
        "reply_history": [{**h, "at": _iso(h.get("at"))} for h in doc.get("reply_history") or []],
        "received_at": _iso(doc.get("received_at")),
        "platform_timestamp": _iso(doc.get("platform_timestamp")),
        "decided_at": _iso(doc.get("decided_at")),
        "replied_at": _iso(doc.get("replied_at")),
    }


# --------------------------------------------------------------------------
# Gaps: comments no rule answered (Persona page)
# --------------------------------------------------------------------------
GAP_SIMILARITY = 0.5  # word overlap (Jaccard) at which two comments count as similar
GAP_SCAN_LIMIT = 2000
GAP_LIST_LIMIT = 50


def _similar(a: set[str], b: set[str]) -> bool:
    return bool(a and b) and len(a & b) / len(a | b) >= GAP_SIMILARITY


async def rule_gaps(user_id: str, persona: dict, days: int = 30) -> dict:
    """Rule coverage and the unmatched comments of the last `days`, similar ones grouped.

    Fallback replies count as unmatched. Simulations and events that never
    reached the matcher (emoji-only, skipped) are left out.
    """
    since = utc_now() - timedelta(days=days)
    query = (
        firebase_db.responder_events
        .where(filter=FieldFilter("user_id", "==", user_id))
        .where(filter=FieldFilter("simulated", "==", False))
        .where(filter=FieldFilter("match_outcome", "in", list(MATCH_OUTCOMES)))
        .where(filter=FieldFilter("received_at", ">=", since))
        .order_by("received_at", direction=firebase_db.DESCENDING)
        .limit(GAP_SCAN_LIMIT)
        .select(["text", "platform", "match_outcome", "status", "received_at"])
    )

    analyzed = matched = 0
    groups: list[dict] = []
    for doc in await firebase_db.fetch(query):
        analyzed += 1
        if doc.get("match_outcome") == "matched":
            matched += 1
            continue
        text = doc.get("text", "")
        norm, words = rule_matcher.normalize(text), rule_matcher.content_words(text)
        group = next((g for g in groups if g["norm"] == norm or _similar(words, g["words"])), None)
        if group is None:
            # Newest first, so a group shows its most recent wording.
            group = {"text": text, "norm": norm, "words": words, "count": 0, "fallback": 0,
                     "last_seen": doc.get("received_at"), "platform": doc.get("platform"),
                     "platforms": set(), "event_ids": []}
            groups.append(group)
        group["count"] += 1
        # Only a fallback that was actually posted; a held comment merely had it as a suggestion.
        group["fallback"] += doc.get("match_outcome") == "fallback" and doc.get("status") in POSTED + ("reply_deleted",)
        group["platforms"].add(doc.get("platform"))
        if len(group["event_ids"]) < 20:
            group["event_ids"].append(doc["id"])

    # A comment a rule now answers (a phrase or keyword was added since) drops off.
    rules = persona.get("rules") or []
    gaps = [g for g in groups if not rule_matcher.match(rules, g["text"], g["platform"])["best"]]
    gaps.sort(key=lambda g: -g["count"])  # stable: ties stay newest first

    return {
        "days": days,
        "coverage": {
            "analyzed": analyzed,
            "matched": matched,
            "percent": round(100 * matched / analyzed) if analyzed else None,
        },
        "gaps": [{
            "text": g["text"],
            "count": g["count"],
            "answered_by_fallback": g["fallback"],
            "last_seen": _iso(g["last_seen"]),
            "platforms": sorted(p for p in g["platforms"] if p),
            "event_ids": g["event_ids"],
        } for g in gaps[:GAP_LIST_LIMIT]],
    }


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
async def notify(user_id: str, type_: str, title: str, body: str, event_id: Any = None) -> None:
    now = utc_now()
    try:
        await firebase_db.notifications.add({
            "user_id": user_id,
            "type": type_,
            "title": title[:140],
            "body": body[:400],
            "event_id": str(event_id) if event_id else None,
            "read": False,
            "created_at": now,
            "expires_at": now + firebase_db.NOTIFICATION_TTL,
        })
    except Exception as e:
        print(f"[RESPONDER] notification insert failed: {e}")


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
async def ingest_event(user_id: str, event: dict) -> str | None:
    """Insert a normalized inbound event. Returns its id, or None if a duplicate.

    `event` keys: platform, kind ("comment"|"dm"), external_id, text, author
    {id, name}, post_id, account_ref, reply_target {...}, platform_timestamp,
    simulated (bool), raw (trimmed original payload).
    """
    now = utc_now()
    doc = {
        "user_id": user_id,
        "platform": event["platform"],
        "kind": event["kind"],
        "external_id": str(event["external_id"]),
        "text": (event.get("text") or "")[:4000],
        "author": event.get("author") or {},
        "post_id": event.get("post_id"),
        "account_ref": event.get("account_ref"),
        "reply_target": event.get("reply_target") or {},
        "platform_timestamp": event.get("platform_timestamp"),
        # How the webhook matched it to this workspace (LinkedIn), and whether
        # the comment text could be read; both can force review (process_event).
        "routing": {k: v for k, v in (event.get("routing") or {}).items() if k != "user_id"} or None,
        "text_missing": bool(event.get("text_missing")),
        "text_missing_reason": event.get("text_missing_reason") or "",
        "simulated": bool(event.get("simulated")),
        # Kept as JSON text: a raw payload may hold arrays inside arrays, which Firestore can't store.
        "raw": json.dumps(event["raw"], default=str)[:8000] if event.get("raw") is not None else None,
        # Set by the matcher; stay null for events it never sees (emoji-only, skipped).
        "rule_id": None,
        "rule_score": None,
        "match_outcome": None,
        "status": "received",
        "received_at": now,
        "created_at": now,
        "updated_at": now,
    }
    # The id is derived from (workspace, platform, message id): a retried
    # delivery of the same message hits the existing document.
    ref = firebase_db.responder_events.document(
        firebase_db.event_doc_id(user_id, doc["platform"], doc["external_id"])
    )
    try:
        await ref.create(doc)
        return ref.id
    except firebase_db.AlreadyExists:
        print(f"[RESPONDER] duplicate {event['platform']} event {event['external_id']} ignored")
        return None


async def _get_event(event_id: str) -> dict | None:
    return await firebase_db.get(firebase_db.responder_events.document(event_id))


async def _set(event_id: str, **fields) -> None:
    fields["updated_at"] = utc_now()
    await firebase_db.responder_events.document(event_id).update(fields)


async def _record(event_id: str, entry: dict) -> None:
    """Append to the event's reply history (what was posted, changed or removed, by whom)."""
    await firebase_db.responder_events.document(event_id).update(
        {"reply_history": firebase_db.ArrayUnion([{**entry, "at": entry.get("at") or utc_now()}])}
    )


# --------------------------------------------------------------------------
# Processing
# --------------------------------------------------------------------------
async def _owner(user_id: str) -> dict | None:
    try:
        return await firebase_db.get_by_id(firebase_db.users, user_id)
    except Exception:
        return None


async def _skip_reason(user: dict | None, persona: dict, event: dict) -> str:
    from deps import apply_dev_override, compute_subscription

    if not user:
        return "The Morrow account no longer exists"
    user = await apply_dev_override(dict(user))
    if not compute_subscription(user).get("access_active"):
        return "Subscription inactive: auto-replies are paused"
    settings = persona.get("auto_reply") or {}
    if event.get("simulated"):
        return ""  # simulations always run so the rules can be tested
    if not settings.get("enabled"):
        return "Auto-responder is turned off"
    if not (settings.get("platforms") or {}).get(event["platform"], True):
        return f"Auto-responder is turned off for {event['platform']}"
    if event["kind"] == "comment" and not settings.get("reply_to_comments", True):
        return "Comment replies are turned off"
    if event["kind"] == "dm" and not settings.get("reply_to_dms", True):
        return "DM replies are turned off"
    return ""


async def _replies_last_hour(user_id: str) -> int:
    since = utc_now() - timedelta(hours=1)
    return await firebase_db.count(
        firebase_db.responder_events
        .where(filter=FieldFilter("user_id", "==", user_id))
        .where(filter=FieldFilter("simulated", "==", False))
        .where(filter=FieldFilter("status", "==", "auto_replied"))
        .where(filter=FieldFilter("replied_at", ">=", since))
    )


async def _replies_to_author_last_hour(event: dict) -> int:
    """Replies already posted to this event's author on this platform in the last hour.

    Equality filters only (user + author id), so no composite index is needed;
    the rest is filtered here. Simulations only count simulations.
    """
    author_id = (event.get("author") or {}).get("id")
    if not author_id:
        return 0
    since = utc_now() - timedelta(hours=1)
    docs = await firebase_db.fetch(
        firebase_db.responder_events
        .where(filter=FieldFilter("user_id", "==", event["user_id"]))
        .where(filter=FieldFilter("author.id", "==", author_id))
        .select(["status", "replied_at", "platform", "simulated"])
        .limit(500)
    )
    return sum(
        1 for d in docs
        if d["id"] != event.get("id") and d.get("platform") == event.get("platform")
        and bool(d.get("simulated")) == bool(event.get("simulated"))
        and d.get("status") in POSTED and d.get("replied_at") and d["replied_at"] >= since
    )


async def _safety_hold(event: dict) -> str:
    """Why an automatic reply must wait for review instead (rate limits), or ""."""
    try:
        sent = await _replies_to_author_last_hour(event)
    except Exception as e:
        print(f"[RESPONDER] recent-reply check failed for {event.get('id')}: {e}")
        return "Could not check recent replies to this person, so it waits for you"
    if sent >= PER_AUTHOR_HOURLY_LIMIT:
        who = (event.get("author") or {}).get("name") or "the same person"
        return f"This would be reply #{sent + 1} to {who} within an hour"
    if not event.get("simulated") and await _replies_last_hour(event["user_id"]) >= RESPONDER_HOURLY_REPLY_LIMIT:
        return f"Hourly reply limit ({RESPONDER_HOURLY_REPLY_LIMIT}) reached"
    return ""


async def _hold(event: dict, why: str, flagged: bool = False) -> None:
    """Put the event in "Needs your attention" and tell the user."""
    await _set(event["id"], status="pending_approval", decision="queued", decision_reason=why)
    label = "Offensive comment flagged" if flagged else "Needs your attention"
    who = (event.get("author") or {}).get("name") or "Someone"
    await notify(
        event["user_id"], "approval_required", f"{label} on {event['platform'].title()}",
        f"{who}: \"{(event.get('text') or '')[:120]}\". {why}.", event["id"],
    )


async def process_event(event_id: str) -> None:
    """Decide one event: post a reply now, hold it in "Needs your attention", or ignore it."""
    event, _ = await _transition(
        firebase_db.db.transaction(), firebase_db.responder_events.document(event_id), None,
        ("received",), {"status": "processing", "updated_at": utc_now()},
    )
    if not event:
        return  # already handled by another worker / retry
    user_id = event["user_id"]
    if not platform_enabled(event.get("platform")):
        # Normally stopped before it is stored; this covers anything stored earlier.
        await _set(event_id, status="skipped", decision="ignored", decision_reason=platform_off_reason(event.get("platform")))
        return
    try:
        user = await _owner(user_id)
        persona = await get_persona(user_id, user)

        reason = await _skip_reason(user, persona, event)
        if reason:
            await _set(event_id, status="skipped", decision="ignored", decision_reason=reason)
            return

        settings = await get_mode_settings(user_id, persona)
        ctx = mode_context(settings, event)
        mode_fields = {"mode_used": ctx["mode"], "mode_source": ctx["mode_source"], "channel_key": ctx["channel_key"]}

        # A comment that could not be tied to a connected channel, or whose text
        # could not be read, is never answered automatically, and never dropped:
        # it waits in "Needs your attention" with the reason.
        routing = event.get("routing") or {}
        holds = []
        if routing.get("channel_matched") is False:
            holds.append(f"Channel not matched: {routing.get('note') or 'the account this arrived on is not connected'}")
        if event.get("text_missing"):
            why_missing = event.get("text_missing_reason") or "the notification did not include it"
            holds.append(f"Comment text unavailable ({why_missing})")
        if holds:
            fields = {"decision": "queued", **mode_fields}
            if not event.get("text_missing"):
                verdict = evaluate(persona, event.get("text", ""), event["platform"], ctx=ctx)
                fields.update(analysis=_analysis(verdict), suggested_reply=verdict["reply"], rule_id=verdict["rule_id"],
                              rule_score=verdict["score"], match_outcome=verdict["outcome"], reply_lang=verdict["lang"])
            await _set(event_id, **fields)
            await _hold({**event, "id": event_id}, ". ".join(holds))
            return

        # Emoji-only: no text to answer. Like it, but only when replies may go out on their own.
        if is_emoji_only(event.get("text")):
            hold = ("review mode is on" if ctx["mode"] == "review"
                    else "auto-replies are paused" if ctx["paused"]
                    else "this account is on your always-review list" if ctx["always_review_author"] else "")
            if hold:
                await _set(event_id, status="skipped", decision="ignored",
                           decision_reason=f"Emoji-only comment: not liked because {hold}", **mode_fields)
            else:
                await _set(event_id, decision="ignored", **mode_fields)
                await _react_only(event)
            return

        verdict = evaluate(persona, event.get("text", ""), event["platform"], ctx=ctx)
        action, why = verdict["action"], verdict["reason"]
        if action == "auto_reply":
            limit_reason = await _safety_hold({**event, "id": event_id})
            if limit_reason:
                action, why = "review", limit_reason
        await _set(
            event_id,
            analysis=_analysis(verdict),
            suggested_reply=verdict["reply"],
            decision_reason=why,
            decision=DECISIONS[action],
            rule_id=verdict["rule_id"],
            rule_score=verdict["score"],
            match_outcome=verdict["outcome"],
            reply_lang=verdict["lang"],
            **mode_fields,
        )

        if action == "ignore":
            await _set(event_id, status="ignored")
            return
        if action == "review":
            await _hold({**event, "id": event_id}, why, flagged=verdict["screen"]["flagged"])
            return

        # Kill switch: read again right before posting, so pausing stops replies in flight.
        if await _paused_now(user_id):
            await _hold({**event, "id": event_id}, "Auto-replies were paused before this reply was posted")
            return
        doc = await _deliver(event, verdict["reply"], success_status="auto_replied", user=user)
        if (doc or {}).get("status") == "failed":
            await _set(event_id, decision="queued")  # a failed auto-reply waits in the queue to be retried
    except Exception as e:
        print(f"[RESPONDER] processing failed for {event_id}: {e}")
        await _set(event_id, status="failed", decision="queued", error=f"Processing error: {str(e)[:300]}")
        await notify(user_id, "reply_failed", "Auto-reply failed", str(e)[:300], event_id)


async def _react_only(event: dict) -> None:
    """Like an emoji-only comment. Never falls back to a text reply, even on failure."""
    event_id = event["id"]
    if event.get("simulated"):
        await _set(event_id, status="liked", decision_reason="Emoji-only comment: liked (simulated)",
                   replied_at=utc_now(), error="")
        return
    if event["kind"] != "comment":
        await _set(event_id, status="skipped",
                   decision_reason="Emoji-only message: nothing to like in a DM, no text reply sent")
        return

    last_error = ""
    for delay in SEND_RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            await send_like(event["user_id"], event)
            await _set(event_id, status="liked", decision_reason="Emoji-only comment: liked, no text reply",
                       replied_at=utc_now(), error="")
            return
        except LikeUnsupported as e:
            await _set(event_id, status="skipped", decision_reason=f"Emoji-only comment: {e} No text reply sent")
            return
        except ReplyError as e:
            last_error = str(e)
            break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
    # "skipped" (not "failed") so the queue never offers a text reply for it.
    await _set(event_id, status="skipped", decision_reason="Emoji-only comment: the like could not be sent",
               error=last_error[:500])


async def _deliver(event: dict, text: str, success_status: str, user: dict | None = None,
                   actor: str = AUTO_ACTOR) -> dict:
    """Post `text` as the reply. Updates the event; returns the updated document."""
    event_id = event["id"]
    user_id = event["user_id"]
    if event.get("simulated"):
        # Simulated events never touch a real platform.
        await _set(event_id, status=success_status, final_reply=text, replied_at=utc_now(),
                   reply_result={"simulated": True}, error="")
        await _record(event_id, {"action": "posted", "text": text, "reply_id": "", "by": actor})
        return await _get_event(event_id)

    last_error = ""
    for delay in SEND_RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            result = await send_reply(user_id, event, text)
            await _set(event_id, status=success_status, final_reply=text, replied_at=utc_now(),
                       reply_result={"reply_id": result.get("reply_id", "")}, error="")
            await _record(event_id, {"action": "posted", "text": text, "reply_id": result.get("reply_id", ""), "by": actor})
            try:
                from usage import record_usage
                owner = user or await _owner(user_id)
                await record_usage(owner, "auto_reply", f"Replied on {event['platform'].title()}", text[:200])
            except Exception:
                pass
            return await _get_event(event_id)
        except ReplyError as e:
            last_error = str(e)
            break  # permanent (permissions, missing ids): do not retry
        except Exception as e:  # network / 5xx: retry
            last_error = f"{type(e).__name__}: {e}"

    await _set(event_id, status="failed", final_reply=text, error=last_error[:500])
    await notify(user_id, "reply_failed", f"Reply failed on {event['platform'].title()}", last_error[:300], event_id)
    return await _get_event(event_id)


async def handle_new_event(user_id: str, event: dict) -> str | None:
    """Ingest + process (used by webhooks and the simulator).

    A platform outside RESPONDER_PLATFORMS is never stored, queued or answered.
    Webhooks check this first and log it; this is the last line of defence.
    """
    if not platform_enabled(event.get("platform")):
        print(f"[RESPONDER] ignored {event.get('platform')} event {event.get('external_id')}: "
              f"{platform_off_reason(event.get('platform'))}")
        return None
    event_id = await ingest_event(user_id, event)
    if event_id is not None:
        await process_event(event_id)
    return event_id


# --------------------------------------------------------------------------
# Human decisions ("Needs your attention")
# --------------------------------------------------------------------------
ACTIONABLE = ("pending_approval", "failed")


async def _claim(user_id: str, event_id: str, statuses=ACTIONABLE) -> dict:
    doc, current = await _transition(
        firebase_db.db.transaction(), _ref(event_id), user_id, statuses,
        {"status": "sending", "decided_at": utc_now(), "updated_at": utc_now()},
    )
    if not doc:
        if not current:
            raise _http_error(404, "Item not found.")
        raise _http_error(409, f"This item was already handled ({current.get('status')}).")
    return doc


async def accept(user_id: str, event_id: str, edited_text: str | None = None, actor: str = "") -> dict:
    doc = await _claim(user_id, event_id)
    text = (edited_text or doc.get("suggested_reply") or "").strip()
    if not text:
        await _set(doc["id"], status="pending_approval")
        raise _http_error(400, "There is no reply text to post.")
    status = "approved_sent" if text == (doc.get("suggested_reply") or "").strip() else "manual_sent"
    return await _deliver(doc, text, success_status=status, actor=actor or "You")


async def send_manual(user_id: str, event_id: str, text: str, actor: str = "") -> dict:
    if not (text or "").strip():
        raise _http_error(400, "Write a reply first.")
    # A declined suggestion can still be answered with the user's own words.
    doc = await _claim(user_id, event_id, statuses=ACTIONABLE + ("declined",))
    return await _deliver(doc, text.strip(), success_status="manual_sent", actor=actor or "You")


async def decline(user_id: str, event_id: str) -> dict:
    doc, _ = await _transition(
        firebase_db.db.transaction(), _ref(event_id), user_id, ACTIONABLE,
        {"status": "declined", "decision": "declined", "decided_at": utc_now(), "updated_at": utc_now()},
    )
    if not doc:
        raise _http_error(409, "This item was already handled or does not exist.")
    return doc


# --------------------------------------------------------------------------
# Changing a reply after it was posted (Activity tab)
# --------------------------------------------------------------------------
@firebase_db.async_transactional
async def _take_lock(transaction, ref, user_id: str, now):
    """Returns (locked event or None, event as it was or None)."""
    current = firebase_db.as_dict(await ref.get(transaction=transaction))
    if current is None or current.get("user_id") != user_id:
        return None, None
    lock = current.get("reply_lock")
    stale = lock is None or lock < now - timedelta(seconds=REPLY_LOCK_SECONDS)
    if current.get("status") not in POSTED or not stale:
        return None, current
    transaction.update(ref, {"reply_lock": now})
    return {**current, "reply_lock": now}, current


async def _lock_posted(user_id: str, event_id: str) -> dict:
    """Claim a posted reply for one change at a time; a stale claim expires."""
    doc, current = await _take_lock(firebase_db.db.transaction(), _ref(event_id), user_id, utc_now())
    if doc:
        return doc
    if not current:
        raise _http_error(404, "Item not found.")
    if current.get("status") not in POSTED:
        raise _http_error(409, "There is no posted reply on this item to change.")
    raise _http_error(409, "This reply is already being changed. Try again in a moment.")


async def _unlock(event_id: str) -> None:
    await firebase_db.responder_events.document(event_id).update({"reply_lock": firebase_db.DELETE_FIELD})


async def edit_reply(user_id: str, event_id: str, text: str, actor: str) -> dict:
    """Replace a posted reply with `text`. On a platform error nothing is changed."""
    text = (text or "").strip()
    if not text:
        raise _http_error(400, "Write the new reply first.")
    doc = await _lock_posted(user_id, event_id)
    try:
        old_text = doc.get("final_reply") or ""
        if text == old_text.strip():
            raise _http_error(400, "The reply is unchanged.")
        old_id = (doc.get("reply_result") or {}).get("reply_id", "")
        if doc.get("simulated"):
            new_id, warning, mode, result = "", "", "simulated", {"simulated": True}
        else:
            blocked = change_support(doc)
            if blocked:
                raise _http_error(400, blocked)
            try:
                outcome = await replace_reply(user_id, doc, old_id, text)
            except ReplyError as e:
                raise _http_error(502, str(e))
            except Exception as e:
                raise _http_error(502, f"Could not reach {doc['platform'].title()} ({type(e).__name__}). Nothing was changed.")
            new_id, warning, mode = outcome["reply_id"], outcome["warning"], "reposted"
            result = {"reply_id": new_id}
        now = utc_now()
        await firebase_db.responder_events.document(doc["id"]).update({
            "final_reply": text, "reply_result": result, "edited_at": now, "updated_at": now, "error": warning,
            "reply_lock": firebase_db.DELETE_FIELD,
            "reply_history": firebase_db.ArrayUnion([{
                "action": "edited", "mode": mode, "previous_text": old_text, "text": text,
                "previous_reply_id": old_id, "reply_id": new_id, "by": actor, "at": now, "warning": warning,
            }]),
        })
        return await _get_event(doc["id"])
    finally:
        await _unlock(doc["id"])


async def delete_posted_reply(user_id: str, event_id: str, actor: str) -> dict:
    """Remove a posted reply from the platform. On a platform error nothing is changed."""
    doc = await _lock_posted(user_id, event_id)
    try:
        old_id = (doc.get("reply_result") or {}).get("reply_id", "")
        if not doc.get("simulated"):
            blocked = change_support(doc)
            if blocked:
                raise _http_error(400, blocked)
            try:
                await delete_reply(user_id, doc, old_id)
            except ReplyError as e:
                raise _http_error(502, str(e))
            except Exception as e:
                raise _http_error(502, f"Could not reach {doc['platform'].title()} ({type(e).__name__}). Nothing was changed.")
        now = utc_now()
        await firebase_db.responder_events.document(doc["id"]).update({
            "status": "reply_deleted", "deleted_at": now, "updated_at": now, "error": "",
            "reply_lock": firebase_db.DELETE_FIELD,
            "reply_history": firebase_db.ArrayUnion([{"action": "deleted", "text": doc.get("final_reply") or "",
                                                      "reply_id": old_id, "by": actor, "at": now}]),
        })
        return await _get_event(doc["id"])
    finally:
        await _unlock(doc["id"])


async def save_as_answer(user_id: str, event_id: str) -> dict:
    """Make the event's current reply the answer of the rule (or fallback) that produced it.

    The answer that was originally posted is replaced, so the same correction is
    not needed twice; if it is no longer in the rule, the reply is added as a new answer.
    """
    doc = await firebase_db.get(_ref(event_id))
    if not doc or doc.get("user_id") != user_id:
        raise _http_error(404, "Item not found.")
    text = (doc.get("final_reply") or "").strip()
    if not text:
        raise _http_error(400, "This item has no reply to save.")
    posted = next((h.get("text") for h in doc.get("reply_history") or [] if h.get("action") == "posted"), None)
    original = (posted or doc.get("suggested_reply") or "").strip()

    persona = await get_persona(user_id)
    if doc.get("match_outcome") == "matched" and doc.get("rule_id"):
        target = next((r for r in persona["rules"] if r.get("id") == doc["rule_id"]), None)
        if not target:
            raise _http_error(404, "The rule that answered this comment no longer exists.")
        name = target.get("name", "rule")
    elif doc.get("match_outcome") == "fallback":
        target, name = persona["fallback"], "the fallback reply"
    else:
        raise _http_error(400, "This reply did not come from a rule.")

    answers = target.setdefault("answers", [])
    replaced = next((a for a in answers if (a.get("text") or "").strip() == original), None)
    if replaced:
        replaced["text"] = text
    elif all((a.get("text") or "").strip() != text for a in answers):
        lang = doc.get("reply_lang") if doc.get("reply_lang") in rule_matcher.LANGS else "any"
        answers.append({"text": text, "lang": lang})
    # The whole rule set is written, so a workspace still on the defaults keeps
    # them (a partial document would be re-migrated over this change).
    await firebase_db.upsert(
        _persona_ref(user_id),
        {**{k: persona[k] for k in PERSONA_FIELDS}, "user_id": user_id, "updated_at": utc_now()},
        on_create={"created_at": utc_now()},
    )
    return {"rule_name": name, "replaced": bool(replaced)}
