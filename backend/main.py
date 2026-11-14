from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import firebase_db
from config import CORS_ORIGINS, SECRET_KEY, META_POLLING_ENABLED, META_POLL_INTERVAL
from routers import auth, content, schedule, social, strategy, user, billing, responder, webhooks
from routers.schedule import scan_due_posts

scheduler = AsyncIOScheduler()

# Local upload directory
UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("[DB] SQLite database ready (scheduled posts)")
    print(f"[UPLOAD] Local storage directory: {UPLOAD_DIR}")

    firestore_up, why = await firebase_db.firestore_ok()
    if firestore_up:
        await social.migrate_legacy_flat_accounts()
        await firebase_db.backfill_users()
        print(f"[DB] Firestore connected (project {firebase_db.db.project})")
    else:
        print(f"[DB] WARNING: Firestore unreachable — auth/history will be unavailable. {why}")

    from tiktok_client import tiktok

    for problem in tiktok.config_warnings():
        print(f"[TIKTOK] WARNING: {problem}")
    if tiktok.is_configured():
        print(f"[TIKTOK] Client key {tiktok.masked_key()}, redirect_uri {tiktok.redirect_uri}")

    import image_provider

    print(f"[IMAGE] Image provider: {image_provider.describe()}")

    from config import RESPONDER_PLATFORMS, RESPONDER_PLATFORMS_UNKNOWN

    print(f"[RESPONDER] Auto-replies on: {', '.join(RESPONDER_PLATFORMS) or 'none'} (RESPONDER_PLATFORMS)")
    if RESPONDER_PLATFORMS_UNKNOWN:
        print(f"[RESPONDER] WARNING: RESPONDER_PLATFORMS has unknown platform(s), ignored: {', '.join(RESPONDER_PLATFORMS_UNKNOWN)}")

    scheduler.add_job(
        scan_due_posts,
        trigger="interval",
        seconds=60,
        id="auto_publish",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    if META_POLLING_ENABLED and firestore_up:
        from datetime import datetime, timedelta
        import meta_poller

        scheduler.add_job(
            meta_poller.poll_once,
            trigger="interval",
            seconds=META_POLL_INTERVAL,
            id="meta_comment_poll",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=META_POLL_INTERVAL,
            next_run_time=datetime.now() + timedelta(seconds=5),
        )
        print(f"[POLLER] Meta comment polling ON (every {META_POLL_INTERVAL}s). Set META_POLLING_ENABLED=false once webhooks work.")
    else:
        print("[POLLER] Meta comment polling OFF")
    scheduler.start()
    print("[SCHEDULER] Auto-publish engine started (scans every 60 seconds)")

    yield

    scheduler.shutdown(wait=False)
    print("[SCHEDULER] Auto-publish engine stopped")


app = FastAPI(
    title="Morrow API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount local uploads for public access
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.include_router(auth.router)
app.include_router(social.router)
app.include_router(content.router)
app.include_router(strategy.router)
app.include_router(schedule.router)
app.include_router(user.router)
app.include_router(billing.router)
app.include_router(billing.admin_router)
app.include_router(responder.router)
app.include_router(webhooks.router)


@app.get("/")
def root():
    return {"message": "Morrow API is running", "version": "1.0.0"}


@app.on_event("startup")
def _security_check():
    if SECRET_KEY in ("brandora-secret-key-change-in-production", ""):
        print(
            "SECURITY WARNING: SECRET_KEY is using the insecure default. "
            "Set a strong SECRET_KEY via the environment (.env) before deploying."
        )


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/tiktok/status")
async def tiktok_status():
    """Unauthenticated TikTok connectivity probe (no secrets are returned)."""
    from tiktok_client import tiktok

    return await tiktok.check_connection()
