"""One-off look at what the Meta comment poller sees (never prints tokens).

    .venv\\Scripts\\python.exe debug_poll.py          dry run: reads only, replies to nothing
    .venv\\Scripts\\python.exe debug_poll.py --live   one real poll_once() pass, same as the scheduler

The dry run lists every Page / IG token on file with its validity and scopes,
which token and owner the poller actually uses, the responder switches for that
owner, and the latest comments with the step that would stop each one.
"""
from __future__ import annotations

import asyncio
import hashlib
import sys

import httpx

import firebase_db
import meta_poller
import routers.social as social_store
from config import (
    FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, GRAPH_BASE, META_POLL_INTERVAL,
    META_POLLING_ENABLED, RESPONDER_HOURLY_REPLY_LIMIT,
)

SCOPES_OF_INTEREST = (
    "pages_show_list", "pages_read_engagement", "pages_read_user_content", "pages_manage_engagement",
    "pages_manage_metadata", "pages_messaging", "pages_manage_posts",
    "instagram_basic", "instagram_manage_comments", "instagram_manage_messages",
)
COMMENTS_SHOWN = 15


def fp(token: str | None) -> str:
    return "tok#" + hashlib.sha256(token.encode()).hexdigest()[:8] if token else "tok#none"


async def debug_token(http: httpx.AsyncClient, token: str) -> str:
    r = await http.get(f"{GRAPH_BASE}/debug_token", params={
        "input_token": token, "access_token": f"{FACEBOOK_CLIENT_ID}|{FACEBOOK_CLIENT_SECRET}"})
    data = (r.json() or {}).get("data") or {}
    if not data.get("is_valid"):
        err = data.get("error") or {}
        return f"INVALID (code {err.get('code')}, subcode {err.get('subcode')}: {str(err.get('message', ''))[:90]})"
    scopes = set(data.get("scopes") or [])
    marks = " ".join(f"{s}={'yes' if s in scopes else 'NO'}" for s in SCOPES_OF_INTEREST)
    return f"valid {data.get('type', '').lower()} token; {marks}"


async def owner_gate(user_id: str) -> str:
    """The same checks responder_service._skip_reason runs, for a real (non-simulated) comment."""
    from deps import apply_dev_override, compute_subscription
    from responder_service import get_persona

    user = await firebase_db.get_by_id(firebase_db.users, user_id)
    if not user:
        return "USER DOES NOT EXIST -> every event is skipped ('The Morrow account no longer exists')"
    sub = compute_subscription(await apply_dev_override(dict(user)))
    persona = await get_persona(user_id, user)
    s = persona.get("auto_reply") or {}
    return (f"user exists; subscription access_active={sub.get('access_active')}; "
            f"auto_reply enabled={s.get('enabled')} platforms={s.get('platforms') or 'all'} "
            f"reply_to_comments={s.get('reply_to_comments', True)}; rules={len(persona.get('rules') or [])}")


async def event_status(user_id: str, platform: str, comment_id: str) -> str:
    doc = await firebase_db.get(firebase_db.responder_events.document(
        firebase_db.event_doc_id(user_id, platform, comment_id)))
    if not doc:
        return "no responder event"
    why = doc.get("decision_reason") or doc.get("error") or ""
    return f"responder event: {doc.get('status')}" + (f" ({str(why)[:110]})" if why else "")


async def show_comments(platform: str, account_id: str, owner: str | None, comments: list[tuple[dict, bool]]):
    seen_docs = await firebase_db.get_many(meta_poller.seen, [f"{platform}:{c['id']}" for c, _ in comments])
    seen = {d["id"].split(":", 1)[1] for d in seen_docs}
    for c, own in comments[:COMMENTS_SHOWN]:
        text = (c.get("message") or c.get("text") or "").replace("\n", " ")
        who = (c.get("from") or {}).get("name") or (c.get("from") or {}).get("username") or c.get("username") or "(no 'from')"
        when = c.get("created_time") or c.get("timestamp") or "?"
        if own:
            verdict = "skipped by poller: written by the Page / IG account itself"
        elif not text:
            verdict = "skipped by poller: no text (sticker / photo only)"
        elif c["id"] in seen:
            verdict = "already in meta_poll_seen (seeded or handled before)"
        else:
            verdict = "NEW -> next poll dispatches it"
        status = await event_status(owner, platform, c["id"]) if owner else "no owner"
        print(f"    {when}  {c['id']}  by {who}: {text[:50]!r}")
        print(f"        poller: {verdict} | {status}")


async def dry_run() -> None:
    print(f"META_POLLING_ENABLED={META_POLLING_ENABLED}  interval={META_POLL_INTERVAL}s  "
          f"hourly limit={RESPONDER_HOURLY_REPLY_LIMIT}  graph={GRAPH_BASE}")
    if firebase_db.INIT_ERROR:
        print("Firestore unavailable:", firebase_db.INIT_ERROR)
        return
    pages, igs = meta_poller.collect_targets()
    async with httpx.AsyncClient(timeout=25) as http:
        print("\nTokens on file (connected_accounts.json, file order)")
        for owner, platforms in social_store.connected_accounts.items():
            for key in ("facebook", "instagram"):
                acct = (platforms or {}).get(key)
                if not isinstance(acct, dict):
                    continue
                if acct.get("access_token"):
                    print(f"  ..{owner[-6:]} {key:9} user token {fp(acct['access_token'])}: "
                          f"{await debug_token(http, acct['access_token'])}")
                for page in acct.get("pages") or []:
                    tok = page.get("access_token")
                    used = [k for k, t in (("page", pages.get(str(page.get('id')))),
                                           ("ig", igs.get(str(page.get('instagram_business_id'))))) if tok and t == tok]
                    print(f"  ..{owner[-6:]} {key:9} page {page.get('id')} ({page.get('name')}) ig={page.get('instagram_business_id')} "
                          f"{fp(tok)}{'  <- POLLER USES for ' + '+'.join(used) if used else ''}")
                    if tok:
                        print(f"      {await debug_token(http, tok)}")

        for kind, platform, targets in (("page", "facebook", pages), ("ig", "instagram", igs)):
            for ident, token in targets.items():
                owners = social_store.find_owners_by_external_id(platform, ident)
                owner = owners[0][0] if owners else None
                st = await firebase_db.get(meta_poller.state.document(f"{kind}:{ident}")) or {}
                print(f"\n{platform} {ident}  polled with {fp(token)}  routed to owner "
                      f"{'..' + owner[-6:] if owner else 'NONE'} (candidates: {['..' + o[-6:] for o, _ in owners]})")
                print(f"  owner gate: {await owner_gate(owner) if owner else 'no owner: event dropped'}")
                print(f"  poll state: seeded={st.get('seeded')} seeded_at={st.get('seeded_at')}")
                try:
                    if kind == "page":
                        body = await meta_poller._graph(
                            http, f"{ident}/feed", token,
                            fields=("id,comments.limit(50).filter(stream).order(reverse_chronological)"
                                    "{id,message,from,created_time,parent{id}}"),
                            limit=meta_poller.FB_POSTS_PER_POLL)
                        comments = [(c, str((c.get("from") or {}).get("id")) == ident)
                                    for p in body.get("data") or [] for c in (p.get("comments") or {}).get("data") or []]
                    else:
                        username = (await meta_poller._graph(http, ident, token, fields="username")).get("username", "")
                        media = (await meta_poller._graph(http, f"{ident}/media", token, fields="id,comments_count",
                                                          limit=meta_poller.IG_MEDIA_PER_POLL)).get("data") or []
                        comments = []
                        for m in media:
                            if int(m.get("comments_count") or 0):
                                body = await meta_poller._graph(http, f"{m['id']}/comments", token,
                                                                fields="id,text,username,timestamp,from", limit=50)
                                comments += [(c, (c.get("username") or "").lower() == username.lower())
                                             for c in body.get("data") or []]
                    comments.sort(key=lambda x: x[0].get("created_time") or x[0].get("timestamp") or "", reverse=True)
                    print(f"  Graph OK: {len(comments)} comment(s) visible to the poller (newest first)")
                    await show_comments(platform, ident, owner, comments)
                except meta_poller.GraphError as e:
                    print(f"  Graph ERROR (code {e.code}): {str(e)[:160]}  <- poll_once() logs this at most every 10 min")


async def live() -> None:
    handled = await meta_poller.poll_once()
    print(f"poll_once() returned {handled} (comments dispatched to the responder this pass)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(live() if "--live" in sys.argv else dry_run())
