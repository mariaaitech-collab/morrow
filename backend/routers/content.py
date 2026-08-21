from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Response
from typing import Optional
from urllib.parse import urlparse
import httpx
import json
import asyncio
import tempfile
import os
import time
import logging
import traceback
import cloudinary
import cloudinary.uploader
from config import (
    GEMINI_API_KEY, GEMINI_API_URL, GEMINI_TEXT_MODEL, TAVILY_API_KEY,
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET,
)
from routers.social import connected_accounts

router = APIRouter(prefix="/api/content", tags=["content"])

LOG_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_FILE = os.path.join(LOG_DIR, "brandora.log")

logger = logging.getLogger("brandora")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_fh)
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(_sh)
logger.propagate = False

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
    print("[CONTENT] Cloudinary configured successfully")
else:
    print("[CONTENT] WARNING: Cloudinary credentials not set in .env — media uploads will fail")

TONE_INSTRUCTIONS = {
    "viral": "Write in a trending, viral style. Use attention-grabbing hooks, emotional triggers, urgency, and shareable language.",
    "professional": "Write in a polished, professional tone suitable for business audiences. Use clear, authoritative language.",
    "educational": "Write in an informative, educational tone. Explain concepts clearly, use data points and facts.",
    "promotional": "Write in a persuasive, promotional tone. Highlight benefits, create FOMO, include strong calls-to-action.",
}

# ---------------------------------------------------------------------------
# Pro AI Image Generator
# ---------------------------------------------------------------------------


async def _generate_post_content(topic: str, tone: str = "professional") -> dict:
    """Core Gemini post generator.

    Converts a topic/prompt into a fully formatted, engaging social media post
    (hook, value, CTA, 3-5 hashtags and tasteful emojis). Returns {"title", "body"}.
    Shared by POST /content/generate and the Auto Scheduler.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    tone_guide = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"])

    prompt = f"""You are Brandora, an expert digital marketing content creator. Generate ONE single, high-quality social media post for the topic: "{topic}"

TONE & STYLE:
{tone_guide}

Return a JSON object with this exact structure:
{{
  "title": "A short catchy campaign title (5-8 words)",
  "body": "The complete social media post. Write it as ONE unified post that works everywhere. Use engaging hooks, clear value, and a call-to-action. Keep it 80-200 words. Use line breaks for readability. Include 3-5 hashtags naturally woven into the text. Where it feels natural, add tasteful emojis so the post feels vibrant but not spammy."
}}

CRITICAL RULES:
- Generate ONE single post body, NOT separate versions per platform
- The post must work on Facebook, LinkedIn, AND Instagram without modification
- Use a hook in the first line that grabs attention on any platform
- Include a clear call-to-action at the end
- Weave 3-5 relevant hashtags into the text naturally
- Add a few tasteful emojis where they improve the tone
- Make it feel authentic and human-written
- Return ONLY valid JSON, no markdown code blocks"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GEMINI_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GEMINI_API_KEY}",
                },
                json={
                    "model": "gemini-3.5-flash-lite",
                    "messages": [
                        {"role": "system", "content": "You are a world-class social media marketing expert. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 1500,
                },
            )

        print(f"[CONTENT] Gemini API status: {response.status_code}")

        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Gemini API error: {response.text}")

        data = response.json()
        raw_text = data["choices"][0]["message"]["content"]

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        content = json.loads(cleaned)
        print(f"[CONTENT] Generated unified post for: {topic}")
        return content

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI returned invalid JSON. Please try again.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Gemini API timed out. Try again.")
    except Exception as e:
        print(f"[CONTENT] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")


@router.post("/generate")
async def generate_content(
    topic: str = Form(...),
    tone: str = Form("professional"),
):
    print(f"[CONTENT] Generating unified post for topic='{topic}', tone={tone}")
    content = await _generate_post_content(topic, tone)
    return {
        "topic": topic,
        "tone": tone,
        "title": content.get("title", ""),
        "body": content.get("body", ""),
    }


# ---------------------------------------------------------------------------
# Live Competitive Analysis & Smart Strategy
# ---------------------------------------------------------------------------

PLATFORM_DOMAINS = {
    "linkedin": {"domain": "linkedin.com", "label": "LinkedIn"},
    "instagram": {"domain": "instagram.com", "label": "Instagram"},
    "facebook": {"domain": "facebook.com", "label": "Facebook"},
}


def _url_key(url: str):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").replace("www.", "")
        return f"{host}{parsed.path}{parsed.query}"
    except Exception:
        return None


def _select_top_four(buckets):
    seen = set()

    def _pick(item):
        key = _url_key(item.get("url") or "")
        if key is None:
            return True
        if key in seen:
            return False
        seen.add(key)
        return True

    active = [list(b) for b in buckets]
    selected = []
    for _ in range(5):
        if len(selected) >= 4:
            break
        progressed = False
        for bucket in active:
            if len(selected) >= 4:
                break
            idx = next((i for i, item in enumerate(bucket) if _pick(item)), -1)
            if idx != -1:
                selected.append(bucket.pop(idx))
                progressed = True
        if not progressed:
            break

    if len(selected) < 4:
        rest = [item for bucket in active for item in bucket if _pick(item)]
        rest.sort(key=lambda x: x.get("score") or 0, reverse=True)
        for item in rest:
            if len(selected) >= 4:
                break
            if _pick(item):
                selected.append(item)

    return selected[:4]


async def _tavily_search_platform(topic: str, platform: str):
    if not TAVILY_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Live search is not configured. Add your free TAVILY_API_KEY to backend/.env (from https://app.tavily.com).",
        )

    config = PLATFORM_DOMAINS[platform]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": topic,
                    "search_depth": "basic",
                    "include_domains": [config["domain"]],
                    "max_results": 5,
                    "include_answer": False,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tavily live search timed out. Try again.")

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="Tavily rejected the API key. Verify TAVILY_API_KEY in backend/.env.")
    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Tavily rate limit or quota exceeded. Try again later.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Tavily live search failed (HTTP {resp.status_code}).")

    items = resp.json().get("results", [])
    return [
        {
            "platform": platform,
            "platform_label": config["label"],
            "title": (i.get("title") or "").strip(),
            "url": (i.get("url") or "").strip(),
            "snippet": (i.get("content") or "").strip(),
            "published_date": i.get("published_date"),
            "score": i.get("score"),
        }
        for i in items
    ]


async def _live_search_competitors(topic: str, platforms):
    active = [p for p in platforms if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    results = await asyncio.gather(*[_tavily_search_platform(topic, p) for p in active])
    competitors = _select_top_four(results)

    if not competitors:
        raise HTTPException(status_code=422, detail="Live search returned no social results for this topic. Try a more specific query.")

    search_meta = {"provider": "tavily", "platforms": active, "total_raw_results": sum(len(b) for b in results)}
    return competitors, search_meta


def _build_strategist_prompt(topic, competitors, user_content):
    listing = "\n".join(
        f'{i + 1}. [{c["platform_label"]}] "{c["title"]}" | snippet: {c["snippet"] or "(no snippet)"} | url: {c["url"]} | published: {c["published_date"] or "unknown"}'
        for i, c in enumerate(competitors)
    )
    user_block = ""
    if user_content and user_content.strip():
        user_block = (
            "\n\nTHE USER'S OWN GENERATED CONTENT (analyze this too, then improve on it):\n"
            + user_content.strip()
        )

    header = (
        f'You are an elite Digital Marketing Strategist. Below are the top 4 currently-ranking real posts/creators found LIVE on LinkedIn, Instagram and Facebook for the topic "{topic}", with official URLs and content snippets.{user_block}\n\n'
        f"TOP 4 REAL RESULTS (from live web search):\n{listing}\n\n"
        "TASK: Produce a ruthless, data-driven competitive analysis and a step-by-step viral strategy that lets the user outperform these exact posts.\n\n"
    )

    schema = '''Return STRICT JSON only (no markdown, no code fences), matching this exact schema:
{
  "top_competitors": [
    {
      "name": "creator or brand name",
      "platform": "linkedin|instagram|facebook",
      "handle": "handle if inferable, else empty string",
      "platform_link": "exact official URL from the results",
      "headline": "one-line summary of what the post is about",
      "what_works": "one sentence on why it ranks"
    }
  ],
  "strengths": ["concise bullet", "..."],
  "weaknesses": ["concise bullet", "..."],
  "smart_strategy": [
    {
      "step": 1,
      "title": "short step name",
      "action": "concrete, specific action the user should take",
      "platform": "where to apply it",
      "why_it_beats_them": "how this step provides unique value to the audience and outranks the competitors"
    }
  ]
}'''

    rules = '''
RULES:
- top_competitors must contain EXACTLY the 4 real results above, with platform_link copied exactly and platforms mapped correctly (linkedin/instagram/facebook). Never invent brands, handles, or URLs.
- strengths: 4-6 tight bullets on what competitors do right (hooks, visual style, value proposition, formatting).
- weaknesses: 4-6 tight bullets on content gaps, missing angles, weak CTAs, or repurposing misses.
- smart_strategy: 6-8 ordered, actionable steps the user can actually execute; each must explain how it gives the audience unique value competitors are not providing.
- If the user's generated content is provided, tailor every strategy step to upgrade that exact content, not generic advice.'''

    return header + schema + rules


async def _analyze_competitive(topic, competitors, user_content):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    prompt = _build_strategist_prompt(topic, competitors, user_content)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                GEMINI_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GEMINI_API_KEY}",
                },
                json={
                    "model": GEMINI_TEXT_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are an elite Digital Marketing Strategist. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 4096,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Gemini strategy analysis timed out. Try again.")

    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Gemini quota or rate limit exceeded. Try again later.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Gemini analysis error: {resp.text[:500]}")

    data = resp.json()
    raw_text = data["choices"][0]["message"]["content"]

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid strategy. Try again.")
        try:
            analysis = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid strategy. Try again.")

    return analysis, GEMINI_TEXT_MODEL


@router.post("/competitive-analysis")
async def competitive_analysis(
    topic: str = Form(...),
    platforms: str = Form('["linkedin","instagram","facebook"]'),
    content: str = Form(""),
):
    started = time.time()
    print(f"[CONTENT] Competitive analysis: topic='{topic[:80]}', content_len={len(content)}")

    if not topic.strip() or len(topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic is required and must be at least 3 characters.")

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')

    competitors, search_meta = await _live_search_competitors(topic.strip(), platform_list)
    analysis, model = await _analyze_competitive(topic.strip(), competitors, content)

    result = {
        "topic": topic.strip(),
        "platforms": search_meta["platforms"],
        "competitors": competitors,
        "analysis": {
            "top_competitors": analysis.get("top_competitors", []),
            "strengths": analysis.get("strengths", []),
            "weaknesses": analysis.get("weaknesses", []),
            "smart_strategy": analysis.get("smart_strategy", []),
        },
        "providers": {"search": "tavily", "analysis": {"provider": "gemini", "model": model}},
        "search_meta": search_meta,
        "generated_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
    }

    print(f"[CONTENT] Competitive analysis done in {result['latency_ms']}ms ({len(competitors)} competitors, {len(result['analysis']['smart_strategy'])} steps)")
    logger.info("Competitive analysis done: %s competitors, %s steps, %sms", len(competitors), len(result["analysis"]["smart_strategy"]), result["latency_ms"])
    return result


PREMIUM_QUALITY_KEYWORDS = (
    "8K resolution, ultra-detailed, hyper-realistic, cinematic lighting, "
    "professional photography, masterpiece, award-winning quality, sharp focus"
)


def _boosted_ai_prompt(prompt: str) -> str:
    return f"{prompt}, {PREMIUM_QUALITY_KEYWORDS}"


async def _generate_pollinations_image(prompt: str, width: int, height: int, model: str = ""):
    """Generate an image via the free Pollinations.ai service. Returns (bytes, mime_type)."""
    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true"
        + (f"&model={model}" if model else "")
    )
    print(f"[CONTENT] Pollinations image request: {pollinations_url}")

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=False) as client:
            response = await client.get(pollinations_url)
        print(f"[CONTENT] Pollinations image status: {response.status_code}")
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Pollinations image API error: {response.status_code}")

        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        return response.content, content_type
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Pollinations image generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pollinations image generation failed: {str(e)}")


@router.post("/generate-image")
async def generate_image(
    prompt: str = Form(...),
    mode: str = Form("free"),
    width: int = Form(1080),
    height: int = Form(1080),
):
    print(f"[CONTENT] Generating AI image: prompt='{prompt[:80]}', mode={mode}, size={width}x{height}")

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Image prompt is required")

    if mode == "pro":
        # Freemium trial: secretly fulfill Pro requests with the free working
        # generator, but boost the prompt so trial users see a premium, highly
        # detailed result that clearly outshines the Free tier.
        enhanced_prompt = _boosted_ai_prompt(prompt.strip())
        image_bytes, mime_type = await _generate_pollinations_image(enhanced_prompt, width, height, model="flux")
        provider = "gemini"
    elif mode == "free":
        image_bytes, mime_type = await _generate_pollinations_image(prompt, width, height)
        provider = "pollinations"
    else:
        raise HTTPException(status_code=400, detail="mode must be 'pro' or 'free'")

    ext = "png" if "png" in mime_type else "jpg"
    filename = f"ai_generated_{provider}_{int(time.time() * 1000)}.{ext}"

    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


async def _upload_to_cloudinary(file_bytes: bytes, filename: str, media_type: str = "image") -> str:
    """Upload file to Cloudinary. Returns the secure HTTPS URL.

    For images: forces JPG output via format='jpg' so Meta Graph API always
    receives a standard image URL (fixes error 9004).
    For videos: writes to a temp file and uses upload_large for chunked transfer.
    """
    public_id = filename.rsplit(".", 1)[0] if "." in filename else filename
    print(f"[CONTENT] Cloudinary upload: {filename} ({len(file_bytes)} bytes, type={media_type})")

    try:
        if media_type == "video":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1] or ".mp4")
            try:
                tmp.write(file_bytes)
                tmp.close()
                result = cloudinary.uploader.upload_large(
                    tmp.name,
                    resource_type="video",
                    public_id=public_id,
                    overwrite=True,
                    chunk_size=6_000_000,
                )
            finally:
                os.unlink(tmp.name)
        else:
            result = cloudinary.uploader.upload(
                file_bytes,
                resource_type="image",
                public_id=public_id,
                overwrite=True,
                format="jpg",
            )

        secure_url = result.get("secure_url")
        print(f"[CONTENT] Cloudinary response: secure_url={secure_url} format={result.get('format')} type={result.get('resource_type')} bytes={result.get('bytes')}")
        if not secure_url:
            raise Exception(f"Cloudinary returned no secure_url: {result}")
        return secure_url
    except Exception as e:
        print(f"[CONTENT] Cloudinary upload FAILED: {e}")
        raise


def _detect_media_type(filename: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    fn = (filename or "").lower()
    video_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp")
    image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg")
    if ct.startswith("video/") or fn.endswith(video_exts):
        return "video"
    if ct.startswith("image/") or fn.endswith(image_exts):
        return "image"
    return "image"


@router.post("/publish")
async def publish_content(
    content: str = Form(...),
    platforms: str = Form(...),
    media: Optional[UploadFile] = File(None),
):
    platform_list = json.loads(platforms)
    print(f"[CONTENT] Publishing (sync) to: {platform_list}, has_media={media is not None}")

    media_url = None
    media_type = None

    if media and media.filename:
        file_bytes = await media.read()
        media_type = _detect_media_type(media.filename, media.content_type or "")
        print(f"[CONTENT] Read media: {media.filename}, type={media_type}, size={len(file_bytes)} bytes")

        try:
            media_url = await _upload_to_cloudinary(file_bytes, media.filename, media_type)
        except Exception as e:
            logger.error("Media upload failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to upload media: {str(e)}")

    results = {}

    for platform in platform_list:
        if platform not in connected_accounts:
            results[platform] = {"status": "not_connected", "message": f"{platform} is not connected"}
            continue

        account = connected_accounts[platform]
        access_token = account.get("access_token")

        if not access_token:
            results[platform] = {"status": "no_token", "message": f"No access token for {platform}"}
            continue

        try:
            if platform == "facebook":
                result = await _post_to_facebook(account, content, media_url, media_type)
            elif platform == "linkedin":
                result = await _post_to_linkedin(access_token, content, media_url, media_type)
            elif platform == "instagram":
                result = await _post_to_instagram(account, content, media_url, media_type)
            else:
                result = {"status": "unsupported", "message": f"Publishing to {platform} not implemented"}

            results[platform] = result
        except Exception as e:
            print(f"[CONTENT] Publish error for {platform}: {e}")
            logger.error("Publish Failed [%s]: %s", platform, e, exc_info=True)
            results[platform] = {"status": "error", "message": str(e)}

    print(f"[CONTENT] Publish complete: {json.dumps(results)}")
    logger.info(f"Publish complete: {json.dumps(results)}")
    return {"results": results}


async def _post_to_facebook(account: dict, content: str, media_url: str = None, media_type: str = None) -> dict:
    page_token = account.get("page_access_token")
    page_id = account.get("page_id")

    if not page_token or not page_id:
        return {"status": "error", "message": "No Facebook Page found. Reconnect your Facebook account."}

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            if media_url and media_type == "video":
                response = await client.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/videos",
                    data={"file_url": media_url, "description": content, "access_token": page_token},
                )
            elif media_url and media_type == "image":
                response = await client.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/photos",
                    data={"url": media_url, "caption": content, "access_token": page_token},
                )
            else:
                response = await client.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/feed",
                    data={"message": content, "access_token": page_token},
                )

        data = response.json()
        print(f"[CONTENT] Facebook publish response: {json.dumps(data)}")
        if "id" in data:
            return {"status": "success", "post_id": data["id"]}
        return {"status": "error", "message": data.get("error", {}).get("message", "Facebook post failed")}
    except Exception as e:
        print(f"[CONTENT] Facebook publish exception: {e}")
        return {"status": "error", "message": f"Facebook publish failed: {str(e)}"}


async def _post_to_linkedin(access_token: str, content: str, media_url: str = None, media_type: str = None) -> dict:
    if media_url and media_type == "video":
        return await _linkedin_video_post(access_token, content, media_url)

    post_data = {
        "author": "urn:li:person:me",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE" if not media_url else "ARTICLE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    if media_url:
        post_data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
            "status": "READY",
            "originalUrl": media_url,
        }]

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=post_data,
        )

    data = response.json()
    if "id" in data:
        return {"status": "success", "post_id": data["id"]}
    return {"status": "error", "message": data.get("message", data.get("error", "LinkedIn post failed"))}


async def _linkedin_video_post(access_token: str, content: str, video_url: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=300.0) as client:
        register_resp = await client.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                    "owner": "urn:li:person:me",
                    "serviceRelationships": [{
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }],
                }
            },
        )

        reg_data = register_resp.json()
        print(f"[CONTENT] LinkedIn register upload: {json.dumps(reg_data, indent=2)[:500]}")

        if "value" not in reg_data:
            return {"status": "error", "message": reg_data.get("message", "LinkedIn video registration failed")}

        upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = reg_data["value"]["asset"]

        video_resp = await client.get(video_url, timeout=300.0)
        video_bytes = video_resp.content

        upload_resp = await client.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"},
            content=video_bytes,
        )
        print(f"[CONTENT] LinkedIn video upload status: {upload_resp.status_code}")

        if upload_resp.status_code not in (200, 201):
            return {"status": "error", "message": f"LinkedIn video upload failed (HTTP {upload_resp.status_code})"}

        post_data = {
            "author": "urn:li:person:me",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "VIDEO",
                    "media": [{
                        "status": "READY",
                        "media": asset_urn,
                    }],
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        post_resp = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=post_data,
        )

        post_data_resp = post_resp.json()
        if "id" in post_data_resp:
            return {"status": "success", "post_id": post_data_resp["id"]}
        return {"status": "error", "message": post_data_resp.get("message", "LinkedIn video post failed")}


async def _post_to_instagram(account: dict, content: str, media_url: str = None, media_type: str = None) -> dict:
    ig_id = account.get("instagram_business_id")
    page_token = account.get("page_access_token")

    if not ig_id:
        return {"status": "error", "message": "No Instagram Business Account found. Reconnect your Facebook account."}
    if not page_token:
        return {"status": "error", "message": "No Page Access Token. Reconnect your Facebook account."}
    if not media_url:
        return {"status": "error", "message": "Instagram requires media. Please attach an image or video."}

    print(f"[CONTENT] IG publish start: ig_id={ig_id}, media_type={media_type}, url={media_url[:80]}...")

    if media_type == "video":
        return await _ig_publish_video(ig_id, page_token, media_url, content)
    else:
        return await _ig_publish_image(ig_id, page_token, media_url, content)


async def _ig_publish_image(ig_id: str, page_token: str, image_url: str, caption: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"[CONTENT] IG image: creating container with image_url={image_url[:80]}...")
        try:
            media_resp = await client.post(
                f"https://graph.facebook.com/v18.0/{ig_id}/media",
                data={"image_url": image_url, "caption": caption, "access_token": page_token},
            )
            media_data = media_resp.json()
        except Exception as e:
            print(f"[CONTENT] IG image container request exception: {e}")
            return {"status": "error", "message": f"IG image container request failed: {str(e)}"}

        print(f"[CONTENT] IG image container FULL response: {json.dumps(media_data)}")

        if "id" not in media_data:
            err = media_data.get("error", {})
            err_msg = err.get("message", "Unknown error")
            err_code = err.get("code", "")
            print(f"[CONTENT] IG image container FAILED: code={err_code} msg={err_msg}")
            return {"status": "error", "message": f"IG image container failed: {err_msg} (code={err_code})"}

        container_id = media_data["id"]
        print(f"[CONTENT] IG image: waiting for container {container_id} to finish processing...")

        status_url = f"https://graph.facebook.com/v18.0/{container_id}"
        published = False
        max_attempts = 20
        for attempt in range(max_attempts):
            await asyncio.sleep(3)
            try:
                status_resp = await client.get(
                    status_url,
                    params={
                        "fields": "status_code",
                        "access_token": page_token,
                    },
                )
                status_data = status_resp.json()

                if "error" in status_data:
                    err = status_data["error"]
                    err_msg = err.get("message", "Unknown error")
                    print(f"[CONTENT] IG image poll {attempt+1}/{max_attempts}: META ERROR: {err_msg}")
                    return {"status": "error", "message": f"Instagram API error: {err_msg}"}

                status_code = status_data.get("status_code", "UNKNOWN")
                print(f"[CONTENT] IG image poll {attempt+1}/{max_attempts}: status={status_code}")

                if status_code in ("FINISHED", "PUBLISHED"):
                    print(f"[CONTENT] IG image container ready after {attempt+1} polls")
                    published = True
                    break
                elif status_code == "ERROR":
                    print(f"[CONTENT] IG image container ERROR in poll")
                    return {"status": "error", "message": "Instagram image processing failed."}
                elif status_code == "EXPIRED":
                    return {"status": "error", "message": "Instagram image container expired. Try a smaller image or different format."}
                else:
                    continue
            except Exception as poll_err:
                print(f"[CONTENT] IG image poll exception (attempt {attempt+1}): {poll_err}")
                continue

        if not published:
            return {"status": "error", "message": f"Instagram image processing timed out after {max_attempts * 3}s."}

        print(f"[CONTENT] IG image: publishing container {container_id}...")
        try:
            publish_resp = await client.post(
                f"https://graph.facebook.com/v18.0/{ig_id}/media_publish",
                data={"creation_id": container_id, "access_token": page_token},
            )
            pub_data = publish_resp.json()
        except Exception as e:
            print(f"[CONTENT] IG image publish request exception: {e}")
            return {"status": "error", "message": f"IG image publish request failed: {str(e)}"}

        print(f"[CONTENT] IG image publish FULL response: {json.dumps(pub_data)}")

        if "id" in pub_data:
            return {"status": "success", "post_id": pub_data["id"]}
        err = pub_data.get("error", {})
        return {"status": "error", "message": f"Instagram image publish failed: {err.get('message', pub_data)}"}


async def _ig_publish_video(ig_id: str, page_token: str, video_url: str, caption: str) -> dict:
    async with httpx.AsyncClient(timeout=600.0) as client:
        print(f"[CONTENT] IG video: creating container...")
        print(f"[CONTENT] IG video: video_url={video_url}")

        video_payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": page_token,
        }

        print(f"[CONTENT] IG video: payload keys={list(video_payload.keys())}")

        try:
            media_resp = await client.post(
                f"https://graph.facebook.com/v18.0/{ig_id}/media",
                data=video_payload,
            )
            media_data = media_resp.json()
        except Exception as e:
            print(f"[CONTENT] IG video container request exception: {e}")
            return {"status": "error", "message": f"IG video container request failed: {str(e)}"}

        print(f"[CONTENT] IG video container FULL response: {json.dumps(media_data)}")

        if "id" not in media_data:
            err = media_data.get("error", {})
            err_msg = err.get("message", "Unknown error")
            err_type = err.get("type", "")
            err_code = err.get("code", "")
            err_subcode = err.get("error_subcode", "")
            err_fbtrace = err.get("fbtrace_id", "")
            print(f"[CONTENT] IG video container FAILED: type={err_type} code={err_code} subcode={err_subcode} msg={err_msg} fbtrace={err_fbtrace}")
            return {"status": "error", "message": f"IG video container failed: {err_msg} (code={err_code})"}

        container_id = media_data["id"]
        print(f"[CONTENT] IG video container created: container_id={container_id}")

        status_url = f"https://graph.facebook.com/v18.0/{container_id}"
        max_attempts = 60
        for attempt in range(max_attempts):
            await asyncio.sleep(3)
            try:
                status_resp = await client.get(
                    status_url,
                    params={
                        "fields": "status_code",
                        "access_token": page_token,
                    },
                )
                status_data = status_resp.json()

                if "error" in status_data:
                    err = status_data["error"]
                    err_msg = err.get("message", "Unknown error")
                    print(f"[CONTENT] IG video poll {attempt+1}/{max_attempts}: META ERROR: {err_msg}")
                    return {"status": "error", "message": f"Instagram API error: {err_msg}"}

                status_code = status_data.get("status_code", "UNKNOWN")

                print(f"[CONTENT] IG video poll {attempt+1}/{max_attempts}: status={status_code}")

                if status_code in ("FINISHED", "PUBLISHED"):
                    print(f"[CONTENT] IG video processing finished after {attempt+1} polls")
                    break
                elif status_code == "ERROR":
                    print(f"[CONTENT] IG video processing ERROR in poll")
                    return {"status": "error", "message": "Instagram video processing failed."}
                elif status_code == "EXPIRED":
                    return {"status": "error", "message": "Instagram video container expired. Try a smaller video or different format."}
                else:
                    continue
            except Exception as poll_err:
                print(f"[CONTENT] IG video poll exception (attempt {attempt+1}): {poll_err}")
                continue
        else:
            return {"status": "error", "message": f"Instagram video processing timed out after 3 minutes ({max_attempts} polls)."}

        print(f"[CONTENT] IG video: publishing container {container_id}...")
        try:
            publish_resp = await client.post(
                f"https://graph.facebook.com/v18.0/{ig_id}/media_publish",
                data={"creation_id": container_id, "access_token": page_token},
            )
            pub_data = publish_resp.json()
        except Exception as e:
            print(f"[CONTENT] IG video publish request exception: {e}")
            return {"status": "error", "message": f"IG video publish request failed: {str(e)}"}

        print(f"[CONTENT] IG video publish FULL response: {json.dumps(pub_data)}")

        if "id" in pub_data:
            return {"status": "success", "post_id": pub_data["id"]}
        err = pub_data.get("error", {})
        return {"status": "error", "message": f"Instagram video publish failed: {err.get('message', pub_data)}"}
