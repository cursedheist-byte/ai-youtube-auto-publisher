from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import (
    AutomationRun,
    DriveSource,
    DriveVideo,
    FailedUpload,
    UploadHistory,
    UploadStatus,
    User,
    YouTubeChannel,
    ChannelStatus,
)
from app.schemas import AdminDashboard, AutomationRunOut, AutomationScheduleOut, AutomationScheduleUpdate
from app.services.automation_service import get_schedule
from app.services import schedule_logic

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboard, dependencies=[Depends(require_admin)])
def get_dashboard(db: Session = Depends(get_db)):
    """
    Real counts from the real schema. Channels/uploads/failures stay at
    zero until Phases 3-4 add YouTube connections and uploads.
    """
    today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)

    total_drive_sources = db.query(func.count(DriveSource.id)).scalar() or 0
    total_discovered_videos = db.query(func.count(DriveVideo.id)).scalar() or 0
    connected_youtube_channels = db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status == ChannelStatus.CONNECTED).scalar() or 0
    todays_uploads = (
        db.query(func.count(UploadHistory.id))
        .filter(UploadHistory.status == UploadStatus.SUCCESS, UploadHistory.uploaded_at >= today_start)
        .scalar()
        or 0
    )
    failed_uploads = db.query(func.count(FailedUpload.id)).filter(FailedUpload.resolved.is_(False)).scalar() or 0

    return AdminDashboard(
        total_drive_sources=total_drive_sources,
        total_discovered_videos=total_discovered_videos,
        connected_youtube_channels=connected_youtube_channels,
        todays_uploads=todays_uploads,
        failed_uploads=failed_uploads,
        automation_status="APScheduler active",
    )


@router.get("/automation/runs", response_model=list[AutomationRunOut], dependencies=[Depends(require_admin)])
def recent_automation_runs(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(min(limit, 100)).all()


@router.get("/automation/schedule", response_model=AutomationScheduleOut, dependencies=[Depends(require_admin)])
def get_automation_schedule(db: Session = Depends(get_db)):
    """The two admin anchor times the whole publishing day is built around."""
    return get_schedule(db)


@router.put("/automation/schedule", response_model=AutomationScheduleOut, dependencies=[Depends(require_admin)])
def update_automation_schedule(payload: AutomationScheduleUpdate, db: Session = Depends(get_db)):
    """Admin sets exactly the two daily anchor times (HH:MM 24h)."""
    from fastapi import HTTPException

    if payload.anchor_1 is None and payload.anchor_2 is None:
        raise HTTPException(status_code=400, detail="Provide anchor_1 and/or anchor_2")
    row = get_schedule(db)
    a1 = payload.anchor_1 or row.anchor_1
    a2 = payload.anchor_2 or row.anchor_2
    t1, t2 = schedule_logic.parse_hhmm(a1), schedule_logic.parse_hhmm(a2)
    if t1 == t2:
        raise HTTPException(status_code=400, detail="The two anchor times must be different")
    row.anchor_1 = a1
    row.anchor_2 = a2
    db.commit()
    db.refresh(row)
    return row


@router.get("/automation/status", dependencies=[Depends(require_admin)])
def automation_status(db: Session = Depends(get_db)):
    """Everything the admin dashboard needs about today's automation state."""
    from datetime import datetime as dt, timezone as tz
    from zoneinfo import ZoneInfo

    schedule = get_schedule(db)
    now_utc = dt.now(tz.utc)
    local_now = now_utc.astimezone(ZoneInfo(schedule.timezone))
    today = local_now.date()
    runs_today = db.query(AutomationRun).filter(AutomationRun.run_date == today).all()
    connected_channels = (
        db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status == ChannelStatus.CONNECTED).scalar() or 0
    )
    return {
        "anchor_1": schedule.anchor_1,
        "anchor_2": schedule.anchor_2,
        "timezone": schedule.timezone,
        "server_time_local": local_now.strftime("%Y-%m-%d %H:%M"),
        "connected_channels": connected_channels,
        "runs_today": len(runs_today),
        "uploads_today": sum(r.videos_uploaded for r in runs_today),
    }


@router.get("/health-summary", dependencies=[Depends(require_admin)])
def health_summary(db: Session = Depends(get_db)):
    connected = db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status == ChannelStatus.CONNECTED).scalar() or 0
    channel_errors = db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status != ChannelStatus.CONNECTED).scalar() or 0
    unresolved = db.query(func.count(FailedUpload.id)).filter(FailedUpload.resolved.is_(False)).scalar() or 0
    recent_failed_scans = db.query(func.count(DriveSource.id)).filter(DriveSource.last_scan_error.isnot(None)).scalar() or 0
    return {"connected_channels": connected, "channels_needing_attention": channel_errors, "unresolved_upload_failures": unresolved, "sources_with_scan_errors": recent_failed_scans}
