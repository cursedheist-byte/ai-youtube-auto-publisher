"""One-off manual upload of a SINGLE video via the existing pipeline. Delete after run."""
import logging

logging.basicConfig(level=logging.INFO)

from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import YouTubeChannel
from app.models import DriveVideo, UploadHistory
from app.services.ai_provider import AIProviderError, get_ai_provider, VideoContext
from app.services.upload_service import claim_upload, mark_failed, mark_success, record_metadata, set_uploading
from app.services.youtube_upload_service import YouTubeUploadError, inspect_youtube_video, upload_video_file

CHANNEL_ID = "07cc7da9-ec53-4e51-8782-50dd8eb2e6e7"
VIDEO_ID = "bcc826d6-deaf-426b-b97e-67a516a5843f"

db = SessionLocal()
video = db.get(DriveVideo, VIDEO_ID)
channel = db.get(YouTubeChannel, CHANNEL_ID)
assert video and video.is_valid_video, "Selected video not eligible"
assert channel, "Channel not found"

history, reason = claim_upload(db, channel.id, video.id, allow_failed_retry=True)
if history is None:
    print("CLAIM FAILED:", reason)
    raise SystemExit(1)
print("[1] CLAIMED upload slot:", history.id)

try:
    provider = get_ai_provider()
    metadata = provider.generate_metadata(
        VideoContext(
            filename=video.filename,
            source_name=video.source.name,
            mime_type=video.mime_type,
            size_bytes=video.size_bytes,
            duration_seconds=video.duration_seconds,
        )
    )
    print("[2] GEMINI metadata:")
    print("    title:", metadata.title)
    print("    tags:", metadata.tags)
    print("    description (first 300 chars):", metadata.description[:300].replace(chr(10), " | "))
    record_metadata(db, history, metadata.title, metadata.description, metadata.tags)
    set_uploading(db, history)

    print("[3] Uploading to YouTube (this may take a while)...")
    youtube_id = upload_video_file(db, channel, video.drive_file_id, metadata)
    print("    YouTube video ID:", youtube_id)
    mark_success(db, history, youtube_id)

    yt_status = inspect_youtube_video(db, channel, youtube_id)
    if yt_status:
        history.youtube_privacy_status = yt_status.privacy_status
        history.youtube_processing_status = yt_status.processing_status
        history.youtube_status_checked_at = datetime.now(timezone.utc)
        db.commit()
    print("[4] YouTube processing status:", yt_status.processing_status if yt_status else "unknown")
    print("[5] FINAL DB UploadStatus:", history.status.value)
    print("DONE OK")
except AIProviderError as exc:
    mark_failed(db, history, str(exc))
    print("FAILED (AI):", exc)
    print("FINAL DB UploadStatus:", history.status.value)
except YouTubeUploadError as exc:
    mark_failed(db, history, str(exc), uncertain=exc.uncertain)
    print("FAILED (YouTube, uncertain=%s):" % exc.uncertain, exc)
    print("FINAL DB UploadStatus:", history.status.value)
except Exception as exc:
    mark_failed(db, history, "Unexpected upload failure: %s" % exc)
    print("FAILED (unexpected):", exc)
    print("FINAL DB UploadStatus:", history.status.value)
finally:
    db.close()
