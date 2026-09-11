"""
Google Drive integration using a service account (agreed simplification --
no per-admin OAuth dance for Drive, just a shared service-account identity
that admins grant Viewer access to on each folder).

Every function here raises DriveSourceError, never a raw Google exception,
so the router can always show the admin a plain-English reason instead of
a 500. Nothing in this module writes to the database -- it only talks to
Google and returns plain dicts/lists.
"""
import json
import logging
import os
import re
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Matches the folder ID out of the common Drive URL shapes, e.g.:
#   https://drive.google.com/drive/folders/1AbC-XyZ123?usp=sharing
#   https://drive.google.com/drive/u/0/folders/1AbC-XyZ123
#   https://drive.google.com/open?id=1AbC-XyZ123
_FOLDER_URL_PATTERNS = [
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
]
_BARE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


class DriveSourceError(Exception):
    """A Drive-related failure meant to be shown to the admin as-is."""


logger = logging.getLogger("ai_yt_publisher.drive")


def _load_service_account_info(key_path: str) -> dict:
    """
    Loads a Google service-account JSON key file, tolerating the two ways a
    Render Secret File commonly mangles it:
      1. the whole JSON wrapped in double quotes,
      2. the private_key's real newlines stored as literal backslash-n text.
    Only metadata (booleans/counts) may ever be logged from here -- never the
    private key or any credential value.
    """
    with open(key_path, "r", encoding="utf-8") as fh:
        raw = fh.read().strip()
    # Case 1: secret pasted as a JSON-string-wrapped value (e.g. via an env var).
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, str):
                raw = decoded.strip()
        except json.JSONDecodeError:
            pass
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DriveSourceError(
            "The service account key file is not valid JSON. Re-upload the "
            "original JSON key file to the Render Secret File unchanged."
        ) from exc
    if not isinstance(info, dict) or not info.get("private_key"):
        raise DriveSourceError(
            "The service account key file has no private_key field. "
            "Upload the full JSON key downloaded from Google Cloud Console."
        )
    # Case 2: literal "\\n" instead of real newlines inside the PEM.
    key = info["private_key"]
    if "\\n" in key and "\n" not in key:
        info["private_key"] = key.replace("\\n", "\n")
        logger.info("drive key: normalized literal backslash-n newlines in private_key")
    logger.info(
        "drive key loaded: fields=%s private_key_lines=%d",
        sorted(k for k in info if k != "private_key"),
        info["private_key"].count("\n"),
    )
    return info


def extract_folder_id(folder_link_or_id: str) -> str:
    """Accepts a full Drive folder URL or a bare folder ID and returns the ID."""
    value = (folder_link_or_id or "").strip()
    if not value:
        raise DriveSourceError("Folder link or ID cannot be empty.")

    for pattern in _FOLDER_URL_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)

    if _BARE_ID_PATTERN.match(value):
        return value

    raise DriveSourceError(
        "Couldn't find a folder ID in that input. Paste the full Drive folder URL "
        "(e.g. https://drive.google.com/drive/folders/<id>) or the bare folder ID."
    )


@lru_cache(maxsize=1)
def _get_drive_service():
    key_path = settings.google_service_account_json_path
    if not key_path:
        raise DriveSourceError(
            "GOOGLE_SERVICE_ACCOUNT_JSON_PATH is not set in the backend .env. "
            "See README's 'Google service account setup' section."
        )
    if not os.path.exists(key_path):
        raise DriveSourceError(f"Service account key file not found at: {key_path}")

    try:
        info = _load_service_account_info(key_path)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except DriveSourceError:
        raise
    except Exception as exc:  # malformed key material, unsupported key, etc.
        raise DriveSourceError(f"Couldn't initialize the Drive client: {exc}") from exc


def list_video_files(folder_id: str) -> list[dict]:
    """
    Lists every VIDEO file (mimeType starting with 'video/') directly inside
    the given Drive folder. Handles pagination internally.

    Returns a list of dicts: {id, name, mimeType, size, md5Checksum, durationSeconds}.
    Raises DriveSourceError with a human-readable reason for any failure:
    folder deleted, folder not shared with the service account, auth/config
    problems, or a generic Drive API error.
    """
    service = _get_drive_service()
    query = f"'{folder_id}' in parents and trashed = false"
    files: list[dict] = []
    page_token = None

    try:
        while True:
            response = (
                service.files()
                .list(
                    q=query,
                    fields=(
                        "nextPageToken, files(id, name, mimeType, size, md5Checksum, "
                        "videoMediaMetadata(durationMillis), "
                        "shortcutDetails(targetId, targetMimeType))"
                    ),
                    pageSize=200,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        status = exc.resp.status if exc.resp is not None else None
        if status == 404:
            raise DriveSourceError(
                "Folder not found. It may have been deleted, or the folder ID is wrong."
            ) from exc
        if status == 403:
            raise DriveSourceError(
                "Access denied. Share this Drive folder with the service account's "
                "email address (Viewer access is enough) and try again."
            ) from exc
        raise DriveSourceError(f"Google Drive API error (HTTP {status}): {exc}") from exc
    except DriveSourceError:
        raise
    except Exception as exc:  # network errors, unexpected client-library failures
        raise DriveSourceError(f"Couldn't reach Google Drive: {exc}") from exc

    resolved: list[dict] = []
    for f in files:
        mime_type = f.get("mimeType", "")
        if mime_type == "application/vnd.google-apps.shortcut":
            # Resolve shortcuts to their real files so a shortcut and the file
            # it points to are treated as ONE video (same Drive ID).
            target = _resolve_shortcut(service, f)
            if target is not None and target.get("mimeType", "").startswith("video/"):
                resolved.append(target)
        elif mime_type.startswith("video/"):
            resolved.append(f)

    for f in resolved:
        media = f.get("videoMediaMetadata") or {}
        duration_millis = media.get("durationMillis")
        f["durationSeconds"] = int(int(duration_millis) / 1000) if duration_millis else None
    return resolved


def _resolve_shortcut(service, shortcut: dict) -> dict | None:
    """
    Resolves a Drive shortcut item to its target file's real metadata.
    Returns the target's dict (with the target's real ID, name, mimeType),
    or None if the shortcut is broken (target deleted / inaccessible) so a
    single bad shortcut never breaks the whole folder scan.
    """
    details = shortcut.get("shortcutDetails") or {}
    target_id = details.get("targetId")
    if not target_id:
        return None
    try:
        return (
            service.files()
            .get(
                fileId=target_id,
                fields="id, name, mimeType, size, md5Checksum, videoMediaMetadata(durationMillis)",
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception:
        # Broken shortcut, deleted target, or no access for the service
        # account -- skip it instead of failing the scan.
        return None


def download_file(drive_file_id: str, destination_path: str) -> None:
    """
    Downloads a Drive file's bytes to a local path. Used by the upload
    pipeline (Phase 6) to stage a video before pushing it to YouTube --
    the two APIs are authenticated as different identities (service account
    for Drive, per-user OAuth for YouTube), so a direct pipe between them
    isn't possible; a short-lived local temp file is the realistic bridge.
    """
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_drive_service()
    try:
        request = service.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
        with open(destination_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
    except HttpError as exc:
        status = exc.resp.status if exc.resp is not None else None
        if status == 404:
            raise DriveSourceError("The video file no longer exists on Drive (deleted?).") from exc
        if status == 403:
            raise DriveSourceError("Access denied downloading the video file from Drive.") from exc
        raise DriveSourceError(f"Google Drive API error while downloading (HTTP {status}): {exc}") from exc
    except Exception as exc:
        raise DriveSourceError(f"Couldn't download the video file from Drive: {exc}") from exc
