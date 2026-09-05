from fastapi import APIRouter, HTTPException, Form, Request
import httpx
import json
import time
import logging
from urllib.parse import urlparse

from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_TEXT_MODEL, TAVILY_API_KEY
from routers.content import PLATFORM_DOMAINS, _tavily_search_platform, _language_rule

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


async def _live_search_competitors(topic: str, platforms, location: str = ""):
    active = [p for p in platforms if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    import asyncio  # noqa: E402

    buckets = await asyncio.gather(*[_tavily_search_platform(topic, p, location) for p in active])
    grouped = _pick_top_three_per_platform(buckets, per_platform=3)

    flat = [item for g in grouped for item in g["results"]]
    if not flat:
        raise HTTPException(status_code=422, detail="Live search returned no social results for this topic. Try a more specific query.")

    return flat, grouped, {"provider": "tavily", "platforms": active, "total_raw_results": sum(len(b) for b in buckets)}


def _build_strategy_prompt(topic, flat_competitors, user_content, language=""):
    lang_rule = _language_rule(language)

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
        f'{lang_rule}'
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


async def _analyze_strategy(topic, flat_competitors, user_content, language=""):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    prompt = _build_strategy_prompt(topic, flat_competitors, user_content, language)

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
    language: str = Form(""),
):
    started = time.time()
    print(f"[STRATEGY] Elite strategy: topic='{topic[:80]}', content_len={len(content)}, language='{language}'")

    if not topic.strip() or len(topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic is required and must be at least 3 characters.")

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')

    flat, grouped, search_meta = await _live_search_competitors(topic.strip(), platform_list)
    analysis, model = await _analyze_strategy(topic.strip(), flat, content, language)

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


# ---------------------------------------------------------------------------
# Brand-Aware Market Intelligence (Business Profile -> Live insights)
# ---------------------------------------------------------------------------


def _build_market_prompt(profile: dict, flat_competitors: list, language: str = ""):
    lang_rule = _language_rule(language)
    location = (profile.get("location") or "").strip()

    listing = "\n".join(
        f'{i + 1}. [{c["platform"]}] "{c.get("title") or ""}" | snippet: {c.get("snippet") or "(no snippet)"} | url: {c.get("url") or ""}'
        for i, c in enumerate(flat_competitors)
    )

    header = (
        f'{lang_rule}'
        "You are the Head of Market Intelligence at an elite digital marketing agency. "
        "Below are REAL, currently-ranking posts/creators found LIVE on LinkedIn, Instagram and Facebook "
        "for the user's brand space, with official URLs and content snippets.\n\n"
        f"USER'S BRAND PROFILE:\n"
        f'- Brand niche: {profile.get("niche") or "(not provided)"}\n'
        f'- Target audience: {profile.get("audience") or "(not provided)"}\n'
        f'- Business type: {profile.get("business_type") or "(not provided)"}\n'
        f'- Core offerings: {profile.get("offerings") or "(not provided)"}\n'
        f'- Geographic market: {location or "(worldwide)"}\n\n'
        f"REAL RESULTS FOUND (from live web search):\n{listing}\n\n"
        "TASK: Produce a data-driven market intelligence brief + a per-platform outpace plan that lets the user "
        "win this LOCAL market with THEIR exact brand profile.\n\n"
    )

    schema = '''Return STRICT JSON only (no markdown, no code fences, no commentary). Match this exact schema:

{
  "market_overview": "2-3 sentences: what is actually happening in this local market right now, based ONLY on the live results",
  "market_leaders": [
    {
      "name": "exact real competitor brand/creator name from the results",
      "platform": "linkedin | instagram | facebook",
      "link": "real URL copied exactly from the results",
      "positioning": "what they are known for / their angle in this local market",
      "winning_move": "exactly what they are doing RIGHT on that platform",
      "gap": "one concrete weakness or missed opportunity you see"
    }
  ],
  "positioning_advice": [
    "4-6 razor-sharp positioning statements tailored to the user's niche, audience, business type, offerings and location that let them stand out from these leaders"
  ],
  "platform_tactics": {
    "facebook": ["3-4 concrete tactics the user should run on Facebook in this local market"],
    "instagram": ["3-4 concrete tactics the user should run on Instagram in this local market"],
    "linkedin": ["3-4 concrete tactics the user should run on LinkedIn in this local market"]
  },
  "quick_wins": [
    "3-5 immediate, executable moves (max 1 sentence each)"
  ]
}'''

    rules = f'''
RULES:
- market_leaders MUST contain EXACTLY 3 entries: exactly 1 LinkedIn competitor, exactly 1 Instagram competitor and exactly 1 Facebook competitor. Each must be a REAL, currently-active competitor in the user's local market ({location or 'worldwide'}) drawn from the live results above — copy each URL exactly. Never invent brands or URLs.
- Choose the single strongest / most relevant real competitor per platform. If no real result exists for a platform from the search, use the closest real result found and be explicit that it is the most relevant one found.
- Every tactical and positioning bullet must be tied to the user's brand profile (niche/audience/offerings) AND their location, never generic boilerplate.
- platform_tactics must contain all three keys (facebook, instagram, linkedin) even if a platform has no results.
- Never invent JSON keys outside this schema. Never wrap the response in markdown.'''

    return header + schema + rules


async def _analyze_market(profile: dict, flat_competitors: list, language: str = ""):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    prompt = _build_market_prompt(profile, flat_competitors, language)

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
                        {"role": "system", "content": "You are the Head of Market Intelligence at an elite digital marketing agency. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 8192,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Gemini market analysis timed out. Try again.")

    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Gemini quota or rate limit exceeded. Try again later.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Gemini market analysis error: {resp.text[:500]}")

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
            raise HTTPException(status_code=502, detail="Gemini returned an invalid market brief. Try again.")
        try:
            return json.loads(cleaned[start : end + 1]), GEMINI_TEXT_MODEL
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid market brief. Try again.")


@router.post("/market/competitor-insights")
async def competitor_insights(
    request: Request,
    brand_niche: str = Form(...),
    target_audience: str = Form(""),
    business_type: str = Form(""),
    core_offerings: str = Form(""),
    location: str = Form(""),
    topic: str = Form(""),
    platforms: str = Form('["linkedin","instagram","facebook"]'),
    language: str = Form(""),
):
    started = time.time()
    print(
        f"[STRATEGY] Market insights: niche='{brand_niche[:80]}', audience='{target_audience[:60]}', "
        f"business_type='{business_type[:60]}', offerings='{core_offerings[:60]}', "
        f"location='{location[:60]}', topic='{topic[:80]}'"
    )

    if not brand_niche.strip() or len(brand_niche.strip()) < 3:
        raise HTTPException(status_code=400, detail="Brand niche is required and must be at least 3 characters.")

    profile = {
        "niche": brand_niche.strip(),
        "audience": target_audience.strip(),
        "business_type": business_type.strip(),
        "offerings": core_offerings.strip(),
        "location": location.strip(),
    }

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')

    # Market search subject: an explicit topic wins, otherwise synthesize one
    # from the brand profile so Tavily searches something meaningful. Location
    # is appended to scope results to the user's local market.
    query = topic.strip()
    if not query:
        query = f"{brand_niche.strip()} {' ' + core_offerings.strip() if core_offerings.strip() else ''} marketing".strip()
        if location.strip():
            query = f"{query} {location.strip()}"
        if not query or len(query) < 3:
            raise HTTPException(status_code=400, detail="Provide a topic or a richer brand niche so market search can run.")

    flat, grouped, search_meta = await _live_search_competitors(query, platform_list, location=location)
    analysis, model = await _analyze_market(profile, flat, language)

    # Hard guarantee: exactly 3 competitor profiles, one per platform.
    leaders = analysis.get("market_leaders", []) or []
    leaders = [l for l in leaders if isinstance(l, dict)]
    by_platform = {}
    for l in leaders:
        p = (l.get("platform") or "").strip().lower()
        if p not in ("linkedin", "instagram", "facebook"):
            continue
        by_platform.setdefault(p, l)
    ordered = [by_platform.get(p) for p in ("linkedin", "instagram", "facebook")]
    leaders = [l for l in ordered if l is not None]

    result = {
        "brand_profile": profile,
        "query": query,
        "market_overview": analysis.get("market_overview", ""),
        "market_leaders": leaders,
        "positioning_advice": analysis.get("positioning_advice", []),
        "platform_tactics": analysis.get("platform_tactics", {
            "facebook": [], "instagram": [], "linkedin": [],
        }),
        "quick_wins": analysis.get("quick_wins", []),
        "providers": {"search": "tavily", "analysis": {"provider": "gemini", "model": model}},
        "search_meta": search_meta,
        "generated_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
    }

    print(
        f"[STRATEGY] Market insights done in {result['latency_ms']}ms "
        f"({len(result['market_leaders'])} leaders across {len(platform_list)} platform search(es))"
    )
    logger.info(
        "Market insights done: %s leaders, %sms",
        len(result["market_leaders"]),
        result["latency_ms"],
    )

    from usage import get_optional_user, record_usage

    user = await get_optional_user(request)
    await record_usage(
        user,
        "market_insights",
        "Ran a Market Intelligence Scan",
        f"Brand: {brand_niche.strip()[:90]}",
    )
    return result