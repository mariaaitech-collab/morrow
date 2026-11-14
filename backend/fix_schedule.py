filepath = r"D:\Downloads\fyp-brandaura\Brandora (2)\Brandora\backend\routers\schedule.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace _upload_to_cloudinary calls with _upload_to_local
content = content.replace(
    "_upload_to_cloudinary,",
    "_upload_to_local,"
)
content = content.replace(
    'run every 60 seconds) that publishes due posts through the existing Cloudinary +\nMeta pipeline',
    'run every 60 seconds) that publishes due posts through the existing local storage +\nMeta pipeline'
)

# Replace _upload_to_cloudinary(img_bytes, filename, "image") with _upload_to_local(img_bytes, filename, "image", request)
content = content.replace(
    'media_url = await _upload_to_local(img_bytes, filename, "image")',
    'media_url = await _upload_to_local(img_bytes, filename, "image", request)'
)
content = content.replace(
    'media_url = await _upload_to_local(file_bytes, media.filename, media_type)',
    'media_url = await _upload_to_local(file_bytes, media.filename, media_type, request)'
)
content = content.replace(
    'media_url = await _upload_to_local(img_bytes, f"cal_ai_{int(time.time()*1000)}.jpg", "image")',
    'media_url = await _upload_to_local(img_bytes, f"cal_ai_{int(time.time()*1000)}.jpg", "image", request)'
)

# Also replace _upload_to_cloudinary(file_bytes, media.filename, media_type)
content = content.replace(
    'media_url = await _upload_to_local(file_bytes, media.filename, media_type)',
    'media_url = await _upload_to_local(file_bytes, media.filename, media_type, request)'
)

# Add Request import to calendar_create_post if not present
# calendar_create_post needs request param
content = content.replace(
    'async def calendar_create_post(payload: CalendarPostCreate, user: dict = Depends(require_token)):',
    'async def calendar_create_post(request: Request, payload: CalendarPostCreate, user: dict = Depends(require_token)):'
)

# Pass request to _build_post_rows
content = content.replace(
    'rows = await _build_post_rows(payload, user["email"])',
    'rows = await _build_post_rows(request, payload, user["email"])'
)

# Update _build_post_rows signature
content = content.replace(
    'async def _build_post_rows(payload: CalendarPostCreate, owner_email: str):',
    'async def _build_post_rows(request: Request, payload: CalendarPostCreate, owner_email: str):'
)

# Update the _upload_to_local call inside _build_post_rows  
# It calls _upload_to_local(img_bytes, f"cal_ai_{int(time.time()*1000)}.jpg", "image")
# Already handled by the replace above since the variable is also named `request` inside

# Fix comment in create_scheduled_post
content = content.replace(
    '# Option B — pre-generate the AI image NOW and save its Cloudinary URL',
    '# Option B — pre-generate the AI image NOW and save its local URL'
)
content = content.replace(
    '# Option A — upload the attached file now so the publish step is only a URL',
    '# Option A — upload the attached file now so the publish step is only a URL'
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("schedule.py fixes applied.")
