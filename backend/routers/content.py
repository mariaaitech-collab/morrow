from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form, Response
from starlette.responses import JSONResponse
from typing import Optional
from urllib.parse import urlparse
import httpx
import json
import asyncio
import os
import time
import uuid
import logging
import traceback
from pathlib import Path
from config import (
    GEMINI_API_KEY, GEMINI_API_URL, GEMINI_TEXT_MODEL, TAVILY_API_KEY,
    GRAPH_BASE, GRAPH_VIDEO_BASE,
)
import limits
import image_provider
from routers.social import refresh_fb_pages_for_user, get_user_accounts
from usage import get_optional_user, record_usage
from deps import get_current_user, require_subscription, require_token, deduct_token, remaining_tokens

router = APIRouter(prefix="/api/content", tags=["content"])

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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

TONE_INSTRUCTIONS = {
    "viral": "Write in a trending, viral style. Use attention-grabbing hooks, emotional triggers, urgency, and shareable language.",
    "professional": "Write in a polished, professional tone suitable for business audiences. Use clear, authoritative language.",
    "educational": "Write in an informative, educational tone. Explain concepts clearly, use data points and facts.",
    "promotional": "Write in a persuasive, promotional tone. Highlight benefits, create FOMO, include strong calls-to-action.",
}

# ---------------------------------------------------------------------------
# Pro AI Image Generator
# ---------------------------------------------------------------------------


def _language_rule(language: str) -> str:
    """Build the injected language instruction for the AI.

    If a non-empty language was provided, instruct Gemini to write the entire
    response strictly in that language. Otherwise default to English.
    """
    lang = (language or "").strip() or "English"
    return (
        f"LANGUAGE: You MUST write the entire response strictly in {lang}. "
        f"Do not use English unless explicitly asked.\n"
    )


def _cached_at_str(value) -> str:
    """Human-readable 'as of' date for a cached analysis result."""
    if value is None:
        return "an earlier run"
    try:
        if isinstance(value, str):
            from datetime import datetime
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.strftime("%d %b %Y, %H:%M")
    except Exception:
        return "an earlier run"


async def _generate_post_content(topic: str, tone: str = "professional", language: str = "") -> dict:
    """Core Gemini post generator.

    Converts a topic/prompt into a fully formatted, engaging social media post
    (hook, value, CTA, 3-5 hashtags and tasteful emojis). Returns {"title", "body"}.
    Shared by POST /content/generate and the Auto Scheduler.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    tone_guide = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"])
    lang_rule = _language_rule(language)

    prompt = f"""{lang_rule}
You are Brandora, an expert digital marketing content creator. Generate ONE single, high-quality social media post for the topic: "{topic}"

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
                    "max_tokens": limits.CAPTION_MAX_TOKENS,
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
    request: Request,
    user: dict = Depends(require_token),
    topic: str = Form(...),
    tone: str = Form("professional"),
    language: str = Form(""),
):
    print(f"[CONTENT] Generating unified post for topic='{topic}', tone={tone}, language='{language}'")

    # Cost guard #1: reject oversized input before any API spend.
    limits.validate_input_len(topic, "Topic")

    # Cost guard #2: consume a caption-generation credit up-front so hard-limit
    # users are blocked BEFORE the paid Gemini call, and regenerations still
    # count against the cycle quota.
    usage_info = await limits.consume(
        user, "captions", 1,
        action="caption_generation", endpoint="POST /api/content/generate",
    )

    content = await _generate_post_content(topic, tone, language)

    remaining = await deduct_token(user)
    await record_usage(user, "content_generation", "Generated an AI caption", f"Topic: {topic.strip()[:90]}")

    return {
        "topic": topic,
        "tone": tone,
        "title": content.get("title", ""),
        "body": content.get("body", ""),
        "tokens_left": remaining,
        "usage": usage_info,
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


async def _tavily_search_platform(topic: str, platform: str, location: str = ""):
    if not TAVILY_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Live search is not configured. Add your free TAVILY_API_KEY to backend/.env (from https://app.tavily.com).",
        )

    config = PLATFORM_DOMAINS[platform]
    # When a geographic location is provided, scope the live search to that
    # local market so competitors genuinely reflect the user's region.
    query = topic
    if location and location.strip():
        query = f"{topic} {location.strip()}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
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
                    "max_tokens": limits.ANALYSIS_MAX_TOKENS,
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
    user: dict = Depends(require_subscription),
    topic: str = Form(...),
    platforms: str = Form('["linkedin","instagram","facebook"]'),
    content: str = Form(""),
):
    started = time.time()
    print(f"[CONTENT] Competitive analysis: topic='{topic[:80]}', content_len={len(content)}")

    if not topic.strip() or len(topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic is required and must be at least 3 characters.")

    # Cost guard #1: reject oversized input before any API spend.
    limits.validate_input_len(topic, "Topic")
    limits.validate_input_len(content, "Content")

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')
    if not isinstance(platform_list, list) or not platform_list:
        raise HTTPException(status_code=400, detail="Select at least one platform.")
    active = [p for p in platform_list if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    cache_key = limits.make_cache_key(
        ["competitive", topic.strip(), sorted(active), content]
    )
    cached = await limits.get_cached_result(cache_key)
    if cached:
        result = cached["payload"]
        result["cache_note"] = f'Showing your cached competitive analysis from {_cached_at_str(cached["cached_at"])}.'
        print(f"[CONTENT] Served cached competitive analysis for topic='{topic[:60]}'")
        return result

    # Cost guard #2: each fresh lookup burns 1 Tavily credit per platform.
    # Combined business+content counter, hard-capped BEFORE hitting the API.
    try:
        usage_info = await limits.consume(
            user, "analysis", len(active),
            action="competitive_analysis", endpoint="POST /api/content/competitive-analysis",
        )
    except HTTPException as e:
        if e.status_code == 402:
            stale = await limits.get_expired_result(cache_key)
            if stale:
                result = stale["payload"]
                result["cache_note"] = f'Showing your last competitive analysis from {_cached_at_str(stale["cached_at"])}.'
                result["usage_warning"] = e.detail
                return result
        raise

    competitors, search_meta = await _live_search_competitors(topic.strip(), active)
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
        "usage": usage_info,
    }

    try:
        await limits.put_cached_result(cache_key, result)
    except Exception as e:
        logger.warning("Failed to cache competitive analysis: %s", e)

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
    """Generate an image with the configured provider (IMAGE_PROVIDER). Returns (bytes, mime_type).

    Raises HTTPException carrying the provider's real reason (503 when no
    provider is configured, 502 when the provider refused or failed).
    """
    try:
        return await image_provider.generate(prompt, width, height, model=model)
    except image_provider.ImageProviderError as e:
        raise HTTPException(status_code=e.http_status, detail=e.reason)


@router.get("/image-provider")
async def image_provider_status(user: dict = Depends(get_current_user)):
    """Whether AI image generation can be offered right now, and if not, why."""
    return image_provider.status()


@router.post("/generate-image")
async def generate_image(
    request: Request,
    user: dict = Depends(require_token),
    prompt: str = Form(...),
    mode: str = Form("free"),
    width: int = Form(1080),
    height: int = Form(1080),
    count: int = Form(1),
):
    print(f"[CONTENT] Generating AI image: prompt='{prompt[:80]}', mode={mode}, size={width}x{height}, count={count}")

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Image prompt is required")

    limits.validate_input_len(prompt, "Image prompt")

    # Lock resolution for the Starter tier: 1024x1024, no resolution overrides.
    effective_size = limits.STARTER_IMAGE_SIZE

    # Each image = +1 image-generation credit; 1..4 allowed per single post.
    if count < 1 or count > limits.MAX_IMAGES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"You can generate between 1 and {limits.MAX_IMAGES_PER_REQUEST} images per post.",
        )

    if image_provider.problem():
        raise HTTPException(status_code=503, detail=image_provider.problem())

    # Hard-block BEFORE any external call if the cycle image quota is exhausted;
    # the credits are only spent once the images were actually made.
    await limits.check_available(user, "images", count)

    images = []
    for _ in range(count):
        if mode == "pro":
            enhanced_prompt = _boosted_ai_prompt(prompt.strip())
            image_bytes, mime_type = await _generate_pollinations_image(enhanced_prompt, effective_size, effective_size, model="flux")
            provider = "gemini"
        elif mode == "free":
            image_bytes, mime_type = await _generate_pollinations_image(prompt, effective_size, effective_size)
            provider = "pollinations"
        else:
            raise HTTPException(status_code=400, detail="mode must be 'pro' or 'free'")
        images.append((image_bytes, mime_type, provider))

    usage_info = await limits.consume(
        user, "images", count,
        action="image_generation", endpoint="POST /api/content/generate-image",
    )
    mode_label ="Pro (Premium)" if mode == "pro" else "Free"
    remaining = await deduct_token(user)
    await record_usage(
        user, "image_generation", f"Generated {count} AI image(s)",
        f"{mode_label} · {prompt.strip()[:90]}",
    )

    if count == 1:
        image_bytes, mime_type, provider = images[0]
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"ai_generated_{provider}_{int(time.time() * 1000)}.{ext}"
        print(f"[CONTENT] AI image ready: {filename}, {len(image_bytes)} bytes, mime={mime_type}")
        return Response(
            content=image_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    # Multi-image: return a JSON list of base64-encoded images.
    import base64
    payload = {
        "images": [
            {"name": f"ai_{provider}_{int(time.time() * 1000)}_{i}.{'png' if 'png' in m else 'jpg'}",
             "mime": m,
             "data_b64": base64.b64encode(b).decode("ascii")}
            for i, (b, m, provider) in enumerate(images)
        ],
        "usage": usage_info,
    }
    print(f"[CONTENT] {count} AI images ready (JSON payload)")
    return JSONResponse(content=payload)


async def _upload_to_local(file_bytes: bytes, filename: str, media_type: str = "image", request: Request = None) -> str:
    """Save file to local disk and return the absolute public URL.

    Images are converted to JPG to satisfy Meta Graph API requirements.
    Videos are stored as-is.
    """
    ext = os.path.splitext(filename)[1] or ".jpg"
    if media_type == "image" and ext.lower() not in (".jpg", ".jpeg"):
        ext = ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / unique_name

    print(f"[LOCAL] Saving {filename} ({len(file_bytes)} bytes, type={media_type}) as {unique_name}")

    import media_rules

    size_error = media_rules.check_upload_size(len(file_bytes), media_type)
    if size_error:
        raise HTTPException(status_code=413, detail=size_error)

    # Images are ALWAYS re-encoded as real RGB JPEGs (EXIF rotation applied,
    # transparency flattened on white). Previously a failed conversion silently
    # stored PNG/WebP bytes under a .jpg name, which Meta rejects.
    if media_type == "image":
        try:
            file_bytes = media_rules.normalize_image_to_jpeg(file_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif os.path.splitext(filename)[1].lower() not in media_rules.VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported video format. Use MP4 or MOV.")

    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # CRITICAL: always persist bytes to disk in strict BINARY mode ("wb").
        # Previously the image branch converted via PIL but never wrote the file,
        # leaving static/uploads empty -> broken previews + Facebook "invalid image".
        with open(save_path, "wb") as f:
            f.write(file_bytes)

        if os.path.getsize(save_path) == 0:
            raise IOError(f"Zero-byte file written to {save_path}")

        local_url = f"/uploads/{unique_name}"
        absolute_url = str(request.base_url) + local_url.lstrip("/") if request else local_url
        print(f"[LOCAL] Saved {unique_name} ({os.path.getsize(save_path)} bytes) at {absolute_url}")
        return absolute_url
    except Exception as e:
        print(f"[LOCAL] Upload FAILED: {e}")
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


async def _upload_to_local_with_url(request: Request, file_bytes: bytes, filename: str, media_type: str = "image") -> str:
    """Save file to local disk and return the absolute public URL."""
    return await _upload_to_local(file_bytes, filename, media_type, request)


@router.post("/publish")
async def publish_content(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_token),
    content: str = Form(...),
    platforms: str = Form(...),
    media: Optional[UploadFile] = File(None),
):
    try:
        platform_list = json.loads(platforms)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Platforms must be a valid JSON array.")
    if not isinstance(platform_list, list) or not all(isinstance(p, str) for p in platform_list):
        raise HTTPException(status_code=400, detail="Platforms must be a valid JSON array of platform names.")
    platform_list = [p.strip().lower() for p in platform_list if p and p.strip()]
    if not platform_list:
        raise HTTPException(status_code=400, detail="Select at least one platform to publish.")
    print(f"[CONTENT] Publishing (sync) to: {platform_list}, has_media={media is not None}")

    # Cost guard: block before any publishing work when the post quota is full.
    await limits.check_available(user, "posts", 1)

    media_url = None
    media_type = None

    if media and media.filename:
        file_bytes = await media.read()
        media_type = _detect_media_type(media.filename, media.content_type or "")
        print(f"[CONTENT] Read media: {media.filename}, type={media_type}, size={len(file_bytes)} bytes")

        try:
            media_url = await _upload_to_local(file_bytes, media.filename, media_type, request)
        except HTTPException:
            raise  # validation errors (400/413) reach the user as-is
        except Exception as e:
            logger.error("Media upload failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to upload media: {str(e)}")

    results = {}
    own_accounts = await refresh_fb_pages_for_user(user["id"])

    for platform in platform_list:
        if platform not in own_accounts:
            results[platform] = {"status": "not_connected", "message": f"{platform} is not connected"}
            continue

        account = own_accounts[platform]
        access_token = account.get("access_token")

        if not access_token:
            results[platform] = {"status": "no_token", "message": f"No access token for {platform}"}
            continue

        try:
            if platform == "facebook":
                result = await _post_to_facebook(account, content, media_url, media_type)
            elif platform == "linkedin":
                result = await _post_to_linkedin(access_token, content, media_url, media_type, account.get("provider_account_id"))
            elif platform == "instagram":
                result = await _post_to_instagram(account, content, media_url, media_type)
            elif platform == "tiktok":
                # TikTok ONLY accepts videos — reject images before any upload.
                if media_type != "video":
                    result = {"status": "error", "message": "TikTok only accepts videos. Attach an MP4 video (image posts are not supported)."}
                else:
                    # Returns "processing" at once; the browser polls /tiktok/status.
                    result = await _start_tiktok_publish(user["id"], media_url, content, background_tasks)
            else:
                result = {"status": "unsupported", "message": f"Publishing to {platform} not implemented"}

            results[platform] = result
        except Exception as e:
            print(f"[CONTENT] Publish error for {platform}: {e}")
            logger.error("Publish Failed [%s]: %s", platform, e, exc_info=True)
            results[platform] = {"status": "error", "message": str(e)}

    print(f"[CONTENT] Publish complete: {json.dumps(results)}")
    logger.info(f"Publish complete: {json.dumps(results)}")
    # Remember which posts are ours, so comments on them can be routed back here.
    import published_posts
    await published_posts.record_results(user["id"], results)
    # A TikTok post that is "processing" was accepted by TikTok and counts as published.
    has_success = any(result.get("status") in ("success", "processing") for result in results.values() if isinstance(result, dict))
    remaining = await deduct_token(user) if has_success else remaining_tokens(user)
    usage_info = {}
    if has_success:
        usage_info = await limits.consume(
            user, "posts", 1,
            action="publish", endpoint="POST /api/content/publish",
        )
    return {"results": results, "tokens_left": remaining, "usage": usage_info}


async def _post_to_facebook(account: dict, content: str, media_url: str = None, media_type: str = None) -> dict:
    # Multi-page publishing: authorized FB Pages live in account["pages"] (one
    # entry per page, each with its own access_token). Post to EVERY page; if a
    # page fails, log the exact Meta error and keep publishing to the rest.
    pages = account.get("pages") or []
    if not pages:
        # Backward compatibility: connections saved before multi-page support
        # only carried the primary page's id + token.
        legacy_id = account.get("page_id")
        legacy_token = account.get("page_access_token")
        if legacy_id and legacy_token:
            pages = [{"id": legacy_id, "access_token": legacy_token}]

    if not pages:
        return {"status": "error", "message": "No Facebook Pages found. Reconnect your Facebook account."}

    published_ids = []
    errors = []

    for page in pages:
        page_id = page.get("id")
        page_token = page.get("access_token")
        if not page_id or not page_token:
            errors.append(f"page missing id/token: {json.dumps(page)}")
            continue

        try:
            # **FIX: Check if media_url is a localhost URL that Meta cannot reach**
            is_localhost = media_url and (
                media_url.startswith("http://localhost") or
                media_url.startswith("http://127.0.0.1") or
                media_url.startswith("https://localhost") or
                media_url.startswith("https://127.0.0.1")
            )

            import media_rules

            local_file_path = media_rules.local_path_for(media_url) if is_localhost else None
            if is_localhost and media_url and not local_file_path:
                errors.append(f"page {page_id}: the media file was not found on the server; please re-upload it")
                continue
            if local_file_path:
                problem = media_rules.check_for_platform("facebook", local_file_path, media_type)
                if problem:
                    return {"status": "error", "message": problem}
                filename = os.path.basename(local_file_path)
                # Stream the open file through httpx's multipart encoder. Videos go to
                # /videos (graph-video host, 'description'); images to /photos. The old
                # code sent EVERY local file to /photos as image/jpeg, so videos failed.
                with open(local_file_path, 'rb') as f:
                    async with httpx.AsyncClient(timeout=900.0) as client:
                        if media_type == "video":
                            size = os.path.getsize(local_file_path)
                            print(f"[CONTENT] {time.strftime('%H:%M:%S')} Facebook: uploading {media_rules.human(size)} "
                                  f"video to page {page_id} (graph-video, timeout 900s)", flush=True)
                            started = time.monotonic()
                            response = await client.post(
                                f"{GRAPH_VIDEO_BASE}/{page_id}/videos",
                                data={'description': content, 'access_token': page_token},
                                files={'source': (filename, f, media_rules.video_mime(filename))},
                            )
                            secs = time.monotonic() - started
                            print(f"[CONTENT] {time.strftime('%H:%M:%S')} Facebook: video upload answered HTTP "
                                  f"{response.status_code} after {secs:.0f}s "
                                  f"({size / 1048576 / max(secs, 0.001):.2f} MB/s average)", flush=True)
                        else:
                            response = await client.post(
                                f"{GRAPH_BASE}/{page_id}/photos",
                                data={'message': content, 'access_token': page_token},
                                files={'source': (filename, f, 'image/jpeg')},
                            )
            elif media_url and media_type == "image" and os.path.exists(media_url):
                # Existing local file path (not localhost URL)
                with open(media_url, 'rb') as f:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        files = {'source': ('image.jpg', f, 'image/jpeg')}
                        payload = {'message': content, 'access_token': page_token}
                        response = await client.post(
                            f"{GRAPH_BASE}/{page_id}/photos",
                            data=payload,
                            files=files,
                        )
            elif media_url and media_type == "video" and os.path.exists(media_url):
                # Existing local file path (not localhost URL)
                with open(media_url, 'rb') as f:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        files = {'source': ('video.mp4', f, 'video/mp4')}
                        payload = {'description': content, 'access_token': page_token}
                        response = await client.post(
                            f"{GRAPH_BASE}/{page_id}/videos",  # TODO: Meta's docs send video uploads to graph-video.facebook.com (GRAPH_VIDEO_BASE, like the local-file upload above); switch and test separately.
                            data=payload,
                            files=files,
                        )
            else:
                # If no local file or URL-based, use original logic
                async with httpx.AsyncClient(timeout=300.0) as client:
                    if media_url and media_type == "video":
                        response = await client.post(
                            f"{GRAPH_BASE}/{page_id}/videos",
                            data={"file_url": media_url, "description": content, "access_token": page_token},
                        )
                    elif media_url and media_type == "image":
                        response = await client.post(
                            f"{GRAPH_BASE}/{page_id}/photos",
                            data={"url": media_url, "caption": content, "access_token": page_token},
                        )
                    else:
                        response = await client.post(
                            f"{GRAPH_BASE}/{page_id}/feed",
                            data={"message": content, "access_token": page_token},
                        )
            data = response.json()
            print(f"[CONTENT] Facebook publish page {page_id} HTTP {response.status_code}: {json.dumps(data)}")

            # STRICT success check per page — only Meta-confirmed IDs count.
            if response.status_code != 200 or "error" in data or not data.get("id"):
                err = data.get("error", {})
                err_msg = err.get("message", data.get("message", "Unknown Facebook error"))
                print(f"[CONTENT] Facebook REJECTED for page {page_id} (HTTP {response.status_code}): {err_msg}")
                errors.append(f"page {page_id}: {err_msg}")
            else:
                published_ids.append(data["id"])
                print(f"[CONTENT] Facebook CONFIRMED live on page {page_id}: post_id={data['id']}")
        except Exception as e:
            print(f"[CONTENT] Facebook publish exception for page {page_id}: {e}")
            errors.append(f"page {page_id}: {str(e)}")

        # Light debounce between pages to stay friendly to Meta rate limits.
        await asyncio.sleep(1)

    if published_ids:
        summary = f"Published to {len(published_ids)} Facebook page(s)"
        if errors:
            summary += f"; {len(errors)} page(s) failed: {' | '.join(errors)}"
        result = {
            "status": "success",
            "post_id": ",".join(published_ids),
            "message": summary,
            "errors": errors,
        }
        print(f"[CONTENT] Facebook multi-page publish: {summary}")
        return result

    return {"status": "error", "message": "Facebook post failed on all pages: " + (" | ".join(errors) if errors else "unknown error")}


async def _post_to_linkedin(access_token: str, content: str, media_url: str = None, media_type: str = None, provider_account_id: str = None) -> dict:
    # "urn:li:person:me" is rejected by the LinkedIn API. We MUST use the user's
    # real profile id captured during OAuth; otherwise the post is never live.
    if not provider_account_id:
        return {"status": "error", "message": "LinkedIn profile ID missing. Reconnect your LinkedIn account."}

    author_urn = f"urn:li:person:{provider_account_id}"

    # **FIX: Check if media_url is a localhost URL that LinkedIn cannot reach**
    is_localhost = media_url and (
        media_url.startswith("http://localhost") or
        media_url.startswith("http://127.0.0.1") or
        media_url.startswith("https://localhost") or
        media_url.startswith("https://127.0.0.1")
    )

    file_bytes = None
    if is_localhost and media_url:
        # Extract just the filename from the localhost URL
        parsed_url = urlparse(media_url)
        filename = os.path.basename(parsed_url.path)
        # Dynamically find the backend root directory from __file__:
        # __file__ = backend/routers/content.py
        # current_dir = backend/routers
        # backend_dir = backend
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        local_file_path = os.path.join(backend_dir, "static", "uploads", filename)
        if os.path.exists(local_file_path):
            with open(local_file_path, 'rb') as f:
                file_bytes = f.read()
        else:
            # File not found, continue without bytes
            media_url = None
    elif media_url and os.path.exists(media_url):
        # Existing local file path (not localhost URL)
        with open(media_url, 'rb') as f:
            file_bytes = f.read()

    if file_bytes is not None:
        import media_rules

        problem = media_rules.check_for_platform("linkedin", media_rules.local_path_for(media_url), media_type)
        if problem:
            return {"status": "error", "message": problem}

    if media_url and media_type == "video" and file_bytes is not None:
        return await _linkedin_video_post(access_token, content, media_url, author_urn, file_bytes)

    if media_url and media_type == "image" and file_bytes is not None:
        return await _linkedin_image_post(access_token, content, media_url, author_urn, file_bytes)

    # Fallback: original URL-based logic (will likely fail from localhost, but handled)
    if media_url and media_type == "video":
        return await _linkedin_video_post(access_token, content, media_url, author_urn)

    if media_url and media_type == "image":
        return await _linkedin_image_post(access_token, content, media_url, author_urn)

    post_data = {
        "author": author_urn,
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

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"},
                json=post_data,
            )
            response_text = response.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn post request failed: {str(e)}"}

    if response.status_code != 201 or "id" not in response_text:
        return {"status": "error", "message": f"LinkedIn post rejected: {response_text}"}
    try:
        data = response.json()
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn post created but id unparsable: {response_text}"}
    return {"status": "success", "post_id": data["id"]}


async def _linkedin_video_post(access_token: str, content: str, video_url: str, author_urn: str, file_bytes: bytes = None) -> dict:
    """Strict LinkedIn v2 video publish — register, upload, publish.
    Every step fails hard (returning LinkedIn's literal response text)."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"}

    # STEP A — Register the video asset.
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            register_resp = await client.post(
                "https://api.linkedin.com/v2/assets?action=registerUpload",
                headers=headers,
                json={
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                        "owner": author_urn,
                        "serviceRelationships": [{
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }],
                    }
                },
            )
            register_text = register_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn video registerUpload request failed: {str(e)}"}

    if register_resp.status_code not in (200, 201) or "value" not in register_text:
        return {"status": "error", "message": f"LinkedIn video registerUpload rejected: {register_text}"}

    try:
        reg_data = register_resp.json()
        upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = reg_data["value"]["asset"]
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn video registerUpload payload malformed: {register_text}"}

    # STEP B — Download the video then PUT the raw bytes.
    if file_bytes:
        video_bytes = file_bytes
    else:
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                video_resp = await client.get(video_url, timeout=300.0)
                video_bytes = video_resp.content
        except Exception as e:
            return {"status": "error", "message": f"LinkedIn video download failed: {str(e)}"}
    if not video_bytes:
        return {"status": "error", "message": "LinkedIn video download returned no bytes"}

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            upload_resp = await client.put(
                upload_url,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"},
                content=video_bytes,
            )
            upload_text = upload_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn video upload request failed: {str(e)}"}
    print(f"[CONTENT] LinkedIn video upload status: {upload_resp.status_code}")

    if upload_resp.status_code not in (200, 201):
        return {"status": "error", "message": f"LinkedIn video upload rejected: {upload_text}"}

    # STEP C — Publish the UGC post with the exact asset URN.
    post_data = {
        "author": author_urn,
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
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            post_resp = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers=headers,
                json=post_data,
            )
            post_text = post_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn video post request failed: {str(e)}"}

    if post_resp.status_code != 201 or "id" not in post_text:
        return {"status": "error", "message": f"LinkedIn video post rejected: {post_text}"}
    try:
        return {"status": "success", "post_id": post_resp.json()["id"]}
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn video post created but id unparsable: {post_text}"}


async def _linkedin_image_post(access_token: str, content: str, image_url: str, author_urn: str, file_bytes: bytes = None) -> dict:
    """Strict LinkedIn v2 image publish — the exact 3-step sequence:
    register -> upload -> publish. Every step fails hard, returning LinkedIn's
    literal response text so the real rejection reason reaches the frontend."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"}

    # STEP A — Register the image asset (recipe feedshare-image), extract the
    # uploadMechanism URL and the asset URN.
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            register_resp = await client.post(
                "https://api.linkedin.com/v2/assets?action=registerUpload",
                headers=headers,
                json={
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                        "owner": author_urn,
                        "serviceRelationships": [{
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }],
                    }
                },
            )
            register_text = register_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn image registerUpload request failed: {str(e)}"}

    if register_resp.status_code not in (200, 201) or "value" not in register_text:
        return {"status": "error", "message": f"LinkedIn image registerUpload rejected: {register_text}"}

    try:
        reg_data = register_resp.json()
        upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = reg_data["value"]["asset"]
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn image registerUpload payload malformed: {register_text}"}

    # STEP B — Download the image and PUT the raw bytes (Bearer token included).
    # If we have local file bytes, use those directly; otherwise download from image_url.
    if file_bytes:
        image_bytes = file_bytes
    else:
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                image_resp = await client.get(image_url, timeout=300.0)
                image_bytes = image_resp.content
        except Exception as e:
            return {"status": "error", "message": f"LinkedIn image download failed: {str(e)}"}
    if not image_bytes:
        return {"status": "error", "message": "LinkedIn image download returned no bytes"}

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            upload_resp = await client.put(
                upload_url,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"},
                content=image_bytes,
            )
            upload_text = upload_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn image upload request failed: {str(e)}"}
    print(f"[CONTENT] LinkedIn image upload status: {upload_resp.status_code}")

    if upload_resp.status_code not in (200, 201):
        return {"status": "error", "message": f"LinkedIn image upload rejected: {upload_text}"}

    # STEP C — Publish the UGC post with the exact asset URN from Step A.
    post_data = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "media": asset_urn,
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            post_resp = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers=headers,
                json=post_data,
            )
            post_text = post_resp.text
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn image post request failed: {str(e)}"}

    if post_resp.status_code != 201 or "id" not in post_text:
        return {"status": "error", "message": f"LinkedIn image post rejected: {post_text}"}
    try:
        return {"status": "success", "post_id": post_resp.json()["id"]}
    except Exception as e:
        return {"status": "error", "message": f"LinkedIn image post created but id unparsable: {post_text}"}


async def _post_to_instagram(account: dict, content: str, media_url: str = None, media_type: str = None) -> dict:
    # Two-step container -> media_publish flow, tunnel-free media upload and
    # mapped Meta errors live in instagram_publisher; kept here for existing imports.
    import instagram_publisher

    return await instagram_publisher.publish(account, content, media_url, media_type)


# ---------------------------------------------------------------------------
# TikTok Content Posting API (video only)
# ---------------------------------------------------------------------------

from tiktok_client import SUPPORTED_VIDEO_EXTENSIONS as TIKTOK_VIDEO_EXTENSIONS


def _resolve_local_media_path(media_url: str) -> str:
    """Resolve a localhost URL (or direct path) to the on-disk upload file.

    The lookup is anchored on __file__ (backend/routers -> backend/static/uploads)
    so it never depends on os.getcwd(), which changes with how the server is
    launched.

    Any http(s) URL under /uploads/ is one of our own uploads, whatever host
    and scheme the request arrived with: localhost, a tunnel (whose
    X-Forwarded-Proto makes it https://127.0.0.1:8000/...) or the production
    domain. Only the basename is used, so the path cannot leave the folder.
    """
    parsed = urlparse(media_url)
    if parsed.scheme in ("http", "https") and parsed.path.startswith("/uploads/"):
        filename = os.path.basename(parsed.path)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        return os.path.join(backend_dir, "static", "uploads", filename)
    return media_url


def _privacy_note(privacy_level: str) -> str:
    if not privacy_level or privacy_level == "PUBLIC_TO_EVERYONE":
        return ""
    return f" (visibility: {privacy_level}, as allowed by TikTok for this app)"


async def _prepare_tiktok_post(user_id: str, video_path: str):
    """Checks shared by every TikTok post. Returns ``(context, None)`` or ``(None, error_result)``.

    Validates the account and the video file, refreshes the 24h access token
    if needed and asks creator_info which privacy level is allowed.
    `video_path` may be an upload URL from this server or a direct file path.
    """
    from routers.social import save_user_account
    from tiktok_client import TikTokError, tiktok

    account = dict(get_user_accounts(user_id).get("tiktok") or {})
    if not account.get("access_token"):
        return None, {"status": "error", "message": "TikTok is not connected. Reconnect your TikTok account."}
    if not video_path:
        return None, {"status": "error", "message": "TikTok requires a video. Attach an MP4 file."}

    local_path = _resolve_local_media_path(video_path)
    if not os.path.exists(local_path):
        return None, {"status": "error", "message": "Video file not found on the server. Please re-upload and try again."}

    ext = os.path.splitext(local_path)[1].lower()
    if ext not in TIKTOK_VIDEO_EXTENSIONS:
        return None, {"status": "error", "message": f"TikTok only accepts videos ({', '.join(TIKTOK_VIDEO_EXTENSIONS)}). Attach a video file."}

    if os.path.getsize(local_path) == 0:
        return None, {"status": "error", "message": "The video file is empty."}

    try:
        # Access tokens expire after 24h. Refresh with the stored refresh token
        # and persist the new pair so later posts keep working.
        if await tiktok.refresh_if_needed(account):
            save_user_account(user_id, "tiktok", account)
            print("[CONTENT] TikTok access token refreshed")
    except TikTokError as e:
        print(f"[CONTENT] TikTok token refresh failed: {e}")
        return None, {"status": "error", "message": str(e)}
    except Exception as e:
        print(f"[CONTENT] TikTok token refresh error: {e}")
        return None, {"status": "error", "message": f"TikTok request failed: {e}"}

    # TikTok requires a creator_info query before every Direct Post. It also
    # tells us whether PUBLIC_TO_EVERYONE is allowed (unaudited apps may only
    # post SELF_ONLY).
    privacy_level = "PUBLIC_TO_EVERYONE"
    try:
        creator = await tiktok.creator_info(account["access_token"])
        privacy_level = tiktok.choose_privacy_level(creator, privacy_level)
    except Exception as e:
        print(f"[CONTENT] TikTok creator_info failed (continuing with {privacy_level}): {e}")

    return {"access_token": account["access_token"], "local_path": local_path, "privacy_level": privacy_level}, None


async def _post_to_tiktok(user_id: str, video_path: str, text_caption: str) -> dict:
    """Publish a video and WAIT for TikTok's final result.

    Used by scheduled posts, which already run in the background. The Create
    page uses `_start_tiktok_publish()` instead, which returns at once.
    """
    from tiktok_client import TikTokError, tiktok

    ctx, error = await _prepare_tiktok_post(user_id, video_path)
    if error:
        return error
    try:
        result = await tiktok.publish_and_wait(
            ctx["access_token"],
            ctx["local_path"],
            title=(text_caption or "").strip(),
            privacy_level=ctx["privacy_level"],
            poll_seconds=3.0,
            max_polls=60,
        )
        return {"status": "success", "post_id": result["publish_id"],
                "message": f"TikTok video published{_privacy_note(ctx['privacy_level'])}."}
    except TikTokError as e:
        print(f"[CONTENT] TikTok publish error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        print(f"[CONTENT] TikTok publish unexpected error: {e}")
        return {"status": "error", "message": f"TikTok request failed: {str(e)}"}


# Interactive TikTok posts (Create page). Uploading the bytes and TikTok's own
# processing can take minutes, longer than a browser should wait and longer
# than Cloudflare tunnels allow (they cut responses at 100s). So the publish
# request only registers the post with TikTok and returns "processing"; the
# upload runs as a background task and the browser polls
# GET /api/content/tiktok/status/{publish_id}.
#
# TikTok's publish_id is the job id, so status still works from TikTok's side
# after a backend restart. This map only holds what TikTok cannot know: our own
# upload stage and its errors, and who owns the post.
_tiktok_jobs: dict = {}
TIKTOK_UPLOAD_TIMEOUT_SECONDS = 30 * 60  # TikTok's upload_url is valid for 1 hour
TIKTOK_JOB_MAX_AGE_SECONDS = 2 * 3600


def _prune_tiktok_jobs() -> None:
    cutoff = time.time() - TIKTOK_JOB_MAX_AGE_SECONDS
    for publish_id in [p for p, job in _tiktok_jobs.items() if job["created"] < cutoff]:
        _tiktok_jobs.pop(publish_id, None)


async def _start_tiktok_publish(user_id: str, video_path: str, text_caption: str, background_tasks: BackgroundTasks) -> dict:
    """Register the post with TikTok (fast) and upload the video in the background."""
    from tiktok_client import TikTokError, tiktok

    ctx, error = await _prepare_tiktok_post(user_id, video_path)
    if error:
        return error
    try:
        upload = await tiktok.start_video_upload(
            ctx["access_token"],
            ctx["local_path"],
            title=(text_caption or "").strip(),
            privacy_level=ctx["privacy_level"],
        )
    except TikTokError as e:
        print(f"[CONTENT] TikTok publish init error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        print(f"[CONTENT] TikTok publish init unexpected error: {e}")
        return {"status": "error", "message": f"TikTok request failed: {str(e)}"}

    publish_id = upload["publish_id"]
    _prune_tiktok_jobs()
    _tiktok_jobs[publish_id] = {
        "user_id": user_id,
        "stage": "uploading",
        "error": None,
        "privacy_level": ctx["privacy_level"],
        "created": time.time(),
    }
    background_tasks.add_task(_upload_tiktok_video, publish_id, upload)
    print(f"[CONTENT] TikTok post {publish_id} registered; uploading {upload['video_size']} bytes in the background")
    return {"status": "processing", "publish_id": publish_id, "message": "Uploading your video to TikTok…"}


async def _upload_tiktok_video(publish_id: str, upload: dict) -> None:
    """Background task: send the video bytes, recording failures for the status endpoint."""
    from tiktok_client import TikTokError, tiktok

    job = _tiktok_jobs.get(publish_id) or {}
    started = time.monotonic()
    try:
        await asyncio.wait_for(tiktok.upload_video(upload), timeout=TIKTOK_UPLOAD_TIMEOUT_SECONDS)
        job["stage"] = "processing"
        print(f"[CONTENT] TikTok post {publish_id}: upload finished in {time.monotonic() - started:.0f}s; TikTok is processing it")
    except asyncio.TimeoutError:
        job["error"] = (f"Uploading the video to TikTok took longer than {TIKTOK_UPLOAD_TIMEOUT_SECONDS // 60} "
                        "minutes and was stopped. Try again, or use a smaller video.")
    except TikTokError as e:
        job["error"] = str(e)
    except Exception as e:
        job["error"] = f"TikTok upload failed: {e}"
    if job.get("error"):
        print(f"[CONTENT] TikTok post {publish_id}: upload failed: {job['error']}")


@router.get("/tiktok/status/{publish_id}")
async def tiktok_publish_status(publish_id: str, user: dict = Depends(get_current_user)):
    """Progress of a TikTok post started by POST /publish; polled by the browser.

    Returns {"status": "processing" | "success" | "error", "stage", "message"}.
    Never spends a token: the post was counted when it started.
    """
    from routers.social import save_user_account
    from tiktok_client import TikTokError, tiktok

    job = _tiktok_jobs.get(publish_id)
    if job and job["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Unknown TikTok post.")
    if job and job.get("error"):
        _tiktok_jobs.pop(publish_id, None)
        return {"status": "error", "stage": "UPLOAD_FAILED", "message": job["error"]}
    if job and job["stage"] == "uploading":
        return {"status": "processing", "stage": "UPLOADING", "message": "Uploading your video to TikTok…"}

    account = dict(get_user_accounts(user["id"]).get("tiktok") or {})
    if not account.get("access_token"):
        return {"status": "error", "stage": "NOT_CONNECTED", "message": "TikTok is not connected. Reconnect your TikTok account."}
    try:
        if await tiktok.refresh_if_needed(account):
            save_user_account(user["id"], "tiktok", account)
        body = await tiktok.publish_status(account["access_token"], publish_id)
    except TikTokError as e:
        if e.status_code and 400 <= e.status_code < 500:
            # TikTok rejected the question itself (unknown id, revoked token):
            # asking again will not help.
            _tiktok_jobs.pop(publish_id, None)
            print(f"[CONTENT] TikTok status for {publish_id} rejected: {e}")
            return {"status": "error", "stage": "STATUS_REJECTED", "message": str(e)}
        print(f"[CONTENT] TikTok status for {publish_id} unavailable (will retry): {e}")
        return {"status": "processing", "stage": "STATUS_UNAVAILABLE", "message": "Checking TikTok's progress…"}
    except Exception as e:
        # Network trouble is not a failed post; the browser simply asks again.
        print(f"[CONTENT] TikTok status for {publish_id} unavailable (will retry): {e}")
        return {"status": "processing", "stage": "STATUS_UNAVAILABLE", "message": "Checking TikTok's progress…"}

    outcome, tiktok_status, message = tiktok.interpret_publish_status(body)
    if outcome == "success" and job:
        message = message.rstrip(".") + _privacy_note(job["privacy_level"]) + "."
    if outcome != "processing":
        _tiktok_jobs.pop(publish_id, None)
        print(f"[CONTENT] TikTok post {publish_id}: {tiktok_status} -> {outcome}")
    return {"status": outcome, "stage": tiktok_status, "message": message}
