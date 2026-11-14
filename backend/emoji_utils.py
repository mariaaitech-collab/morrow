"""Emoji-only detection for the Auto-Responder.

    is_emoji_only("🔥🔥 ❤️")      -> True    (react with a Like, never write text)
    is_emoji_only("love it 😍")   -> False   (has words: goes to the AI reply path)
    is_emoji_only("1234")         -> False   (digits are text, not emoji)

Stdlib only. Whitespace and punctuation are ignored, so "🔥🔥!!!" still counts
as emoji-only; at least one real emoji is required, so "..." or "!!!" does not.
"""
from __future__ import annotations

import re
import unicodedata

# (start, end) inclusive code point ranges that render as emoji.
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),  # mahjong/cards, enclosed, flags, symbols, skin tones, pictographs
    (0x2600, 0x27BF),    # misc symbols + dingbats (☀ ❤ ✨ ✔)
    (0x2300, 0x23FF),    # misc technical (⌚ ⏰ ⏩)
    (0x2B00, 0x2BFF),    # arrows/stars (⭐ ⬆)
    (0x2934, 0x2935),
    (0x25AA, 0x25AB), (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FE),
    (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x203C), (0x2049, 0x2049),
    (0x2122, 0x2122), (0x2139, 0x2139), (0x3030, 0x3030), (0x303D, 0x303D),
    (0x3297, 0x3297), (0x3299, 0x3299),
)

# Invisible glue inside emoji sequences: ZWJ, variation selectors, keycap
# combiner, and the tag characters used by subdivision flags (🏴󠁧󠁢󠁥󠁮󠁧󠁿).
_JOINERS = {0x200D, 0xFE0E, 0xFE0F, 0x20E3}
_TAG_RANGE = (0xE0020, 0xE007F)


def _is_emoji_char(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


_KEYCAP_RE = re.compile("[0-9#*]️?⃣")


def is_emoji_only(text: str) -> bool:
    # Keycaps (1️⃣) are the one emoji built from ASCII; drop them up
    # front so the digit is not mistaken for text below.
    stripped = _KEYCAP_RE.sub("", text or "")
    seen_emoji = stripped != (text or "")
    for ch in stripped:
        cp = ord(ch)
        if cp in _JOINERS or _TAG_RANGE[0] <= cp <= _TAG_RANGE[1]:
            continue
        category = unicodedata.category(ch)
        if category[0] in "ZP" or category in ("Cc", "Cf"):
            continue
        if not _is_emoji_char(cp):
            return False  # a letter, digit or other character: real text
        seen_emoji = True
    return seen_emoji
