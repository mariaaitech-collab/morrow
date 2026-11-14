import re

filepath = r"D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend\routers\content.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fix the AProuter typo
content = content.replace("router = AProuter(", "router = APIRouter(")

# Remove tempfile from the import if it's not there (we added it)
# Already handled by the earlier edit

# Find and replace the _upload_to_cloudinary function block
# Pattern: from "async def _upload_to_cloudinary" to just before "async def _generate_pollinations_image"
old_cloudinary_pattern = r'async def _upload_to_cloudinary\(.*?\n(?:.*?\n)*?    raise\n\n'

# More targeted: find from _upload_to_cloudinary to _detect_media_type and replace
start_marker = "async def _upload_to_cloudinary("
end_marker = "@router.post(\"/publish\")"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    # Replace everything between markers with the new upload functions
    new_block = '''async def _upload_to_local(file_bytes: bytes, filename: str, media_type: str = "image") -> str:
    """Save file to local disk and return the local path URL.

    Images are converted to JPG to satisfy Meta Graph API requirements.
    Videos are stored as-is.
    """
    ext = os.path.splitext(filename)[1] or ".jpg"
    if media_type == "image" and ext.lower() not in (".jpg", ".jpeg"):
        ext = ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / unique_name

    print(f"[LOCAL] Saving {filename} ({len(file_bytes)} bytes, type={media_type}) as {unique_name}")

    try:
        if media_type == "image":
            try:
                import io
                from PIL import Image
                img_obj = Image.open(io.BytesIO(file_bytes))
                if img_obj.mode in ("RGBA", "P"):
                    img_obj = img_obj.convert("RGB")
                output = io.BytesIO()
                img_obj.save(output, format="JPEG", quality=90)
                file_bytes = output.getvalue()
            except Exception:
                pass
        elif media_type == "video":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            try:
                tmp.write(file_bytes)
                tmp.close()
                shutil.copy(tmp.name, save_path)
            finally:
                os.unlink(tmp.name)
        else:
            with open(save_path, "wb") as f:
                f.write(file_bytes)

        local_url = f"/uploads/{unique_name}"
        print(f"[LOCAL] Saved {unique_name} at {local_url}")
        return local_url
    except Exception as e:
        print(f"[LOCAL] Upload FAILED: {e}")
        raise


async def _upload_to_local_with_url(request: Request, file_bytes: bytes, filename: str, media_type: str = "image") -> str:
    """Save file to local disk and return the absolute public URL."""
    local_url = await _upload_to_local(file_bytes, filename, media_type)
    return str(request.base_url) + local_url.lstrip("/")


'''
    content = content[:start_idx] + new_block + content[end_idx:]

# Now replace _upload_to_cloudinary calls with _upload_to_local calls in publish_content
# Find the publish_content function and update the upload call
publish_section = content.find("async def publish_content(")
if publish_section != -1:
    # Replace _upload_to_cloudinary(file_bytes, media.filename, media_type) with _upload_to_local(file_bytes, media.filename, media_type)
    content = content.replace(
        "media_url = await _upload_to_cloudinary(file_bytes, media.filename, media_type)",
        "media_url = await _upload_to_local(file_bytes, media.filename, media_type)"
    )

# Remove the cloudinary import block
content = content.replace(
    "import cloudinary\nimport cloudinary.uploader\n",
    ""
)
content = content.replace(
    "    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET,\n",
    ""
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixes applied successfully.")
