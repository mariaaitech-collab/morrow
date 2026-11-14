"""Rule-based matcher for the comment auto-responder: no model, no network, no cost.

    respond(rules, fallback, text, platform)  -> what would be posted, and why
    match(rules, text, platform)              -> the best passing rule, plus every scored rule
    find_keywords(keywords, text)             -> which of these keywords the text contains
    migrate_faqs(faqs)                        -> old persona FAQs as rules (nothing dropped)

A rule is a dict:
    {"id", "name", "enabled", "single_keyword", "keywords": [...], "phrases": [...],
     "answers": [{"text": "...", "lang": "any" | "en" | "ur" | "ur-Arab"}], "platforms": [...],
     "match_type": "smart" | "exact" | "contains" | "starts_with", "priority": 0-100,
     "force_review": bool}
`platforms` empty means every platform. Answer languages: English, Roman Urdu,
Urdu script, or any. Missing match_type/priority/force_review mean smart/0/False.

Comments and triggers are normalized the same way first: lowercase, trimmed,
emoji, punctuation, @mentions and URLs removed.

Simple match types use the rule's keywords and phrases as plain triggers:
    exact        the comment IS one of them                        score 100
    starts_with  the comment begins with one (whole words)         score 95
    contains     one appears anywhere in the comment (whole words) score 90

The smart match type scores one rule against one comment:
    exact      comment == one of the rule's trigger phrases              score 100
    fuzzy      comment ~ a trigger phrase, similarity >= cutoff          score = similarity (85-99)
    keywords   rule keywords found as whole words; a one-word keyword     10 per hit, 8 per fuzzy hit,
               may also be misspelled within the cutoff ("shiping")       at most 80
A keyword match only counts with MIN_KEYWORD_HITS hits, or one hit on a keyword
of STRONG_KEYWORD_LEN characters or more, unless the rule has single_keyword
on (any one hit is enough). Keyword scores stay below any phrase match.

When several rules match, the winner is the one with the highest priority; on
a tie, the most specific one (its longest matched keyword or phrase), then the
higher score, more matched keywords, and finally the rule listed first.
"""
from __future__ import annotations

import copy
import random
import re
import uuid

from rapidfuzz import fuzz

from config import RESPONDER_FUZZY_CUTOFF, RESPONDER_MIN_KEYWORD_HITS, RESPONDER_STRONG_KEYWORD_LEN

MATCH_TYPES = ("smart", "exact", "contains", "starts_with")
SIMPLE_MATCH_SCORES = {"exact": 100.0, "starts_with": 95.0, "contains": 90.0}
EXACT_SCORE = 100.0
KEYWORD_HIT_SCORE = 10.0
FUZZY_KEYWORD_HIT_SCORE = 8.0
KEYWORD_SCORE_CAP = 80.0
FUZZY_MIN_WORD_LEN = 4  # shorter words are never fuzzy-matched ("hi" vs "he")
LANGS = ("any", "en", "ur", "ur-Arab")

# --------------------------------------------------------------------------
# Normalization + language
# --------------------------------------------------------------------------
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MENTION = re.compile(r"@[\w.]+")
_ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
# Harakat, superscript alef and tatweel carry no meaning for matching.
_ARABIC_MARKS = re.compile(r"[ً-ٰٟـ]")
# Arabic-keyboard letters typed for their Urdu equivalents.
_URDU_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ه": "ہ"})

# Common Roman Urdu words that rarely appear in English comments.
_ROMAN_URDU = frozenset("""
hai hain ka ki ke ko se mein aap ap kya kitne kitna kitni kab kahan kaise kyun bhai yar yaar
shukriya acha achha bohat bohot bahut nahi nai karein karen krna milega chahiye hoga wala wali
salam salaam assalam asalam aoa jazakallah mashallah zabardast qeemat rabta humein hamari
""".split())

_STOPWORDS = frozenset("""
a an the and or but if of to in on at for from with by about as is are was were be been am
do does did i you he she it we they me my your our their this that these those there here
what which who how when where why can could would should will may might must have has had
not no yes so very just please pls plz much many any some get got hi hello hey thanks thank
hai hain ho ka ki ke ko se mein main aap ap tum hum ye yeh wo woh kya bhi na nahi
kab kahan kaise kyun kitna kitne kitni
""".split())


def normalize(text: str) -> str:
    """Lowercase; @mentions, URLs, punctuation and emoji removed; whitespace collapsed."""
    text = _MENTION.sub(" ", _URL.sub(" ", (text or "").lower()))
    text = _ARABIC_MARKS.sub("", text).translate(_URDU_LETTERS)
    return " ".join(re.sub(r"[^\w\s]|_", " ", text).split())


def detect_language(text: str) -> str:
    """'ur-Arab' for Urdu script, 'ur' for Roman Urdu words, else 'en'."""
    if _ARABIC_SCRIPT.search(text or ""):
        return "ur-Arab"
    return "ur" if set(normalize(text).split()) & _ROMAN_URDU else "en"


def content_words(text: str) -> set[str]:
    """Content words, lightly stemmed (delivery, deliveries, delivered -> deliver).

    Used to group similar unanswered comments.
    """
    words = set()
    for word in normalize(text).split():
        if len(word) < 2 or word in _STOPWORDS or word.isdigit():
            continue
        for suffix in ("ies", "ing", "ed", "s", "y"):
            if word.isascii() and word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)]
                break
        words.add(word)
    return words


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------
def _words_match(rule_word: str, comment_word: str, fuzzy: bool, cutoff: float) -> bool:
    if rule_word == comment_word:
        return True
    return (fuzzy and len(rule_word) >= FUZZY_MIN_WORD_LEN and len(comment_word) >= FUZZY_MIN_WORD_LEN - 1
            and fuzz.ratio(rule_word, comment_word) >= cutoff)


def _keyword_hits(keywords: list[str], words: list[str], cutoff: float) -> list[dict]:
    """Whole-word keyword hits. Each comment word counts for one keyword at most."""
    used: set[int] = set()
    hits: list[dict] = []
    found: set[str] = set()
    # Longest keywords first, so "cash on delivery" claims its words before "delivery".
    ordered = sorted({normalize(k) for k in keywords if normalize(k)}, key=len, reverse=True)
    for fuzzy in (False, True):
        for kw in ordered:
            if kw in found:
                continue
            parts = kw.split()
            for start in range(len(words) - len(parts) + 1):
                span = range(start, start + len(parts))
                if any(i in used for i in span):
                    continue
                if all(_words_match(p, words[i], fuzzy, cutoff) for p, i in zip(parts, span)):
                    used.update(span)
                    found.add(kw)
                    hits.append({"keyword": kw, "fuzzy": fuzzy, "heard": " ".join(words[i] for i in span)})
                    break
    return hits


def find_keywords(keywords: list[str], text: str, cutoff: float = RESPONDER_FUZZY_CUTOFF) -> list[str]:
    """Which of `keywords` appear in `text` (whole words, misspellings within the cutoff)."""
    return [h["keyword"] for h in _keyword_hits(keywords, normalize(text).split(), cutoff)]


def _priority(rule: dict) -> int:
    try:
        return int(rule.get("priority") or 0)
    except (TypeError, ValueError):
        return 0


def _simple_hit(match_type: str, comment: str, trigger: str) -> bool:
    """Whole words only, so "hi" never matches inside "this"."""
    if match_type == "exact":
        return comment == trigger
    if match_type == "starts_with":
        return comment == trigger or comment.startswith(trigger + " ")
    return f" {trigger} " in f" {comment} "


def _score_simple(rule: dict, comment: str, match_type: str) -> dict:
    """exact / starts_with / contains against the rule's keywords and phrases."""
    triggers = {t for t in (normalize(x) for x in (rule.get("keywords") or []) + (rule.get("phrases") or [])) if t}
    hits = sorted((t for t in triggers if _simple_hit(match_type, comment, t)), key=len, reverse=True)
    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name", ""),
        "method": match_type if hits else "",
        "score": SIMPLE_MATCH_SCORES[match_type] if hits else 0.0,
        "passed": bool(hits),
        "phrase": hits[0] if hits and match_type == "exact" else "",
        "keywords": hits,
        "fuzzy_keywords": [],
        "priority": _priority(rule),
        "specificity": len(hits[0]) if hits else 0,
    }


def score_rule(rule: dict, comment: str, *, cutoff: float = RESPONDER_FUZZY_CUTOFF,
               min_hits: int = RESPONDER_MIN_KEYWORD_HITS,
               strong_len: int = RESPONDER_STRONG_KEYWORD_LEN) -> dict:
    """Score one rule against an already-normalized comment."""
    match_type = rule.get("match_type") or "smart"
    if match_type in SIMPLE_MATCH_SCORES:
        return _score_simple(rule, comment, match_type)
    words = comment.split()
    phrases = [p for p in (normalize(x) for x in rule.get("phrases") or []) if p]

    method, score, phrase = "", 0.0, ""
    if comment and comment in phrases:
        method, score, phrase = "exact", EXACT_SCORE, comment
    elif comment and phrases:
        best = max(phrases, key=lambda p: fuzz.ratio(comment, p))
        similarity = round(fuzz.ratio(comment, best), 1)
        if similarity >= cutoff:
            method, score, phrase = "fuzzy", similarity, best

    hits = _keyword_hits(rule.get("keywords") or [], words, cutoff)
    keyword_score = min(KEYWORD_SCORE_CAP, sum(FUZZY_KEYWORD_HIT_SCORE if h["fuzzy"] else KEYWORD_HIT_SCORE for h in hits))
    keyword_pass = bool(hits) and (
        bool(rule.get("single_keyword"))
        or len(hits) >= min_hits
        or any(len(h["keyword"]) >= strong_len for h in hits)
    )
    if not method and hits:
        method, score = "keywords", keyword_score

    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name", ""),
        "method": method,
        "score": score,
        "passed": method in ("exact", "fuzzy") or keyword_pass,
        "phrase": phrase,
        "keywords": [h["keyword"] for h in hits],
        "fuzzy_keywords": [f"{h['heard']}~{h['keyword']}" for h in hits if h["fuzzy"]],
        "priority": _priority(rule),
        # How much of the comment the rule pinned down: its longest matched trigger.
        "specificity": max([len(phrase)] + [len(h["keyword"]) for h in hits]) if method else 0,
    }


def match(rules: list[dict], text: str, platform: str | None = None, **params) -> dict:
    """Best passing rule (or None) and every rule that scored, best score first."""
    comment = normalize(text)
    scored = []
    for order, rule in enumerate(rules or []):
        if not rule.get("enabled", True):
            continue
        if platform and rule.get("platforms") and platform not in rule["platforms"]:
            continue
        result = score_rule(rule, comment, **params)
        if result["score"] > 0:
            scored.append((result, order))
    # Shown to the user (test box, near misses): higher score first.
    scored.sort(key=lambda item: (-item[0]["score"], -len(item[0]["keywords"]), item[1]))
    # The winner: highest priority, then the most specific, then score, then listed first.
    passing = [item for item in scored if item[0]["passed"]]
    best = min(passing, key=lambda item: (-item[0]["priority"], -item[0]["specificity"], -item[0]["score"],
                                          -len(item[0]["keywords"]), item[1]))[0] if passing else None
    return {"normalized": comment, "best": best, "scored": [r for r, _ in scored]}


# --------------------------------------------------------------------------
# Replies
# --------------------------------------------------------------------------
# Urdu-script comments take Urdu-script answers first, then Roman Urdu.
_LANG_PREFERENCE = {"ur-Arab": ("ur-Arab", "ur"), "ur": ("ur",), "en": ("en",)}


def pick_answer(answers: list[dict], lang: str, rng: random.Random | None = None) -> str:
    """A random answer in the comment's language (or 'any'); any answer if none fits."""
    usable = [a for a in answers or [] if (a.get("text") or "").strip()]
    pool: list[dict] = []
    for preferred in _LANG_PREFERENCE.get(lang, ()):
        pool = [a for a in usable if a.get("lang", "any") in (preferred, "any")]
        if any(a.get("lang") == preferred for a in pool):
            break
    pool = pool or [a for a in usable if a.get("lang", "any") == "any"] or usable
    return (rng or random).choice(pool)["text"].strip() if pool else ""


def respond(rules: list[dict], fallback: dict, text: str, platform: str | None = None,
            rng: random.Random | None = None, **params) -> dict:
    """What the responder would do with one comment.

    outcome: "matched" (a rule's answer), "fallback" (the default reply), or
    "no_match" (fallback switched off: the comment goes to the queue).
    """
    lang = detect_language(text)
    result = match(rules, text, platform, **params)
    best = result["best"]
    base = {"lang": lang, "normalized": result["normalized"], "scored": result["scored"]}
    if best:
        rule = next(r for r in rules if r.get("id") == best["rule_id"])
        reply = pick_answer(rule.get("answers"), lang, rng)
        if reply:
            return {**base, "outcome": "matched", "rule_id": best["rule_id"], "rule_name": best["rule_name"],
                    "score": best["score"], "method": best["method"], "keywords": best["keywords"],
                    "fuzzy_keywords": best["fuzzy_keywords"], "phrase": best["phrase"], "reply": reply}
    empty = {"rule_id": None, "rule_name": "", "score": 0.0, "method": "", "keywords": [],
             "fuzzy_keywords": [], "phrase": ""}
    if (fallback or {}).get("enabled", True):
        reply = pick_answer((fallback or {}).get("answers"), lang, rng)
        if reply:
            return {**base, **empty, "outcome": "fallback", "reply": reply}
    return {**base, **empty, "outcome": "no_match", "reply": ""}


# --------------------------------------------------------------------------
# Defaults (editable by the user; answers never state facts the brand did not give)
# --------------------------------------------------------------------------
def _en(text: str) -> dict:
    return {"text": text, "lang": "en"}


def _ur(text: str) -> dict:
    return {"text": text, "lang": "ur"}


def _urs(text: str) -> dict:
    return {"text": text, "lang": "ur-Arab"}


DEFAULT_RULES: list[dict] = [
    {
        "id": "greeting", "name": "Greeting", "enabled": True, "single_keyword": True, "platforms": [],
        "keywords": ["hi", "hello", "hey", "salam", "salaam", "assalam", "asalam", "aoa",
                     "assalamualaikum", "good morning", "good evening",
                     "السلام علیکم", "سلام", "ہیلو", "صبح بخیر"],
        "phrases": ["hi", "hello", "hey", "hi there", "hello there", "salam", "salaam", "aoa",
                    "assalam o alaikum", "asalam o alaikum", "assalamualaikum", "good morning", "good evening",
                    "السلام علیکم", "سلام", "ہیلو", "صبح بخیر"],
        "answers": [_en("Hi there! 👋 Thanks for stopping by. How can we help you today?"),
                    _en("Hello! 😊 Let us know how we can help."),
                    _ur("Salam! 😊 Bataiye, hum aap ki kya madad kar sakte hain?"),
                    _urs("خوش آمدید! 😊 بتائیے، ہم آپ کی کیا مدد کر سکتے ہیں؟")],
    },
    {
        "id": "praise", "name": "Praise and thanks", "enabled": True, "single_keyword": True, "platforms": [],
        "keywords": ["nice", "lovely", "beautiful", "amazing", "wow", "awesome", "gorgeous", "love it",
                     "zabardast", "bohat acha", "bohot acha", "bahut acha", "mashallah", "masha allah",
                     "shukriya", "thanks", "thank you",
                     "شکریہ", "ماشاءاللہ", "ماشااللہ", "زبردست", "بہت اچھا", "خوبصورت", "کمال"],
        "phrases": ["nice", "very nice", "so nice", "wow", "lovely", "beautiful", "amazing", "awesome",
                    "love it", "love this", "mashallah", "masha allah", "zabardast", "bohat acha",
                    "bohot acha", "thanks", "thank you", "shukriya",
                    "شکریہ", "ماشاءاللہ", "زبردست", "بہت اچھا", "بہت خوبصورت"],
        "answers": [_en("Thank you so much! 💛 We're glad you like it."),
                    _en("Thanks a lot for the love! 😊"),
                    _ur("Bohat shukriya! 💛 Aap ka pyaar hamare liye bohat qeemti hai."),
                    _ur("Shukriya! 😊 Aap ko pasand aaya, yeh hamare liye bohat khushi ki baat hai."),
                    _urs("بہت شکریہ! 💛 آپ کی محبت ہمارے لیے بہت قیمتی ہے۔"),
                    _urs("شکریہ! 😊 آپ کو پسند آیا، یہ ہمارے لیے بہت خوشی کی بات ہے۔")],
    },
    {
        "id": "price", "name": "Price", "enabled": True, "single_keyword": False, "platforms": [],
        "keywords": ["price", "pricing", "cost", "how much", "rate", "kitne ka", "kitne ki", "kitnay ka",
                     "qeemat", "kitna", "قیمت", "کتنے کا", "کتنے کی", "ریٹ", "کتنا"],
        "phrases": ["price", "price please", "price plz", "what is the price", "whats the price", "how much",
                    "how much is this", "kitne ka hai", "kitne ki hai", "price kya hai", "rate kya hai",
                    "qeemat kya hai", "قیمت", "قیمت کیا ہے", "کتنے کا ہے", "کتنے کی ہے", "ریٹ کیا ہے"],
        "answers": [_en("Thanks for your interest! Please DM us and we'll share the price details."),
                    _ur("Price ki details ke liye humein DM karein, hum foran bata denge."),
                    _urs("قیمت کی تفصیل کے لیے ہمیں ڈی ایم کریں، ہم فوراً بتا دیں گے۔")],
    },
    {
        "id": "delivery", "name": "Delivery", "enabled": True, "single_keyword": False, "platforms": [],
        "keywords": ["delivery", "deliver", "shipping", "courier", "cash on delivery", "kab milega", "kitne din",
                     "ڈیلیوری", "ترسیل", "کوریئر", "کب ملے گا", "کتنے دن"],
        "phrases": ["do you deliver", "delivery", "shipping", "delivery kab hogi", "kab milega",
                    "kitne din mein milega", "shipping charges", "delivery charges",
                    "ڈیلیوری", "ڈیلیوری کب ہوگی", "کب ملے گا", "کتنے دن میں ملے گا"],
        "answers": [_en("We'd love to get this to you! Please DM us your city and we'll share delivery time and charges."),
                    _ur("Apna shehar humein DM karein, hum delivery ka time aur charges bata denge."),
                    _urs("اپنا شہر ہمیں ڈی ایم کریں، ہم ڈیلیوری کا وقت اور چارجز بتا دیں گے۔")],
    },
    {
        "id": "contact", "name": "Contact", "enabled": True, "single_keyword": False, "platforms": [],
        "keywords": ["contact", "number", "phone", "whatsapp", "dm", "inbox", "email", "kaise rabta", "rabta",
                     "رابطہ", "نمبر", "واٹس ایپ", "فون"],
        "phrases": ["contact", "contact number", "whatsapp number", "number please", "how can i contact you",
                    "rabta kaise karein", "رابطہ", "رابطہ نمبر", "واٹس ایپ نمبر", "رابطہ کیسے کریں"],
        "answers": [_en("Please send us a DM here and our team will get back to you shortly."),
                    _ur("Humein yahan DM karein, hamari team jald aap se rabta karegi."),
                    _urs("ہمیں یہاں ڈی ایم کریں، ہماری ٹیم جلد آپ سے رابطہ کرے گی۔")],
    },
    {
        "id": "hours", "name": "Hours", "enabled": True, "single_keyword": False, "platforms": [],
        "keywords": ["open", "opening hours", "timing", "timings", "close", "closed", "hours", "kab khulta",
                     "kab khulti", "اوقات", "ٹائمنگ", "کب کھلتا", "کب کھلتی", "کب بند"],
        "phrases": ["timing", "timings", "opening hours", "what are your timings", "are you open today",
                    "kab khulta hai", "kab tak khula hai", "اوقات", "اوقات کار", "ٹائمنگ", "کب کھلتا ہے",
                    "کب تک کھلا ہے"],
        "answers": [_en("Thanks for asking! Please DM us and we'll share our current timings."),
                    _ur("Hamari timings ke liye humein DM karein, hum bata denge."),
                    _urs("ہمارے اوقات کے لیے ہمیں ڈی ایم کریں، ہم بتا دیں گے۔")],
    },
]

DEFAULT_FALLBACK: dict = {
    "enabled": True,
    "answers": [
        _en("Thanks for reaching out! Please DM us and our team will get back to you."),
        _en("Thank you for your comment — send us a DM and we'll help you out."),
        _en("Thanks for your message! Drop us a DM and we'll get back to you shortly."),
        _ur("Shukriya! Please humein DM karein, hamari team aap se rabta karegi."),
        _ur("Comment karne ka shukriya! Humein DM karein, hum jald jawab denge."),
        _urs("شکریہ! براہ کرم ہمیں ڈی ایم کریں، ہماری ٹیم آپ سے رابطہ کرے گی۔"),
        _urs("کمنٹ کرنے کا شکریہ! ہمیں ڈی ایم کریں، ہم جلد جواب دیں گے۔"),
    ],
}

# The blocklist: comments with any of these always go to "Needs your attention",
# whatever matched and whatever the mode. Complaint, refund, legal and abuse terms.
DEFAULT_ESCALATION_KEYWORDS: list[str] = [
    "refund", "complaint", "scam", "wrong", "broken", "cheated",
    "chargeback", "fraud", "legal", "lawyer", "lawsuit", "sue", "court",
    "abuse", "abusive", "harassment", "threat",
    "ghalat", "kharab", "dhoka", "shikayat",
    "غلط", "خراب", "دھوکہ", "شکایت",
]


def default_rules() -> list[dict]:
    return copy.deepcopy(DEFAULT_RULES)


def default_fallback() -> dict:
    return copy.deepcopy(DEFAULT_FALLBACK)


def default_escalation_keywords() -> list[str]:
    return list(DEFAULT_ESCALATION_KEYWORDS)


# --------------------------------------------------------------------------
# Migration from the old FAQ list
# --------------------------------------------------------------------------
def extract_keywords(question: str, limit: int = 6) -> list[str]:
    """Content words of a question, in order: 'Which areas do you deliver to?' -> ['areas', 'deliver']."""
    seen: list[str] = []
    for word in normalize(question).split():
        if len(word) >= 3 and not word.isdigit() and word not in _STOPWORDS and word not in seen:
            seen.append(word)
    return seen[:limit]


def rule_from_faq(faq: dict) -> dict:
    question = (faq.get("question") or "").strip()
    return {
        "id": faq.get("id") or uuid.uuid4().hex[:10],  # keeps the FAQ's id, so history stays linked
        "name": question[:80] or "Imported FAQ",
        "enabled": True,
        "single_keyword": False,
        "platforms": [],
        "keywords": extract_keywords(question),
        "phrases": [question] if question else [],
        "answers": [{"text": (faq.get("answer") or "").strip(), "lang": "any"}],
        "source": "faq",
    }


def migrate_faqs(faqs: list[dict]) -> list[dict]:
    """Every FAQ with a question and an answer becomes a rule; imported rules go first."""
    return [rule_from_faq(f) for f in faqs or [] if (f.get("question") or "").strip() and (f.get("answer") or "").strip()]
