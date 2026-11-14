"""Safety screen for the Auto-Responder: the only check that runs before a reply.

The responder itself is rule-based (rule_matcher.py) and makes no model call.
A comment whose text hits an offensive or sensitive term is routed to the
"Needs your attention" queue instead of being answered automatically.

Public API:
    local_screen(text) -> dict
"""
from __future__ import annotations

import re

# --- Deterministic safety net ------------------------------------------------
# Not a complete profanity list: it catches obvious abuse by exact word.
# Matches route to HUMAN REVIEW, they never block or delete anything.
# Includes common Roman-Urdu/Hindi insults.
_OFFENSIVE_TERMS = [
    "fuck", "fucking", "fucker", "motherfucker", "shit", "bullshit", "bitch", "bastard", "asshole",
    "dick", "cunt", "slut", "whore", "retard", "retarded", "idiot", "stupid", "moron", "dumbass",
    "loser", "pathetic", "scumbag", "kill yourself", "kys",
    "nigger", "nigga", "faggot", "fag",
    "harami", "haramzada", "kamina", "kameena", "kutta", "kutti", "kuttay", "gadha", "ullu",
    "bewakoof", "badtameez", "chutiya", "chutiye", "madarchod", "behenchod", "bhenchod",
    "gandu", "lanat", "besharam", "ghatiya",
]
_SENSITIVE_TERMS = [
    "refund", "chargeback", "lawsuit", "sue you", "lawyer", "legal action", "police",
    "scam", "scammer", "fraud", "fake", "stolen", "cheated", "dhoka", "dhokebaaz", "fraudia",
    "never received", "worst", "disgusting", "allergic", "food poisoning", "injury", "hospital",
    "unsafe", "complaint", "boycott", "report you", "consumer court",
]


def _compile(terms: list[str]) -> re.Pattern:
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(escaped) + r")(?![\w])", re.IGNORECASE)


_OFFENSIVE_RE = _compile(_OFFENSIVE_TERMS)
_SENSITIVE_RE = _compile(_SENSITIVE_TERMS)


def local_screen(text: str) -> dict:
    text = text or ""
    offensive = sorted({m.group(1).lower() for m in _OFFENSIVE_RE.finditer(text)})
    sensitive = sorted({m.group(1).lower() for m in _SENSITIVE_RE.finditer(text)})
    letters = [c for c in text if c.isalpha()]
    shouting = len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.8
    return {
        "offensive_terms": offensive,
        "sensitive_terms": sensitive,
        "shouting": shouting,
        "flagged": bool(offensive),
        "sensitive": bool(sensitive),
    }
