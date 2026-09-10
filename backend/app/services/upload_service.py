"""Upload-history lifecycle and duplicate-safe claiming."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DriveVideo, FailedUpload, UploadHistory, UploadStatus

logger = logging.getLogger("ai_yt_publisher.uploads")


def claim_upload(db: Session, channel_id: uuid.UUID, drive_video_id: uuid.UUID, *, run_id=None, allow_failed_retry=True):
    """Claim a stable Drive file/channel pair without a check-then-upload race."""
    target = db.get(DriveVideo, drive_video_id)
    if target is None:
        return None, "video_not_found"

    # The DB trigger is the final cross-source guarantee. This query is the
    # application-level fast path and also handles historical rows discovered
    # through another DriveSource record for the same stable Drive file ID.
    stable_rows = (
        db.query(UploadHistory)
        .join(DriveVideo, UploadHistory.drive_video_id == DriveVideo.id)
        .filter(UploadHistory.channel_id == channel_id, DriveVideo.drive_file_id == target.drive_file_id)
        .with_for_update()
        .all()
    )
    existing = next((r for r in stable_rows if r.drive_video_id == drive_video_id), None)
    other = next((r for r in stable_rows if r.drive_video_id != drive_video_id), None)

    if other is not None:
        if other.status == UploadStatus.SUCCESS:
            return None, "already_success"
        if other.status in (UploadStatus.PENDING, UploadStatus.UPLOADING):
            return None, "already_in_progress"
        if other.status == UploadStatus.UNCERTAIN:
            return None, "uncertain_failure"
        return None, "already_claimed"

    if existing:
        if existing.status == UploadStatus.SUCCESS:
            return None, "already_success"
        if existing.status in (UploadStatus.PENDING, UploadStatus.UPLOADING):
            return None, "already_in_progress"
        if existing.status == UploadStatus.UNCERTAIN:
            return None, "uncertain_failure"
        if existing.status == UploadStatus.FAILED:
            if not allow_failed_retry:
                return None, "failed_retry_not_allowed"
            existing.status = UploadStatus.PENDING
            existing.error_message = None
            existing.run_id = run_id
            existing.last_attempt_at = datetime.now(timezone.utc)
            db.flush()
            db.commit()
            return existing, "retry_claimed"

    history = UploadHistory(
        channel_id=channel_id,
        drive_video_id=drive_video_id,
        run_id=run_id,
        status=UploadStatus.PENDING,
        last_attempt_at=datetime.now(timezone.utc),
    )
    try:
        with db.begin_nested():
            db.add(history)
            db.flush()
        db.commit()
        return history, "claimed"
    except IntegrityError:
        # Covers the local unique constraint and the PostgreSQL stable-ID trigger.
        db.rollback()
        winner = (
            db.query(UploadHistory)
            .join(DriveVideo, UploadHistory.drive_video_id == DriveVideo.id)
            .filter(UploadHistory.channel_id == channel_id, DriveVideo.drive_file_id == target.drive_file_id)
            .with_for_update()
            .first()
        )
        if winner is None:
            raise
        if winner.status == UploadStatus.SUCCESS:
            return None, "already_success"
        if winner.status in (UploadStatus.PENDING, UploadStatus.UPLOADING):
            return None, "already_in_progress"
        if winner.status == UploadStatus.UNCERTAIN:
            return None, "uncertain_failure"
        return None, "already_claimed"

def set_uploading(db: Session, history: UploadHistory) -> None:
    history.status = UploadStatus.UPLOADING
    history.last_attempt_at = datetime.now(timezone.utc)
    history.error_message = None
    db.commit()


def record_metadata(db: Session, history: UploadHistory, title: str, description: str, tags: list[str]) -> None:
    history.generated_title = title
    history.generated_description = description
    history.generated_tags = json.dumps(tags, ensure_ascii=False)
    db.commit()


def mark_success(db: Session, history: UploadHistory, youtube_video_id: str) -> None:
    history.last_attempt_at = datetime.now(timezone.utc)
    history.youtube_video_id = youtube_video_id
    history.status = UploadStatus.SUCCESS
    history.uploaded_at = datetime.now(timezone.utc)
    history.error_message = None
    failed = history.failed_upload
    if failed:
        failed.resolved = True
        failed.last_retry_at = datetime.now(timezone.utc)
    db.commit()


def mark_failed(db: Session, history: UploadHistory, message: str, *, uncertain: bool = False, increment_retry=False) -> None:
    clean = message[:10000]
    history.last_attempt_at = datetime.now(timezone.utc)
    history.status = UploadStatus.UNCERTAIN if uncertain else UploadStatus.FAILED
    history.error_message = clean
    failed = history.failed_upload
    if failed is None:
        failed = FailedUpload(upload_history_id=history.id, failure_reason=clean, retry_count=0, resolved=False)
        db.add(failed)
    else:
        failed.failure_reason = clean[:10000]
        failed.resolved = False
    if increment_retry:
        failed.retry_count += 1
        failed.last_retry_at = datetime.now(timezone.utc)
    db.commit()
