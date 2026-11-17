from fastapi import APIRouter, Depends, HTTPException, Form, Request
import httpx
import json
import time
import logging
import re
import unicodedata
from urllib.parse import quote_plus, urlparse

from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_TEXT_MODEL, TAVILY_API_KEY
import limits
from routers.content import PLATFORM_DOMAINS, _tavily_search_platform, _language_rule, _cached_at_str
from deps import get_current_user
from usage import get_optional_user, record_usage

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


_MARKET_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "into",
    "is", "of", "on", "or", "the", "to", "with", "your", "best", "new",
    "ideas", "idea", "post", "posts", "content", "marketing", "brand",
}


def _market_topic_match(topic: str, item: dict):
    """Classify a live result using only the requested topic and its real text."""
    def normalize(value):
        ascii_text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()

    query = normalize(topic)
    terms = [word for word in query.split() if len(word) > 1 and word not in _MARKET_STOP_WORDS]
    if not terms:
        terms = [word for word in query.split() if len(word) > 1]
    title = normalize(item.get("title"))
    snippet = normalize(item.get("snippet"))
    text = f"{title} {snippet}".strip()
    if not terms or not text:
        return None

    matched = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text)]
    if not matched:
        return None

    full_phrase = bool(query and re.search(rf"\b{re.escape(query)}\b", text))
    if full_phrase or len(matched) == len(terms):
        match_type = "exact"
    elif len(terms) <= 2 or (len(matched) >= 2 and len(matched) / len(terms) >= 0.5):
        match_type = "related"
    else:
        return None

    query = quote_plus(topic.strip())
    search_urls = {
        "linkedin": f"https://www.linkedin.com/search/results/content/?keywords={query}",
        "instagram": f"https://www.instagram.com/explore/search/keyword/?q={query}",
        "facebook": f"https://www.facebook.com/search/posts/?q={query}",
    }
    return {**item, "match_type": match_type, "matched_terms": matched, "search_url": search_urls.get(item.get("platform"))}


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
    relevant_buckets = []
    for bucket in buckets:
        matched_items = [matched for item in bucket if (matched := _market_topic_match(topic, item))]
        matched_items.sort(key=lambda item: (item.get("match_type") != "exact", -(item.get("score") or 0)))
        relevant_buckets.append(matched_items)
    grouped = _pick_top_three_per_platform(relevant_buckets, per_platform=3)

    flat = [item for g in grouped for item in g["results"]]
    if not flat:
        raise HTTPException(status_code=422, detail="No posts matched this topic closely enough. Try a shorter or more specific topic.")

    return flat, grouped, {
        "provider": "tavily",
        "platforms": active,
        "topic": topic,
        "total_raw_results": sum(len(b) for b in buckets),
        "relevant_results": len(flat),
        "exact_results": sum(1 for item in flat if item["match_type"] == "exact"),
        "related_results": sum(1 for item in flat if item["match_type"] == "related"),
    }


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
      "profile_link": "exact URL copied from this matching live result",
      "post_title": "exact title from the matching live result",
      "post_snippet": "short excerpt from the matching live result",
      "match_type": "exact | related",
      "matched_terms": ["topic words found in the result"]
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
- Use only live results listed above that were checked against the topic. Include at most one card for each real result, and never invent a creator, post, title, hook, or URL. Fewer than nine cards is correct when fewer relevant results exist.
- Copy the result title into post_title and the result excerpt into post_snippet. Keep the match_type and matched_terms from that same result. A related result must remain labeled related.
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
    user: dict = Depends(get_current_user),
    topic: str = Form(...),
    platforms: str = Form('["linkedin","instagram","facebook"]'),
    content: str = Form(""),
    language: str = Form(""),
):
    started = time.time()
    print(f"[STRATEGY] Elite strategy: topic='{topic[:80]}', content_len={len(content)}, language='{language}'")

    if not topic.strip() or len(topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Topic is required and must be at least 3 characters.")

    limits.validate_input_len(topic, "Topic")

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')
    active = [p for p in platform_list if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    cache_key = limits.make_cache_key(
        ["strategy-v2", topic.strip(), sorted(active), content, language]
    )
    cached = await limits.get_cached_result(cache_key)
    if cached:
        result = cached["payload"]
        result["cache_note"] = f'Showing your cached strategy from {_cached_at_str(cached["cached_at"])}.'
        print(f"[STRATEGY] Served cached strategy for topic='{topic[:60]}'")
        return result

    try:
        usage_info = await limits.consume(
            user, "analysis", len(active),
            action="strategy_analysis", endpoint="POST /api/strategy",
        )
    except HTTPException as e:
        if e.status_code == 402:
            stale = await limits.get_expired_result(cache_key)
            if stale:
                result = stale["payload"]
                result["cache_note"] = f'Showing your last strategy from {_cached_at_str(stale["cached_at"])}.'
                result["usage_warning"] = e.detail
                return result
        raise

    flat, grouped, search_meta = await _live_search_competitors(topic.strip(), active)
    analysis, model = await _analyze_strategy(topic.strip(), flat, content, language)

    source_by_url = {_url_key(item.get("url") or ""): item for item in flat if _url_key(item.get("url") or "")}
    model_by_source = {}
    for candidate in analysis.get("trending_competitors", []) or []:
        if not isinstance(candidate, dict):
            continue
        source = source_by_url.get(_url_key(candidate.get("profile_link") or ""))
        if source and candidate.get("platform") == source.get("platform"):
            model_by_source[_url_key(source.get("url") or "")] = candidate

    verified_competitors = []
    for source in flat:
        model_card = model_by_source.get(_url_key(source.get("url") or ""), {})
        verified_competitors.append({
            "name": model_card.get("name") or source.get("title") or PLATFORM_DOMAINS[source["platform"]]["label"],
            "platform": source["platform"],
            "viral_hook": model_card.get("viral_hook") or source.get("title") or "",
            "profile_link": source.get("search_url") or source.get("url"),
            "search_url": source.get("search_url"),
            "source_url": source.get("url"),
            "post_title": source.get("title") or "",
            "post_snippet": source.get("snippet") or "",
            "match_type": source.get("match_type"),
            "matched_terms": source.get("matched_terms") or [],
        })

    result = {
        "topic": topic.strip(),
        "trending_competitors": verified_competitors,
        "content_analysis": analysis.get("content_analysis", {}),
        "competitor_weaknesses": analysis.get("competitor_weaknesses", []),
        "viral_roadmap": analysis.get("viral_roadmap", []),
        "providers": {"search": "tavily", "analysis": {"provider": "gemini", "model": model}},
        "search_meta": search_meta,
        "generated_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
        "usage": usage_info,
    }

    try:
        await limits.put_cached_result(cache_key, result)
    except Exception as e:
        logger.warning("Failed to cache strategy result: %s", e)

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
        f'{i + 1}. [{c["platform"]}] [{c.get("match_type", "related")} match on {", ".join(c.get("matched_terms") or [])}] '
        f'"{c.get("title") or ""}" | snippet: {c.get("snippet") or "(no snippet)"} | url: {c.get("url") or ""}'
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
        f'- User topic: {profile.get("topic") or profile.get("niche") or "(not provided)"}\n\n'
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
      "post_title": "exact title copied from the matching live result",
      "post_snippet": "short excerpt copied from that matching live result",
      "match_type": "exact | related",
      "matched_terms": ["topic words found in the result"],
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
- Every result above has already been checked against the user topic. Include only these real results; never add a result that is not listed.
- Use only a matching result from the live list, copying its exact URL, title, snippet, match type and matched terms. Include no more than one leader per available platform; fewer than three is correct when fewer platforms have relevant results.
- Never invent a brand, account, post, or URL. Preserve the exact/related classification so the UI can explain the match.
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
                    "max_tokens": limits.ANALYSIS_MAX_TOKENS,
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
    user: dict = Depends(get_current_user),
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

    limits.validate_input_len(brand_niche, "Brand niche")
    limits.validate_input_len(target_audience, "Target audience")
    limits.validate_input_len(topic, "Topic")
    limits.validate_input_len(location, "Location")

    relevance_topic = topic.strip() or f"{brand_niche.strip()} {core_offerings.strip()}".strip()
    profile = {
        "niche": brand_niche.strip(),
        "audience": target_audience.strip(),
        "business_type": business_type.strip(),
        "offerings": core_offerings.strip(),
        "location": location.strip(),
        "topic": relevance_topic,
    }

    try:
        platform_list = json.loads(platforms) if platforms else ["linkedin", "instagram", "facebook"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='platforms must be a JSON array like ["linkedin","instagram","facebook"]')
    active = [p for p in platform_list if p in PLATFORM_DOMAINS]
    if not active:
        raise HTTPException(status_code=400, detail="No supported platforms selected. Use linkedin, instagram, facebook.")

    cache_key = limits.make_cache_key(
        ["market-v2", brand_niche.strip(), topic.strip(), location.strip(), sorted(active), language]
    )
    cached = await limits.get_cached_result(cache_key)
    if cached:
        result = cached["payload"]
        result["cache_note"] = f'Showing your cached competitor insights from {_cached_at_str(cached["cached_at"])}.'
        print(f"[STRATEGY] Served cached competitor insights for niche='{brand_niche[:60]}'")
        return result

    try:
        usage_info = await limits.consume(
            user, "analysis", len(active),
            action="competitor_insights", endpoint="POST /api/market/competitor-insights",
        )
    except HTTPException as e:
        if e.status_code == 402:
            stale = await limits.get_expired_result(cache_key)
            if stale:
                result = stale["payload"]
                result["cache_note"] = f'Showing your last competitor insights from {_cached_at_str(stale["cached_at"])}.'
                result["usage_warning"] = e.detail
                return result
        raise

    # Market search subject: an explicit topic wins, otherwise synthesize one
    # from the brand profile so Tavily searches something meaningful. Location
    # is appended to scope results to the user's local market.
    query = relevance_topic
    if not query:
        raise HTTPException(status_code=400, detail="Provide a topic or a richer brand niche so market search can run.")

    flat, grouped, search_meta = await _live_search_competitors(query, platform_list, location=location)
    analysis, model = await _analyze_market(profile, flat, language)

    # Only allow model summaries to refer to URLs returned by live search.
    leaders = analysis.get("market_leaders", []) or []
    leaders = [l for l in leaders if isinstance(l, dict)]
    source_by_url = {_url_key(item.get("url") or ""): item for item in flat if _url_key(item.get("url") or "")}
    model_by_source = {}
    for l in leaders:
        p = (l.get("platform") or "").strip().lower()
        source = source_by_url.get(_url_key(l.get("link") or ""))
        if p not in active or not source or source.get("platform") != p:
            continue
        model_by_source[_url_key(l.get("link") or "")] = l

    verified_leaders = []
    for platform in active:
        candidates = [item for item in flat if item.get("platform") == platform]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item.get("match_type") != "exact", -(item.get("score") or 0)))
        source = next((item for item in candidates if _url_key(item.get("url") or "") in model_by_source), candidates[0])
        model_leader = model_by_source.get(_url_key(source.get("url") or ""), {})
        verified_leaders.append({
            **model_leader,
            "name": source.get("title") or model_leader.get("name") or PLATFORM_DOMAINS[platform]["label"],
            "platform": platform,
            "link": source.get("url"),
            "post_title": source.get("title") or "",
            "post_snippet": source.get("snippet") or "",
            "match_type": source.get("match_type"),
            "matched_terms": source.get("matched_terms") or [],
            "search_url": source.get("search_url"),
        })

    result = {
        "brand_profile": profile,
        "query": query,
        "market_overview": analysis.get("market_overview", ""),
        "market_leaders": verified_leaders,
        "matching_posts": flat,
        "positioning_advice": analysis.get("positioning_advice", []),
        "platform_tactics": analysis.get("platform_tactics", {
            "facebook": [], "instagram": [], "linkedin": [],
        }),
        "quick_wins": analysis.get("quick_wins", []),
        "providers": {"search": "tavily", "analysis": {"provider": "gemini", "model": model}},
        "search_meta": search_meta,
        "generated_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
        "usage": usage_info,
    }

    try:
        await limits.put_cached_result(cache_key, result)
    except Exception as e:
        logger.warning("Failed to cache market insights: %s", e)

    print(
        f"[STRATEGY] Market insights done in {result['latency_ms']}ms "
        f"({len(result['market_leaders'])} leaders across {len(platform_list)} platform search(es))"
    )
    logger.info(
        "Market insights done: %s leaders, %sms",
        len(result["market_leaders"]),
        result["latency_ms"],
    )

    await record_usage(
        user,
        "market_insights",
        "Ran a Market Intelligence Scan",
        f"Brand: {brand_niche.strip()[:90]}",
    )
    return result
