from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
import mongodb
from config import CORS_ORIGINS, SECRET_KEY
from routers import auth, content, schedule, social, strategy, user, billing
from routers.schedule import scan_due_posts

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("[DB] SQLite database ready (scheduled posts)")

    if await mongodb.mongo_ok():
        await mongodb.init_mongo()
        await mongodb.fix_missing_trials()
        print("[DB] MongoDB connected (users + activity history)")
    else:
        print("[DB] WARNING: MongoDB unreachable — auth/history will be unavailable")

    scheduler.add_job(
        scan_due_posts,
        trigger="interval",
        seconds=60,
        id="auto_publish",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    print("[SCHEDULER] Auto-publish engine started (scans every 60 seconds)")

    yield

    scheduler.shutdown(wait=False)
    print("[SCHEDULER] Auto-publish engine stopped")


app = FastAPI(
    title="BrandAura Social Media Integration",
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

app.include_router(auth.router)
app.include_router(social.router)
app.include_router(content.router)
app.include_router(strategy.router)
app.include_router(schedule.router)
app.include_router(user.router)
app.include_router(billing.router)
app.include_router(billing.admin_router)


@app.get("/")
def root():
    return {"message": "BrandAura API is running", "version": "1.0.0"}


@app.on_event("startup")
def _security_check():
    # Fail loud (but keep running) if a hard-coded default secret is in use.
    if SECRET_KEY in ("brandora-secret-key-change-in-production", ""):
        print(
            "SECURITY WARNING: SECRET_KEY is using the insecure default. "
            "Set a strong SECRET_KEY via the environment (.env) before deploying."
        )


@app.get("/api/health")
def health():
    return {"status": "healthy"}