import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, categories, channels, drive, uploads, access

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_yt_publisher")

scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def daily_automation_job():
    from app.services.automation_service import run_daily_automation
    run_daily_automation()


def retry_uploads_job():
    from app.services.automation_service import retry_failed_uploads
    retry_failed_uploads()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.get_job("automation_watchdog"):
        # A 60-second watchdog tick instead of a fixed cron: each tick computes
        # which anchor slots are due from the admin's schedule and claims them
        # idempotently. This is what makes the schedule survive Render free
        # tier sleep/wake — when the service wakes, the next tick catches up
        # every missed slot of today exactly once.
        scheduler.add_job(
            daily_automation_job,
            "interval",
            minutes=1,
            id="automation_watchdog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
    if not scheduler.get_job("retry_failed_uploads"):
        scheduler.add_job(
            retry_uploads_job,
            "interval",
            minutes=settings.retry_interval_minutes,
            id="retry_failed_uploads",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started (watchdog every 1 min; retry every %d min).", settings.retry_interval_minutes)
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AI YouTube Auto Publisher API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(access.router)
app.include_router(access.admin_router)
app.include_router(admin.router)
app.include_router(categories.router)
app.include_router(categories.admin_router)
app.include_router(drive.router)
app.include_router(channels.router)
app.include_router(uploads.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
