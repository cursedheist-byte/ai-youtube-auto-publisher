"""Daily automation and retry orchestration for the single-process APScheduler."""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, text
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.database import SessionLocal
from app.models import (
    AutomationRun, AutomationSchedule, AutomationSettings, ChannelStatus, DriveSource, DriveVideo,
    FailedUpload, UploadHistory, UploadStatus, User, YouTubeChannel,
)
from app.services import schedule_logic
from app.services.ai_provider import AIProviderError, get_ai_provider
from app.services.video_processing import generate_video_metadata
from app.services.upload_service import claim_upload, mark_failed, mark_success, record_metadata, set_uploading
from app.services.youtube_upload_service import YouTubeUploadError, upload_video_file
from app.services.access_service import reserve_admin_upload, finish_admin_upload

logger = logging.getLogger("ai_yt_publisher.automation")


def _eligible_query(db: Session, channel_id, category_id=None):
    other_video = aliased(DriveVideo)
    uploaded = exists().where(
        UploadHistory.channel_id == channel_id,
        UploadHistory.drive_video_id == other_video.id,
        other_video.drive_file_id == DriveVideo.drive_file_id,
    )
    return (
        db.query(DriveVideo)
        .join(DriveSource, DriveSource.id == DriveVideo.source_id)
        .filter(DriveSource.status == "active", DriveVideo.is_valid_video.is_(True), ~uploaded)
        .filter(DriveSource.category_id == category_id if category_id else DriveSource.category_id.isnot(None))
    )


def eligible_videos(db: Session, channel_id, limit: int = 100, category_id=None):
    videos = _eligible_query(db, channel_id, category_id=category_id).all()
    random.shuffle(videos)
    if len(videos) <= limit:
        return videos

    # Prefer one video from each distinct active source before filling the
    # remainder randomly. This avoids repeatedly consuming one source while
    # other eligible sources are available, without making selection deterministic.
    by_source = {}
    for video in videos:
        by_source.setdefault(video.source_id, []).append(video)
    source_ids = list(by_source)
    random.shuffle(source_ids)
    selected = []
    while source_ids and len(selected) < limit:
        next_sources = []
        for source_id in source_ids:
            bucket = by_source[source_id]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop())
            if bucket:
                next_sources.append(source_id)
        source_ids = next_sources
    return selected


def _claim_daily_run(db: Session, channel_id, run_day: date, slot_index: int = 0):
    """Claim a specific scheduling slot for a channel/day.

    Uniqueness is (channel_id, run_date, slot_index) so two anchors per day
    each get their own run, and concurrent processes/ticks can never create
    the same slot twice.
    """
    existing = (
        db.query(AutomationRun)
        .filter(
            AutomationRun.channel_id == channel_id,
            AutomationRun.run_date == run_day,
            AutomationRun.slot_index == slot_index,
        )
        .with_for_update()
        .first()
    )
    if existing:
        return existing, False
    run = AutomationRun(
        channel_id=channel_id,
        run_date=run_day,
        slot_index=slot_index,
        status="failed",
        started_at=datetime.now(timezone.utc),
        videos_attempted=0,
        videos_uploaded=0,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
        return run, True
    except Exception:
        existing = (
            db.query(AutomationRun)
            .filter(
                AutomationRun.channel_id == channel_id,
                AutomationRun.run_date == run_day,
                AutomationRun.slot_index == slot_index,
            )
            .with_for_update()
            .first()
        )
        if existing:
            return existing, False
        raise


def get_schedule(db: Session):
    """Return the (single) admin schedule row, creating a default if absent.

    Default anchors 09:00 and 18:00 Asia/Kolkata. The singleton guarantee
    comes from a unique constraint + advisory lock so two cold starts cannot
    create two rows.
    """
    row = db.query(AutomationSchedule).first()
    if row:
        return row
    # Serialize creation across processes.
    db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": 71642003})
    try:
        row = db.query(AutomationSchedule).first()
        if row is None:
            row = AutomationSchedule(singleton=True, anchor_1="09:00", anchor_2="18:00", timezone=schedule_logic.DEFAULT_TIMEZONE)
            db.add(row)
            db.commit()
            db.refresh(row)
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": 71642003})
    return row


def process_channel(db: Session, channel: YouTubeChannel, *, run_day: date | None = None, slot_index: int = 0, count_override: int | None = None) -> AutomationRun | None:
    run_day = run_day or datetime.now(ZoneInfo(settings.scheduler_timezone)).date()
    settings_row = channel.settings
    if not settings_row or not settings_row.enabled or channel.status != ChannelStatus.CONNECTED:
        return None

    run, created = _claim_daily_run(db, channel.id, run_day, slot_index)
    if not created:
        logger.info("[scheduler] channel=%s already has run slot=%s for %s; skipping", channel.id, slot_index, run_day)
        return run

    count = max(1, min(count_override if count_override is not None else settings_row.daily_upload_count, 10))
    videos = eligible_videos(db, channel.id, limit=max(count * 3, count), category_id=settings_row.category_id)
    if not videos:
        run.status = "no_eligible_videos"
        run.notes = "No eligible videos were available in the selected category." if settings_row.category_id else "No eligible videos were available from active Drive sources."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run

    attempted = uploaded = 0
    errors = []
    provider = None
    for video in videos:
        if attempted >= count:
            break
        history, reason = claim_upload(db, channel.id, video.id, run_id=run.id, allow_failed_retry=False)
        if history is None:
            continue
        attempted += 1
        reservation = None
        try:
            reservation = reserve_admin_upload(db, channel.user)
            if provider is None:
                provider = get_ai_provider(channel.user)
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
            finish_admin_upload(db, reservation, True)
            uploaded += 1
        except ValueError as exc:
            mark_failed(db, history, str(exc))
            errors.append(f"{video.filename}: {exc}")
        except AIProviderError as exc:
            finish_admin_upload(db, locals().get("reservation"), False)
            mark_failed(db, history, str(exc))
            errors.append(f"{video.filename}: {exc}")
        except YouTubeUploadError as exc:
            finish_admin_upload(db, locals().get("reservation"), False)
            mark_failed(db, history, str(exc), uncertain=exc.uncertain)
            errors.append(f"{video.filename}: {exc}")
        except Exception as exc:
            finish_admin_upload(db, locals().get("reservation"), False)
            logger.exception("Unexpected upload failure for channel=%s video=%s", channel.id, video.id)
            mark_failed(db, history, f"Unexpected upload failure: {exc}")
            errors.append(f"{video.filename}: unexpected failure")

    run.videos_attempted = attempted
    run.videos_uploaded = uploaded
    if uploaded == 0:
        run.status = "failed" if errors else "no_eligible_videos"
    elif errors:
        run.status = "partial"
    else:
        run.status = "success"
    run.notes = "; ".join(errors)[:10000] if errors else None
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run


def _try_job_lock(db: Session, key: int) -> bool:
    return bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())


def _unlock_job(db: Session, key: int) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    db.commit()


def run_daily_automation() -> None:
    """Watchdog tick: claim and run every due scheduling slot.

    Runs every minute from main.py. Because due slots are computed from the
    admin's two anchor times with a per-day deterministic distribution, a
    Render cold start (or any restart) just calls this tick and it catches
    up all missed slots of today without duplicating any upload — every slot
    is claimed exactly once via (channel_id, run_date, slot_index).
    """
    db = SessionLocal()
    lock_key = 71642001
    try:
        if not _try_job_lock(db, lock_key):
            logger.warning("[scheduler] daily job already running in another process; skipping")
            return
        schedule = get_schedule(db)
        now_utc = datetime.now(timezone.utc)
        tz = ZoneInfo(schedule.timezone)
        run_day = now_utc.astimezone(tz).date()
        channels = (
            db.query(YouTubeChannel)
            .join(AutomationSettings, AutomationSettings.channel_id == YouTubeChannel.id)
            .filter(AutomationSettings.enabled.is_(True), YouTubeChannel.status == ChannelStatus.CONNECTED)
            .all()
        )
        if not channels:
            return
        logger.info("[scheduler] watchdog tick: %d enabled channels for %s (%s)", len(channels), run_day, schedule.timezone)
        for channel in channels:
            try:
                settings_row = channel.settings
                count = max(1, min(settings_row.daily_upload_count, 10))
                existing = {
                    r.slot_index
                    for r in db.query(AutomationRun)
                    .filter(AutomationRun.channel_id == channel.id, AutomationRun.run_date == run_day)
                    .all()
                }
                due = schedule_logic.due_slot_indexes(
                    now_utc=now_utc,
                    channel_key=str(channel.id),
                    run_date=run_day,
                    count=count,
                    anchor_1=schedule.anchor_1,
                    anchor_2=schedule.anchor_2,
                    tz_name=schedule.timezone,
                    done_slot_indexes=existing,
                )
                for slot_index in due:
                    process_channel(db, channel, run_day=run_day, slot_index=slot_index, count_override=1)
            except Exception:
                db.rollback()
                logger.exception("[scheduler] channel=%s failed; continuing", channel.id)
    finally:
        try:
            _unlock_job(db, lock_key)
        except Exception:
            db.rollback()
        db.close()


def retry_failed_uploads() -> None:
    """Retry only deterministic failures; never blindly retry uncertain outcomes."""
    db = SessionLocal()
    lock_key = 71642002
    try:
        if not _try_job_lock(db, lock_key):
            logger.warning("[scheduler] retry job already running in another process; skipping")
            return
        # A process crash can leave an upload in UPLOADING. It is not safe to
        # turn that into a normal retry because YouTube may already have created
        # the video. Move only stale uploads to explicit UNCERTAIN review state.
        stale_cutoff = datetime.now(timezone.utc).timestamp() - (settings.upload_stale_after_minutes * 60)
        stale = (
            db.query(UploadHistory)
            .filter(UploadHistory.status == UploadStatus.UPLOADING, UploadHistory.last_attempt_at.is_not(None),
                    func.extract("epoch", UploadHistory.last_attempt_at) < stale_cutoff)
            .with_for_update()
            .all()
        )
        for history in stale:
            mark_failed(db, history, "Upload process stopped before YouTube confirmed the outcome; manual review is required.", uncertain=True)

        failed = (
            db.query(FailedUpload)
            .join(UploadHistory, FailedUpload.upload_history_id == UploadHistory.id)
            .filter(FailedUpload.resolved.is_(False), FailedUpload.retry_count < settings.max_upload_retries,
                    UploadHistory.status == UploadStatus.FAILED)
            .with_for_update(of=(FailedUpload, UploadHistory))
            .all()
        )
        for failure in failed:
            history = failure.upload_history
            if not history or history.status != UploadStatus.FAILED:
                continue
            channel = history.channel
            video = history.drive_video
            if not channel or not video or channel.status != ChannelStatus.CONNECTED:
                continue
            try:
                history.status = UploadStatus.PENDING
                failure.retry_count += 1
                failure.last_retry_at = datetime.now(timezone.utc)
                db.commit()
                reservation = reserve_admin_upload(db, channel.user)
                provider = get_ai_provider(channel.user)
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
                finish_admin_upload(db, reservation, True)
            except AIProviderError as exc:
                finish_admin_upload(db, locals().get("reservation"), False)
                if not exc.retryable:
                    failure.retry_count = settings.max_upload_retries
                mark_failed(db, history, str(exc), increment_retry=False)
                failure.last_retry_at = datetime.now(timezone.utc)
                db.commit()
            except YouTubeUploadError as exc:
                finish_admin_upload(db, locals().get("reservation"), False)
                mark_failed(db, history, str(exc), uncertain=exc.uncertain, increment_retry=False)
                failure.last_retry_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as exc:
                finish_admin_upload(db, locals().get("reservation"), False)
                mark_failed(db, history, f"Retry failed: {exc}", increment_retry=False)
                failure.last_retry_at = datetime.now(timezone.utc)
                db.commit()
    finally:
        try:
            _unlock_job(db, lock_key)
        except Exception:
            db.rollback()
        db.close()
