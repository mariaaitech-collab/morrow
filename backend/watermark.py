"""Brand watermark on every AI-generated image.

The site name (WATERMARK_TEXT in backend/.env, default "Morrow") is drawn into
the image's pixels on the server, bottom-right, in semi-transparent white. The
preview, a downloaded or saved copy, the stored upload and the published post
therefore all carry it; there is no unwatermarked copy to fetch.

Sizes are fractions of the image width, so the mark looks the same on a
512 px thumbnail and a 4K image.
"""
import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from config import WATERMARK_TEXT

OPACITY = 0.55            # the white text: 55% opaque
SHADOW_OPACITY = 0.25     # a soft dark halo under it, so it stays readable on light images
FONT_SCALE = 0.045        # text size: 4.5% of the image width
MAX_WIDTH_SCALE = 0.40    # a long name is shrunk to at most 40% of the width
MARGIN_SCALE = 0.025      # gap to the right and bottom edges: 2.5% of the width
MIN_FONT_PX = 12
# Clean, bold sans-serif faces: Windows first, then common Linux ones, then
# Pillow's bundled font so it works anywhere.
FONT_CANDIDATES = ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, width: int) -> ImageFont.FreeTypeFont:
    size = max(MIN_FONT_PX, round(width * FONT_SCALE))
    font = _font(size)
    text_w = draw.textlength(text, font=font)
    limit = width * MAX_WIDTH_SCALE
    if text_w > limit:
        font = _font(max(MIN_FONT_PX, int(size * limit / text_w)))
    return font


def apply(data: bytes, text: str | None = None, keep_clear_bottom: float = 0.0) -> tuple[bytes, str]:
    """Return (watermarked image bytes, mime type). Keeps PNG/WebP as they are; anything else becomes JPEG.

    `keep_clear_bottom`: a band at the bottom (as a fraction of the image width)
    that already carries something, e.g. the provider's own badge. The mark sits
    just above it instead of on top of it.

    Raises PIL.UnidentifiedImageError / OSError when `data` is not a readable image.
    """
    text = (WATERMARK_TEXT if text is None else text).strip()
    with Image.open(io.BytesIO(data)) as src:
        src.load()
        fmt = src.format if src.format in FORMATS else "JPEG"
        has_alpha = src.mode in ("RGBA", "LA", "PA") or "transparency" in src.info
        img = ImageOps.exif_transpose(src).convert("RGBA")
    if not text:
        return data, FORMATS.get(fmt, "image/jpeg")

    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _fit_font(draw, text, w)
    margin = max(4, round(w * MARGIN_SCALE))
    bottom = max(margin, round(w * (keep_clear_bottom + MARGIN_SCALE * 0.6))) if keep_clear_bottom else margin
    corner = (w - margin, h - bottom)  # anchor "rs": right edge, baseline

    # Soft shadow first (blurred), then the semi-transparent white text on top.
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(corner, text, font=font, anchor="rs", fill=(0, 0, 0, round(255 * SHADOW_OPACITY)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, font.size * 0.08)))
    draw.text(corner, text, font=font, anchor="rs", fill=(255, 255, 255, round(255 * OPACITY)))
    out = Image.alpha_composite(Image.alpha_composite(img, shadow), layer)

    buf = io.BytesIO()
    if fmt == "PNG":
        (out if has_alpha else out.convert("RGB")).save(buf, "PNG", optimize=True)
    elif fmt == "WEBP":
        (out if has_alpha else out.convert("RGB")).save(buf, "WEBP", quality=92)
    else:
        fmt = "JPEG"
        out.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
    return buf.getvalue(), FORMATS[fmt]
