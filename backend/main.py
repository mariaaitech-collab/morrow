from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
from routers import auth, content, schedule, social, strategy
from routers.schedule import scan_due_posts

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()

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
    title="Brandora Social Media Integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(social.router)
app.include_router(content.router)
app.include_router(strategy.router)
app.include_router(schedule.router)


@app.get("/")
def root():
    return {"message": "Brandora API is running", "version": "1.0.0"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}