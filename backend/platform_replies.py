"""Send a reply to an inbound comment or DM through the platform's own API.

    await send_reply(user_id, event, text) -> {"reply_id": "...", "raw": {...}}
    raises ReplyError with a user-readable message on failure.

Required permissions (granted at connect time):
  Facebook  comments: pages_manage_engagement     DMs: pages_messaging
  Instagram comments: instagram_manage_comments   DMs: instagram_manage_messages
  LinkedIn  comments: w_organization_social / w_member_social (Community Management API)
  TikTok    comments: TikTok API for Business comment management (Login Kit tokens
            cannot reply). TikTok has no public DM reply API.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from config import GRAPH_BASE
from routers.social import engagement_account, page_token_for, save_user_account

GRAPH = GRAPH_BASE
LINKEDIN_API = "https://api.linkedin.com/v2"
TIMEOUT = 20.0


class ReplyError(RuntimeError):
    pass


def _graph_error(resp: httpx.Response, action: str) -> ReplyError:
    try:
        err = (resp.json() or {}).get("error") or {}
        message = err.get("message") or resp.text[:300]
        code = err.get("code")
    except Exception:
        message, code = resp.text[:300], None
    hint = ""
    # Only real permission/token errors (Meta's generic "object does not exist ...
    # missing permissions" text, code 100, usually means a deleted comment).
    if code in (10, 190, 200, 230) or (code is None and "permission" in message.lower()):
        hint = " Reconnect the account so Morrow can request the comment/message permissions."
    elif code == 100:
        hint = " The comment may have been deleted, or it is older than Meta allows replies for."
    return ReplyError(f"{action} failed: {message}{hint}")


async def _meta_reply(account: dict, event: dict, text: str) -> dict:
    platform = event["platform"]
    target = event.get("reply_target") or {}
    page_id, page_token = page_token_for(account, event.get("account_ref"))
    if not page_token:
        raise ReplyError(f"No Page access token found for this {platform} account. Reconnect it.")

    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        if event["kind"] == "comment":
            comment_id = target.get("comment_id") or event.get("external_id")
            # Facebook replies are nested comments; Instagram uses /replies.
            edge = "comments" if platform == "facebook" else "replies"
            resp = await http.post(
                f"{GRAPH}/{comment_id}/{edge}",
                data={"message": text, "access_token": page_token},
            )
            if resp.status_code != 200:
                raise _graph_error(resp, f"{platform.title()} comment reply")
            body = resp.json()
            return {"reply_id": body.get("id", ""), "raw": body}

        # Direct message (Messenger / Instagram Messaging) within the 24h window.
        recipient = target.get("recipient_id") or (event.get("author") or {}).get("id")
        if not recipient:
            raise ReplyError("The message sender id is missing, so a DM reply cannot be sent.")
        resp = await http.post(
            f"{GRAPH}/{page_id or 'me'}/messages",
            params={"access_token": page_token},
            json={
                "recipient": {"id": recipient},
                "messaging_type": "RESPONSE",
                "message": {"text": text},
            },
        )
        if resp.status_code != 200:
            raise _graph_error(resp, f"{platform.title()} DM reply")
        body = resp.json()
        return {"reply_id": body.get("message_id", ""), "raw": body}


async def _linkedin_reply(account: dict, event: dict, text: str) -> dict:
    if event["kind"] != "comment":
        raise ReplyError("LinkedIn does not offer a public API for replying to direct messages.")
    target = event.get("reply_target") or {}
    post_urn = target.get("post_urn") or event.get("post_id")
    if not post_urn:
        raise ReplyError("The LinkedIn post URN is missing for this comment.")
    actor = target.get("actor_urn")
    if not actor:
        pid = account.get("provider_account_id")
        actor = f"urn:li:person:{pid}" if pid else ""
    if not actor:
        raise ReplyError("Reconnect LinkedIn so Morrow knows which profile/page should reply.")

    payload = {"actor": actor, "object": post_urn, "message": {"text": text}}
    if target.get("comment_urn"):
        payload["parentComment"] = target["comment_urn"]

    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        resp = await http.post(
            f"{LINKEDIN_API}/socialActions/{quote(post_urn, safe='')}/comments",
            headers={
                "Authorization": f"Bearer {account['access_token']}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code not in (200, 201):
        raise ReplyError(f"LinkedIn comment reply failed: HTTP {resp.status_code} {resp.text[:300]}")
    try:
        body = resp.json()
    except Exception:
        body = {}
    return {"reply_id": body.get("id") or resp.headers.get("x-restli-id", ""), "raw": body}


async def _tiktok_reply(user_id: str, account: dict, event: dict, text: str) -> dict:
    from tiktok_client import TikTokError, tiktok

    if event["kind"] != "comment":
        raise ReplyError("TikTok does not offer a public API for replying to direct messages.")
    target = event.get("reply_target") or {}
    video_id = target.get("video_id") or event.get("post_id")
    comment_id = target.get("comment_id") or event.get("external_id")
    business_id = account.get("business_id") or account.get("open_id")
    if not (video_id and comment_id and business_id):
        raise ReplyError("TikTok comment reply is missing the video, comment or business account id.")
    try:
        if await tiktok.refresh_if_needed(account):
            save_user_account(user_id, "tiktok", account)
        body = await tiktok.reply_to_comment(account["access_token"], business_id, video_id, comment_id, text)
    except TikTokError as e:
        raise ReplyError(
            f"{e}. Replying to TikTok comments needs a TikTok API for Business token with comment permissions."
        )
    data = body.get("data") or {}
    return {"reply_id": data.get("comment_id", ""), "raw": body}


class LikeUnsupported(ReplyError):
    """The platform's API has no way to like a comment (not retryable)."""


async def send_like(user_id: str, event: dict) -> dict:
    """Like/heart an inbound comment. Used for emoji-only comments instead of a text reply."""
    platform = event.get("platform")
    if event.get("kind") != "comment":
        raise LikeUnsupported("Only comments can be liked.")
    account = engagement_account(user_id, platform)
    if not account.get("access_token"):
        raise ReplyError(f"{(platform or 'This platform').title()} is not connected anymore. Reconnect it to react.")
    target = event.get("reply_target") or {}

    if platform == "facebook":
        _, page_token = page_token_for(account, event.get("account_ref"))
        if not page_token:
            raise ReplyError("No Page access token found for this facebook account. Reconnect it.")
        comment_id = target.get("comment_id") or event.get("external_id")
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(f"{GRAPH}/{comment_id}/likes", data={"access_token": page_token})
        if resp.status_code != 200:
            raise _graph_error(resp, "Facebook comment like")
        return {"raw": resp.json()}

    if platform == "linkedin":
        comment_urn = target.get("comment_urn")
        actor = target.get("actor_urn")
        if not (comment_urn and actor):
            raise ReplyError("The LinkedIn comment or page id is missing, so it cannot be liked.")
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.post(
                f"{LINKEDIN_API}/socialActions/{quote(comment_urn, safe='')}/likes",
                headers={
                    "Authorization": f"Bearer {account['access_token']}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "Content-Type": "application/json",
                },
                json={"actor": actor, "object": comment_urn},
            )
        if resp.status_code not in (200, 201):
            raise ReplyError(f"LinkedIn comment like failed: HTTP {resp.status_code} {resp.text[:300]}")
        return {"raw": {}}

    # Instagram's Graph API can reply to / hide / delete comments but not like them,
    # and TikTok's comment API has no like endpoint.
    raise LikeUnsupported(f"{(platform or 'This platform').title()} does not allow liking comments through its API.")


# --------------------------------------------------------------------------
# Changing a reply after it was posted
# --------------------------------------------------------------------------
_LABELS = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "tiktok": "TikTok"}


def change_support(event: dict) -> str:
    """'' when a posted reply can be edited/deleted on its platform, else the reason it can't."""
    platform = event.get("platform")
    label = _LABELS.get(platform, platform or "This platform")
    if event.get("simulated"):
        return ""
    if event.get("kind") == "dm":
        return f"{label} does not let apps edit or delete a direct message once it is sent."
    if platform == "tiktok":
        return "TikTok's API does not let Morrow edit or delete a reply. Change it in the TikTok app."
    if platform not in ("facebook", "instagram", "linkedin"):
        return f"Changing replies is not supported for {label}."
    return ""


def _linkedin_comment_id(reply_id: str) -> str:
    # urn:li:comment:(urn:li:activity:123,456) -> 456; a bare id is used as is.
    return reply_id.rsplit(",", 1)[-1].rstrip(")") if reply_id.startswith("urn:") else reply_id


async def delete_reply(user_id: str, event: dict, reply_id: str) -> None:
    """Remove one posted reply from the platform. Raises ReplyError when it can't."""
    problem = change_support(event)
    if problem:
        raise ReplyError(problem)
    if not reply_id:
        raise ReplyError("The id of the posted reply was not recorded, so it can't be changed on the platform.")
    platform = event["platform"]
    account = engagement_account(user_id, platform)
    if not account.get("access_token"):
        raise ReplyError(f"{_LABELS[platform]} is not connected anymore. Reconnect it first.")

    if platform in ("facebook", "instagram"):
        _, page_token = page_token_for(account, event.get("account_ref"))
        if not page_token:
            raise ReplyError(f"No Page access token found for this {platform} account. Reconnect it.")
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            resp = await http.delete(f"{GRAPH}/{reply_id}", params={"access_token": page_token})
        try:
            ok = resp.status_code == 200 and (resp.json() or {}).get("success") is not False
        except ValueError:
            ok = False
        if not ok:
            raise _graph_error(resp, f"{_LABELS[platform]} reply delete")
        return

    target = event.get("reply_target") or {}
    post_urn = target.get("post_urn") or event.get("post_id")
    actor = target.get("actor_urn") or (
        f"urn:li:person:{account['provider_account_id']}" if account.get("provider_account_id") else ""
    )
    if not (post_urn and actor):
        raise ReplyError("The LinkedIn post or page id is missing, so the reply can't be deleted.")
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        resp = await http.delete(
            f"{LINKEDIN_API}/socialActions/{quote(post_urn, safe='')}/comments/{_linkedin_comment_id(reply_id)}",
            params={"actor": actor},
            headers={"Authorization": f"Bearer {account['access_token']}", "X-Restli-Protocol-Version": "2.0.0"},
        )
    if resp.status_code not in (200, 204):
        raise ReplyError(f"LinkedIn reply delete failed: HTTP {resp.status_code} {resp.text[:300]}")


async def replace_reply(user_id: str, event: dict, old_reply_id: str, text: str) -> dict:
    """Put `text` in place of a posted reply: post the new one, then delete the old one.

    Facebook, Instagram and LinkedIn replies are not edited in place. If the old
    reply can't be removed, the new one is taken down again and ReplyError is
    raised, so the platform is left as it was. Only if that also fails is the
    new reply kept, with a warning that both are visible.
    """
    problem = change_support(event)
    if problem:
        raise ReplyError(problem)
    if not old_reply_id:
        raise ReplyError("The id of the posted reply was not recorded, so it can't be changed on the platform.")
    new_id = (await send_reply(user_id, event, text)).get("reply_id", "")
    try:
        await delete_reply(user_id, event, old_reply_id)
    except Exception as e:
        reason = str(e)
        try:
            await delete_reply(user_id, event, new_id)
        except Exception as undo_error:
            return {"reply_id": new_id, "warning": (
                f"The new reply is live, but the old one could not be removed ({reason}) and the new one "
                f"could not be taken down again ({undo_error}). Both are visible on "
                f"{_LABELS[event['platform']]}; delete one there."
            )}
        raise ReplyError(f"The old reply could not be removed ({reason}). The new reply was taken down again, so nothing changed.")
    return {"reply_id": new_id, "warning": ""}


async def send_reply(user_id: str, event: dict, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ReplyError("The reply text is empty.")
    platform = event.get("platform")
    account = engagement_account(user_id, platform)
    if not account.get("access_token"):
        raise ReplyError(f"{(platform or 'This platform').title()} is not connected anymore. Reconnect it to reply.")

    if platform in ("facebook", "instagram"):
        return await _meta_reply(account, event, text)
    if platform == "linkedin":
        return await _linkedin_reply(account, event, text)
    if platform == "tiktok":
        return await _tiktok_reply(user_id, account, event, text)
    raise ReplyError(f"Replies are not supported for {platform}.")
