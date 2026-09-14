import logging

from fastapi import APIRouter, Header, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])
logger = logging.getLogger("ai_yt_publisher.scheduler_tick")


@router.get("/tick")
@router.post("/tick")
def external_tick(x_cron_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    """External keep-alive tick for hosting platforms that sleep when idle.

    Render's free tier spins the backend down when no browser is open, so the
    in-process APScheduler never fires and scheduled videos stop uploading.
    Point a free external cron (cron-job.org, UptimeRobot, GitHub Actions
    schedule, etc.) at GET /api/scheduler/tick every 5-10 minutes. Each call
    runs the same idempotent watchdog used internally, so missed slots are
    caught up exactly once and no upload can ever be duplicated.

    Protect it by setting CRON_SECRET in the backend env; the cron then sends
    the same value in the `X-Cron-Key` header.
    """
    if settings.cron_secret and x_cron_key != settings.cron_secret:
        return {"status": "ignored", "reason": "invalid or missing X-Cron-Key"}

    from app.services.automation_service import run_daily_automation, retry_failed_uploads

    run_daily_automation()
    retry_failed_uploads()
    return {"status": "ok"}
