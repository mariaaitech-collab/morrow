from fastapi import APIRouter, HTTPException, Form, Request
import httpx
import json
import time
import logging
from urllib.parse import urlparse

from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_TEXT_MODEL, TAVILY_API_KEY
from routers.content import PLATFORM_DOMAINS, _tavily_search_platform

router = APIRouter(prefix="/api", tags=["strategy"])

logger = logging.getLogger("brandora")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _fh = logging.FileHandler("brandora.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_fh)
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(_sh)
logger.propagate = False


def _url_key(url: str):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").replace("www.", "")
        return f"{host}{parsed.path}{parsed.query}"
    except Exception:
        return None


def _pick_top_three_per_platform(buckets, per_platform=3):
    """Pick up to `per_platform` distinct real results per platform bucket."""
    seen = set()
    selected = []
    for bucket in buckets:
        if not bucket:
            continue
        platform = bucket[0].get("platform")
        chosen = []
        for item in bucket:
            if len(chosen) >= per_platform:
                break
            key = _url_key(item.get("url") or "")
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            chosen.append(item)
        selected.append({"platform": platform, "results": chosen})
    return selected


async def _live_search_competitors(topic: str, platforms):
    active = [p for p in platforms if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    import asyncio  # noqa: E402

    buckets = await asyncio.gather(*[_tavily_search_platform(topic, p) for p in active])
    grouped = _pick_top_three_per_platform(buckets, per_platform=3)

    flat = [item for g in grouped for item in g["results"]]
    if not flat:
        raise HTTPException(status_code=422, detail="Live search returned no social results for this topic. Try a more specific query.")

    return flat, grouped, {"provider": "tavily", "platforms": active, "total_raw_results": sum(len(b) for b in buckets)}


def _build_strategy_prompt(topic, flat_competitors, user_content):
    listing = "\n".join(
        f'{i + 1}. [{c["platform"]}] "{c.get("title") or ""}" | snippet: {c.get("snippet") or "(no snippet)"} | url: {c.get("url") or ""} | published: {c.get("published_date") or "unknown"}'
        for i, c in enumerate(flat_competitors)
    )

    user_block = ""
    if user_content and user_content.strip():
        user_block = (
            "\n\nTHE USER'S OWN GENERATED CONTENT (lease analyze this caption and then improve on it):\n"
            + user_content.strip()
        )

    header = (
        f'You are the Chief Strategist of an elite digital marketing SaaS. Below are real, currently-ranking creators/posts '
        f'found LIVE on LinkedIn, Instagram and Facebook for the topic "{topic}" — with official URLs and content snippets.{user_block}\n\n'
        f"REAL RESULTS FOUND (from live web search):\n{listing}\n\n"
        "TASK: Produce a ruthless, data-driven competitive teardown plus a step-by-step viral deployment roadmap that lets "
        "the user outperform these exact posts with their own generated caption.\n\n"
    )

    schema = '''Return STRICT JSON only (no markdown, no code fences, no commentary). Match this exact schema:

{
  "trending_competitors": [
    {
      "name": "creator or brand name",
      "platform": "linkedin | instagram | facebook",
      "viral_hook": "the exact hook/title that made it viral, one punchy line",
      "profile_link": "real URL from the results above if available, otherwise a plausible profile URL like https://www.<platform>.com/<handle>"
    }
  ],
  "content_analysis": {
    "strengths": [
      "3-5 concise bullets: what the user's generated caption already does well, with specific reference to its opening hook and call-to-action"
    ],
    "specific_improvements": [
      "4-6 concise, concrete, rewrite-ready improvements: exactly how to make the hook sharper, add curiosity gaps, tighten the CTA, improve format, and boost shareability"
    ]
  },
  "competitor_weaknesses": [
    {
      "weakness": "a concrete gap or mistake the viral competitors are making (e.g. weak CTA, ignoring comments, no follow-up post, overlong caption, no engagement bait)",
      "why_you_win": "how the user's improved post exploits this exact gap"
    }
  ],
  "viral_roadmap": [
    {
      "day": "Day 1",
      "action": "the single concrete task to execute that day",
      "platform": "where to run it (linkedin/instagram/facebook)",
      "expected_outcome": "the specific result this action should produce"
    }
  ]
}'''

    rules = f'''
RULES:
- trending_competitors MUST contain EXACTLY 9 entries: 3 LinkedIn, 3 Instagram, 3 Facebook. Use the REAL results provided whenever possible (copy their URL exactly). If fewer than 3 real results exist for a platform, fill the remaining slots with highly realistic, believable trending competitor profiles — do NOT reuse a URL already used.
- Each viral_hook must be a realistic, hook-lifting one-liner based on the snippet or the creator's likely style.
- content_analysis.strengths and content_analysis.specific_improvements must reference the user's actual generated caption, never generic boilerplate.
- competitor_weaknesses is the BONUS teardown: name real mistakes these viral competitors make (weak CTAs, ignoring comments, no repurposing, low-engagement hooks) and give a sharp counter.
- viral_roadmap must be step-by-step and anchored on real calendar days, e.g. Day 1, Day 2, Day 3, Day 5, Day 7 — each with one executable action per platform and a measurable expected outcome.
- Never invent JSON keys outside this schema. Never wrap the response in markdown.'''

    return header + schema + rules


async def _analyze_strategy(topic, flat_competitors, user_content):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    prompt = _build_strategy_prompt(topic, flat_competitors, user_content)

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
                        {"role": "system", "content": "You are the Chief Strategist of an elite digital marketing SaaS. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 8192,
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
        return json.loads(cleaned), GEMINI_TEXT_MODEL
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid strategy. Try again.")
        try:
            return json.loads(cleaned[start : end + 1]), GEMINI_TEXT_MODEL
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid strategy. Try again.")


@router.post("/strategy")
async def elite_strategy(
    request: Request,
    topic: str = Form(...),
    platforms: str = Form('["linkedin","instagram","facebook"]'),
    content: str = Form(""),
):
    started = time.time()
    print(f"[STRATEGY] Elite strategy: topic='{topic[:80]}', content_len={len(content)}")

    if not topic.strip() or len(topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic is required and must be at least 3 characters.")

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')

    flat, grouped, search_meta = await _live_search_competitors(topic.strip(), platform_list)
    analysis, model = await _analyze_strategy(topic.strip(), flat, content)

    result = {
        "topic": topic.strip(),
        "trending_competitors": analysis.get("trending_competitors", []),
        "content_analysis": analysis.get("content_analysis", {}),
        "competitor_weaknesses": analysis.get("competitor_weaknesses", []),
        "viral_roadmap": analysis.get("viral_roadmap", []),
        "providers": {"search": "tavily", "analysis": {"provider": "gemini", "model": model}},
        "search_meta": search_meta,
        "generated_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
    }

    print(
        f"[STRATEGY] Elite strategy done in {result['latency_ms']}ms "
        f"({len(analysis.get('trending_competitors', []))} competitors, {len(analysis.get('viral_roadmap', []))} roadmap steps)"
    )
    logger.info(
        "Elite strategy done: %s competitors, %s roadmap steps, %sms",
        len(analysis.get("trending_competitors", [])),
        len(analysis.get("viral_roadmap", [])),
        result["latency_ms"],
    )

    from usage import get_optional_user, record_usage

    user = await get_optional_user(request)
    await record_usage(
        user,
        "competitive_analysis",
        "Ran a Competitive Analysis",
        f"Topic: {topic.strip()[:90]}",
    )
    return result