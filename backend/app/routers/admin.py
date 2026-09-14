import uuid
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
from app.schemas import AdminDashboard, AdminUserOut, AutomationRunOut, AutomationScheduleOut, AutomationScheduleUpdate
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


@router.get("/users", response_model=list[AdminUserOut], dependencies=[Depends(require_admin)])
def admin_list_users(db: Session = Depends(get_db)):
    """Every registered user with their account details for the admin."""
    from app.models import UserCredential
    from app.schemas import AdminUserOut

    users = db.query(User).order_by(User.created_at.desc()).all()
    channel_counts = dict(db.query(YouTubeChannel.user_id, func.count(YouTubeChannel.id)).group_by(YouTubeChannel.user_id).all())
    upload_counts = dict(
        db.query(YouTubeChannel.user_id, func.count(UploadHistory.id))
        .join(UploadHistory, UploadHistory.channel_id == YouTubeChannel.id)
        .filter(UploadHistory.status == UploadStatus.SUCCESS)
        .group_by(YouTubeChannel.user_id)
        .all()
    )
    out = []
    for u in users:
        grant = u.access_grant
        creds = db.query(UserCredential).filter(UserCredential.user_id == u.id).first()
        out.append(AdminUserOut(
            id=u.id,
            email=u.email,
            role=u.role,
            access_mode=u.access_mode.value if hasattr(u.access_mode, "value") else str(u.access_mode),
            created_at=u.created_at,
            has_google_credentials=bool(creds and creds.google_client_id and creds.google_client_secret),
            has_openrouter_key=bool(creds and creds.openrouter_api_key),
            daily_video_limit=grant.daily_video_limit if grant else None,
            channel_limit=grant.channel_limit if grant else None,
            channel_count=channel_counts.get(u.id, 0),
            upload_count=upload_counts.get(u.id, 0),
        ))
    return out


@router.post("/users/{user_id}/terminate", dependencies=[Depends(require_admin)])
def admin_terminate_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Terminate a user account: revoke admin-code access and disconnect their channels."""
    from fastapi import HTTPException

    from app.models import AccessGrant, UserCredential

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Admin accounts cannot be terminated from here.")

    # Revoke any admin-code access grant so they fall back to own credentials.
    grant = db.query(AccessGrant).filter(AccessGrant.user_id == target.id).first()
    if grant:
        code = db.query(AccessCode).filter(AccessCode.id == grant.access_code_id).with_for_update().first()
        if code:
            code.status = AccessCodeStatus.REVOKED
        db.delete(grant)
    target.access_mode = AccessMode.OWN
    # Disconnect every channel so the scheduler stops uploading for them.
    for channel in db.query(YouTubeChannel).filter(YouTubeChannel.user_id == target.id).all():
        channel.status = ChannelStatus.REVOKED
        settings_row = channel.settings
        if settings_row:
            settings_row.enabled = False
    db.commit()
    return {"status": "terminated", "user_id": str(target.id), "email": target.email}
