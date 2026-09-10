import json
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.config import settings
from app.deps import get_current_user
from app.models import Category, ChannelStatus, DriveSource, DriveVideo, UploadHistory, UploadStatus, User, YouTubeChannel
from app.services.access_service import reserve_admin_upload, finish_admin_upload
from app.schemas import EligibleVideoOut, UploadHistoryOut, UploadNowRequest, UploadNowResult
from app.services.ai_provider import AIProviderError, get_ai_provider
from app.services.video_processing import generate_video_metadata
from app.services.upload_service import claim_upload, mark_failed, mark_success, record_metadata, set_uploading
from app.services.youtube_upload_service import YouTubeUploadError, inspect_youtube_video, upload_video_file

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _own_channel(db: Session, channel_id: uuid.UUID, user: User) -> YouTubeChannel:
    channel = db.get(YouTubeChannel, channel_id)
    if not channel or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.get("/channels/{channel_id}/eligible-videos", response_model=list[EligibleVideoOut])
def list_eligible_videos(
    channel_id: uuid.UUID,
    category_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _own_channel(db, channel_id, user)
    if category_id is not None and db.get(Category, category_id) is None:
        raise HTTPException(status_code=400, detail="Category not found")
    other_video = aliased(DriveVideo)
    uploaded = exists().where(
        UploadHistory.channel_id == channel_id,
        UploadHistory.drive_video_id == other_video.id,
        other_video.drive_file_id == DriveVideo.drive_file_id,
    )
    rows = (
        db.query(DriveVideo, DriveSource.name)
        .join(DriveSource, DriveSource.id == DriveVideo.source_id)
        .filter(DriveSource.status == "active", DriveVideo.is_valid_video.is_(True), ~uploaded)
        .filter(DriveSource.category_id == category_id if category_id else DriveSource.category_id.isnot(None))
        .order_by(func.random())
        .limit(limit)
        .all()
    )
    return [EligibleVideoOut(id=v.id, filename=v.filename, source_name=source, size_bytes=v.size_bytes, duration_seconds=v.duration_seconds) for v, source in rows]


@router.get("/channels/{channel_id}/history", response_model=list[UploadHistoryOut])
def list_history(
    channel_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _own_channel(db, channel_id, user)
    rows = (
        db.query(UploadHistory)
        .filter(UploadHistory.channel_id == channel_id)
        .order_by(UploadHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [UploadHistoryOut.from_model(row) for row in rows]


@router.post("/channels/{channel_id}/upload-now", response_model=UploadNowResult)
def upload_now(
    channel_id: uuid.UUID,
    payload: UploadNowRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    channel = _own_channel(db, channel_id, user)
    if channel.status != ChannelStatus.CONNECTED:
        raise HTTPException(status_code=409, detail="Channel authorization is not connected. Reconnect the channel first.")

    video = None
    if payload and payload.drive_video_id:
        video = db.get(DriveVideo, payload.drive_video_id)
        if not video or not video.is_valid_video:
            raise HTTPException(status_code=404, detail="Eligible Drive video not found")
        source = db.get(DriveSource, video.source_id)
        if not source or source.status != "active":
            raise HTTPException(status_code=409, detail="The selected video's Drive source is inactive.")
        if source.category_id is None:
            raise HTTPException(status_code=409, detail="This Drive source has no category. Ask an admin to assign one before uploading.")
        if payload.category_id is not None:
            if db.get(Category, payload.category_id) is None:
                raise HTTPException(status_code=400, detail="Category not found")
            if source.category_id != payload.category_id:
                raise HTTPException(status_code=409, detail="The selected video is not in the requested category.")
    else:
        if payload and payload.category_id is not None and db.get(Category, payload.category_id) is None:
            raise HTTPException(status_code=400, detail="Category not found")
        other_video = aliased(DriveVideo)
        uploaded = exists().where(
            UploadHistory.channel_id == channel.id,
            UploadHistory.drive_video_id == other_video.id,
            other_video.drive_file_id == DriveVideo.drive_file_id,
        )
        video = (
            db.query(DriveVideo)
            .join(DriveSource, DriveSource.id == DriveVideo.source_id)
            .filter(DriveSource.status == "active", DriveVideo.is_valid_video.is_(True), ~uploaded)
            .filter(DriveSource.category_id == payload.category_id if payload and payload.category_id else DriveSource.category_id.isnot(None))
            .order_by(func.random())
            .first()
        )
        if not video:
            detail = "No eligible videos are available in this category for this channel." if payload and payload.category_id else "No eligible Drive videos are available for this channel."
            raise HTTPException(status_code=409, detail=detail)

    try:
        reservation = reserve_admin_upload(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    history, reason = claim_upload(db, channel.id, video.id, allow_failed_retry=True)
    if history is None:
        finish_admin_upload(db, reservation, False)
        if reason == "already_success":
            raise HTTPException(status_code=409, detail="This Drive video has already been uploaded to this YouTube channel.")
        if reason == "already_in_progress":
            raise HTTPException(status_code=409, detail="This video is already being uploaded to this channel.")
        if reason == "uncertain_failure":
            raise HTTPException(status_code=409, detail="The previous upload outcome is uncertain. Automatic retry is disabled to avoid creating a duplicate YouTube video.")
        raise HTTPException(status_code=409, detail="This video already has an upload attempt for this channel.")

    try:
        provider = get_ai_provider(user)
        metadata = generate_video_metadata(
            provider,
            filename=video.filename,
            source_name=video.source.name,
            mime_type=video.mime_type,
            size_bytes=video.size_bytes,
            duration_seconds=video.duration_seconds,
        )
        record_metadata(db, history, metadata.title, metadata.description, metadata.tags)
        set_uploading(db, history)
        youtube_id = upload_video_file(db, channel, video.drive_file_id, metadata)
        mark_success(db, history, youtube_id)
        yt_status = inspect_youtube_video(db, channel, youtube_id)
        if yt_status:
            history.youtube_privacy_status = yt_status.privacy_status
            history.youtube_processing_status = yt_status.processing_status
            history.youtube_status_checked_at = datetime.now(timezone.utc)
            db.commit()
        finish_admin_upload(db, reservation, True)
        return UploadNowResult(
            status=history.status.value if hasattr(history.status, "value") else str(history.status),
            message=("Video uploaded successfully." if history.youtube_privacy_status in (None, settings.youtube_privacy_status) else f"Video uploaded; YouTube reports privacy as {history.youtube_privacy_status}."),
            upload=UploadHistoryOut.from_model(history),
        )
    except AIProviderError as exc:
        finish_admin_upload(db, reservation, False)
        mark_failed(db, history, str(exc))
        return UploadNowResult(status=history.status.value if hasattr(history.status, "value") else str(history.status), message=str(exc), upload=UploadHistoryOut.from_model(history))
    except YouTubeUploadError as exc:
        finish_admin_upload(db, reservation, False)
        mark_failed(db, history, str(exc), uncertain=exc.uncertain)
        return UploadNowResult(status=history.status.value if hasattr(history.status, "value") else str(history.status), message=str(exc), upload=UploadHistoryOut.from_model(history))
    except Exception as exc:
        finish_admin_upload(db, reservation, False)
        mark_failed(db, history, f"Unexpected upload failure: {exc}")
        return UploadNowResult(status="failed", message=f"Unexpected upload failure: {exc}", upload=UploadHistoryOut.from_model(history))
