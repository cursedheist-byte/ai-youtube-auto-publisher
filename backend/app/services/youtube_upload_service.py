"""Real Drive -> YouTube upload integration with conservative retry semantics."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import settings
from app.models import ChannelStatus, YouTubeChannel
from app.services.ai_provider import SEOMetadata
from app.services.drive_service import DriveSourceError, download_file
from app.services.youtube_oauth_service import YouTubeChannelError, get_credentials_for_channel

logger = logging.getLogger("ai_yt_publisher.youtube")


class YouTubeUploadError(Exception):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain

def _safe_youtube_error_text(value) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(api[_ -]?key|client_secret|refresh_token|access_token)[=:]\s*[^,;\s]+", r"\1=[REDACTED]", text)
    return text[:500]


def _youtube_http_error_details(exc: HttpError) -> tuple[str, str, str, list[tuple[str, str]]]:
    # Extract only safe, actionable fields from Google's JSON error response.
    raw = getattr(exc, "content", b"")
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    error = error if isinstance(error, dict) else {}
    code = _safe_youtube_error_text(error.get("code") or getattr(exc.resp, "status", ""))
    reason = _safe_youtube_error_text(error.get("reason"))
    message = _safe_youtube_error_text(error.get("message"))
    items = []
    for item in error.get("errors") or []:
        if isinstance(item, dict):
            items.append((_safe_youtube_error_text(item.get("reason")), _safe_youtube_error_text(item.get("message"))))
    return code, reason, message, items

def _format_youtube_http_error(exc: HttpError) -> str:
    code, reason, message, items = _youtube_http_error_details(exc)
    parts = [part for part in (f"code={code}" if code else "", f"reason={reason}" if reason else "", f"message={message}" if message else "") if part]
    for item_reason, item_message in items:
        detail = "/".join(part for part in (item_reason, item_message) if part)
        if detail:
            parts.append(f"detail={detail}")
    return "; ".join(parts) or "No diagnostic details were provided by YouTube."

@dataclass(frozen=True)
class YouTubeVideoStatus:
    privacy_status: str | None
    processing_status: str | None


def inspect_youtube_video(db, channel: YouTubeChannel, youtube_video_id: str) -> YouTubeVideoStatus | None:
    """Best-effort status lookup. A lookup failure never invalidates a known upload."""
    try:
        credentials = get_credentials_for_channel(db, channel)
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        response = service.videos().list(part="status,processingDetails", id=youtube_video_id).execute()
        item = (response.get("items") or [None])[0]
        if not item:
            return None
        return YouTubeVideoStatus(
            privacy_status=(item.get("status") or {}).get("privacyStatus"),
            processing_status=(item.get("processingDetails") or {}).get("processingStatus"),
        )
    except Exception:
        logger.exception("Unable to inspect YouTube video status for channel=%s video=%s", channel.id, youtube_video_id)
        return None


def upload_video_file(db, channel: YouTubeChannel, drive_file_id: str, metadata: SEOMetadata) -> str:
    if not channel.oauth_refresh_token:
        raise YouTubeUploadError("YouTube authorization is missing. Reconnect the channel.")
    try:
        credentials = get_credentials_for_channel(db, channel)
    except YouTubeChannelError as exc:
        raise YouTubeUploadError(str(exc)) from exc

    fd, temp_path = tempfile.mkstemp(prefix="yt-upload-", suffix=".video")
    os.close(fd)
    try:
        try:
            download_file(drive_file_id, temp_path)
        except DriveSourceError as exc:
            raise YouTubeUploadError(str(exc)) from exc

        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id or settings.youtube_default_category_id,
            },
            "status": {"privacyStatus": settings.youtube_privacy_status},
        }
        media = MediaFileUpload(temp_path, resumable=True, chunksize=settings.youtube_upload_chunk_bytes)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        try:
            response = None
            while response is None:
                _, response = request.next_chunk(num_retries=2)
            youtube_video_id = response.get("id") if response else None
            if not youtube_video_id:
                raise YouTubeUploadError("YouTube accepted the upload but returned no video ID.", uncertain=True)
            return youtube_video_id
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", None)
            if status_code in (401, 403):
                if status_code == 401:
                    channel.status = ChannelStatus.REVOKED
                    db.commit()
                raise YouTubeUploadError(
                    f"YouTube authorization/permission error (HTTP {status_code}). Reconnect or check channel permissions."
                ) from exc
            if status_code == 400:
                diagnostics = _format_youtube_http_error(exc)
                logger.warning("YouTube upload rejected (HTTP 400): %s", diagnostics)
                raise YouTubeUploadError(f"YouTube rejected the upload (HTTP 400): {diagnostics}") from exc
            if status_code == 404:
                raise YouTubeUploadError("YouTube rejected the upload (HTTP 404). Check the channel and request.") from exc
            # 429/5xx can be retriable in principle, but after an upload request
            # has begun the outcome can be ambiguous. Never start a second upload.
            uncertain = status_code == 429 or status_code is None or status_code >= 500
            raise YouTubeUploadError(
                f"YouTube API error during upload (HTTP {status_code})." if uncertain else f"YouTube API error during upload (HTTP {status_code}).",
                uncertain=uncertain,
            ) from exc
        except YouTubeUploadError:
            raise
        except Exception as exc:
            raise YouTubeUploadError(
                f"Upload interrupted before confirmation from YouTube: {exc}", uncertain=True
            ) from exc
        finally:
            # MediaFileUpload keeps its own open handle on temp_path for the
            # whole resumable upload. On Windows that handle locks the file,
            # so it MUST be released before os.remove() or cleanup fails
            # with WinError 32. Closing here (always, success or failure)
            # guarantees the lock is gone before the outer finally deletes
            # the temp file.
            try:
                media._fd.close()
            except Exception:
                logger.debug("Could not close MediaFileUpload handle directly.", exc_info=True)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            # Last-resort on Windows: a lingering lock should no longer be
            # possible after the explicit close above, but never let temp
            # file cleanup break an already-completed upload flow.
            logger.debug("Temp upload file %s still locked; left for OS cleanup.", temp_path, exc_info=True)
