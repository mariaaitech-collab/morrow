"""Per-platform media rules + helpers shared by every publisher.

Limits follow each platform's publishing API documentation:

  Instagram (Graph API, content publishing)
    image  JPEG only, max 8 MB, aspect ratio 4:5 (0.8) to 1.91:1, width 320-1440 px
    video  Reels: MP4/MOV (H.264 + AAC), max 300 MB, 3 s - 15 min
    Local files reach Meta without a tunnel (see instagram_publisher).
  Facebook Pages
    image  JPEG/PNG/GIF/WebP..., max 10 MB (/photos, multipart "source")
    video  max 1 GB / 20 min for the non-resumable /videos upload
  LinkedIn (assets registerUpload, single PUT)
    image  JPEG/PNG/GIF, max 10 MB
    video  MP4, 75 KB - 200 MB, 3 s - 30 min
  TikTok (Content Posting API, FILE_UPLOAD)
    video  MP4/MOV/WebM, max 4 GB, chunked by tiktok_client.plan_chunks

Codec/duration cannot be verified without ffprobe; those are left to the
platform, whose error message is surfaced to the user.
"""
from __future__ import annotations

import io
import os
from urllib.parse import urlparse

MB = 1024 * 1024

# Hard cap for any upload accepted by BrandAura (protects memory/disk).
MAX_IMAGE_BYTES = 20 * MB
MAX_VIDEO_BYTES = 1024 * MB

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".heic", ".heif")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")

LIMITS = {
    "instagram": {"image_bytes": 8 * MB, "video_bytes": 300 * MB, "video_exts": (".mp4", ".mov", ".m4v")},
    "facebook": {"image_bytes": 10 * MB, "video_bytes": 1024 * MB, "video_exts": (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")},
    "linkedin": {"image_bytes": 10 * MB, "video_bytes": 200 * MB, "video_exts": (".mp4", ".mov", ".m4v")},
    "tiktok": {"image_bytes": 0, "video_bytes": 4096 * MB, "video_exts": (".mp4", ".mov", ".m4v", ".webm")},
}

VIDEO_MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
              ".avi": "video/x-msvideo", ".mkv": "video/x-matroska"}

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "static", "uploads")

IG_MIN_RATIO, IG_MAX_RATIO = 0.8, 1.91
IG_MAX_WIDTH, IG_MIN_WIDTH = 1440, 320


def human(n: int) -> str:
    return f"{n / MB:.1f} MB"


def video_mime(path: str) -> str:
    return VIDEO_MIME.get(os.path.splitext(path)[1].lower(), "video/mp4")


# ---------------------------------------------------------------------------
# Upload-time normalization
# ---------------------------------------------------------------------------
def normalize_image_to_jpeg(file_bytes: bytes) -> bytes:
    """Return clean RGB JPEG bytes (EXIF rotation applied, transparency on white).

    Raises ValueError when the bytes are not a readable image, so a PNG/WebP is
    never stored under a .jpg name (Meta rejects such files).
    """
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Unsupported or corrupt image file ({e}). Use JPG, PNG or WebP.")
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)  # animated GIF/WebP: publish the first frame
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P", "PA"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()


def check_upload_size(size: int, media_type: str) -> str | None:
    """Return an error message when an upload exceeds BrandAura's hard cap."""
    cap = MAX_VIDEO_BYTES if media_type == "video" else MAX_IMAGE_BYTES
    if size == 0:
        return "The uploaded file is empty."
    if size > cap:
        return f"The {media_type} is {human(size)}; the maximum is {human(cap)}."
    return None


# ---------------------------------------------------------------------------
# Publish-time checks
# ---------------------------------------------------------------------------
def local_path_for(media_url: str | None) -> str | None:
    """Map an /uploads/... URL (any host) or a direct path to the file on disk."""
    if not media_url:
        return None
    if os.path.exists(media_url):
        return media_url
    path = urlparse(media_url).path
    if "/uploads/" in path:
        candidate = os.path.join(UPLOAD_DIR, os.path.basename(path))
        if os.path.exists(candidate):
            return candidate
    return None


def check_for_platform(platform: str, local_path: str | None, media_type: str | None) -> str | None:
    """Return a user-readable reason this file cannot go to `platform`, or None."""
    if not local_path or not media_type:
        return None
    rules = LIMITS.get(platform)
    if not rules:
        return None
    size = os.path.getsize(local_path)
    ext = os.path.splitext(local_path)[1].lower()
    name = platform.title() if platform != "linkedin" else "LinkedIn"
    if media_type == "video":
        if ext not in rules["video_exts"]:
            return f"{name} does not accept {ext or 'this'} videos. Use {', '.join(e.lstrip('.').upper() for e in rules['video_exts'])}."
        if size > rules["video_bytes"]:
            return f"This video is {human(size)}; {name} allows up to {human(rules['video_bytes'])}."
    else:
        if platform == "tiktok":
            return "TikTok only accepts videos."
        # Instagram gets its own fitted copy (see prepare_instagram_image).
        if platform != "instagram" and size > rules["image_bytes"]:
            return f"This image is {human(size)}; {name} allows up to {human(rules['image_bytes'])}."
    return None


def prepare_instagram_image(local_path: str) -> str:
    """Write an Instagram-compliant JPEG next to the original and return its path.

    Pads (never crops) to the allowed 4:5 - 1.91:1 aspect range, scales the width
    into 320-1440 px and keeps the file under 8 MB.
    """
    from PIL import Image

    img = Image.open(local_path)
    img.load()
    img = img.convert("RGB")
    w, h = img.size
    ratio = w / h
    if ratio < IG_MIN_RATIO:  # too tall: pad the sides
        new_w = int(round(h * IG_MIN_RATIO))
        canvas = Image.new("RGB", (new_w, h), (255, 255, 255))
        canvas.paste(img, ((new_w - w) // 2, 0))
        img = canvas
    elif ratio > IG_MAX_RATIO:  # too wide: pad top/bottom
        new_h = int(round(w / IG_MAX_RATIO))
        canvas = Image.new("RGB", (w, new_h), (255, 255, 255))
        canvas.paste(img, (0, (new_h - h) // 2))
        img = canvas
    w, h = img.size
    if w > IG_MAX_WIDTH:
        img = img.resize((IG_MAX_WIDTH, int(round(h * IG_MAX_WIDTH / w))), Image.LANCZOS)
    elif w < IG_MIN_WIDTH:
        img = img.resize((IG_MIN_WIDTH, int(round(h * IG_MIN_WIDTH / w))), Image.LANCZOS)

    base = os.path.splitext(os.path.basename(local_path))[0]
    out_path = os.path.join(UPLOAD_DIR, f"{base}_ig.jpg")
    for quality in (92, 85, 75, 65):
        img.save(out_path, format="JPEG", quality=quality, optimize=True)
        if os.path.getsize(out_path) <= LIMITS["instagram"]["image_bytes"]:
            break
    return out_path


# ---------------------------------------------------------------------------
# Public URLs (Instagram must DOWNLOAD the media from the internet)
# ---------------------------------------------------------------------------
def public_base_url() -> str:
    """PUBLIC_BACKEND_URL re-read from .env, so an edited value applies without a restart."""
    from dotenv import dotenv_values

    live = (dotenv_values(os.path.join(BACKEND_DIR, ".env")).get("PUBLIC_BACKEND_URL") or "").strip().rstrip("/")
    if not live:
        from config import PUBLIC_BACKEND_URL
        live = PUBLIC_BACKEND_URL
    return live if live.startswith("https://") else ""


def public_url_for(local_path: str) -> str | None:
    base = public_base_url()
    if not base or not local_path.startswith(UPLOAD_DIR):
        return None
    return f"{base}/uploads/{os.path.basename(local_path)}"


def is_private_url(url: str | None) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local") or host.startswith("192.168.") or host.startswith("10.")
