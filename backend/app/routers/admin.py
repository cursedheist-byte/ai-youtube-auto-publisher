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
from app.schemas import AdminDashboard, AutomationRunOut

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


@router.get("/health-summary", dependencies=[Depends(require_admin)])
def health_summary(db: Session = Depends(get_db)):
    connected = db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status == ChannelStatus.CONNECTED).scalar() or 0
    channel_errors = db.query(func.count(YouTubeChannel.id)).filter(YouTubeChannel.status != ChannelStatus.CONNECTED).scalar() or 0
    unresolved = db.query(func.count(FailedUpload.id)).filter(FailedUpload.resolved.is_(False)).scalar() or 0
    recent_failed_scans = db.query(func.count(DriveSource.id)).filter(DriveSource.last_scan_error.isnot(None)).scalar() or 0
    return {"connected_channels": connected, "channels_needing_attention": channel_errors, "unresolved_upload_failures": unresolved, "sources_with_scan_errors": recent_failed_scans}
