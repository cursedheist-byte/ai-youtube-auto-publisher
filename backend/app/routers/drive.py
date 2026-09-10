import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Category, DriveSource, DriveVideo, UploadHistory, User
from app.schemas import (
    DriveSourceCreate,
    DriveSourceOut,
    DriveSourceUpdate,
    DriveVideoOut,
    ScanResult,
)
from app.services.drive_service import DriveSourceError, extract_folder_id, list_video_files

router = APIRouter(
    prefix="/api/admin/drive-sources",
    tags=["drive-sources"],
    dependencies=[Depends(require_admin)],
)


def _to_out(source: DriveSource, video_count: int) -> DriveSourceOut:
    return DriveSourceOut(
        id=source.id,
        name=source.name,
        drive_folder_id=source.drive_folder_id,
        status=source.status,
        video_count=video_count,
        last_scanned_at=source.last_scanned_at,
        last_scan_error=source.last_scan_error,
        category_id=source.category_id,
        category_name=source.category.name if source.category else None,
        created_at=source.created_at,
    )


def _get_source_or_404(db: Session, source_id: uuid.UUID) -> DriveSource:
    source = db.get(DriveSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drive source not found")
    return source


def _video_count(db: Session, source_id: uuid.UUID) -> int:
    return db.query(func.count(DriveVideo.id)).filter(DriveVideo.source_id == source_id).scalar() or 0


@router.get("", response_model=list[DriveSourceOut])
def list_sources(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    sources = db.query(DriveSource).order_by(DriveSource.created_at.desc()).all()
    counts = dict(
        db.query(DriveVideo.source_id, func.count(DriveVideo.id)).group_by(DriveVideo.source_id).all()
    )
    return [_to_out(s, counts.get(s.id, 0)) for s in sources]


@router.post("", response_model=DriveSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: DriveSourceCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    try:
        folder_id = extract_folder_id(payload.folder_link)
    except DriveSourceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    category = db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    source = DriveSource(owner_admin_id=admin.id, name=payload.name, drive_folder_id=folder_id, category_id=category.id)
    db.add(source)
    db.commit()
    db.refresh(source)
    return _to_out(source, video_count=0)


@router.patch("/{source_id}", response_model=DriveSourceOut)
def update_source(
    source_id: uuid.UUID,
    payload: DriveSourceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    source = _get_source_or_404(db, source_id)

    if payload.name is not None:
        source.name = payload.name
    if payload.status is not None:
        source.status = payload.status
    if "category_id" in payload.model_fields_set:
        if payload.category_id is not None and db.get(Category, payload.category_id) is None:
            raise HTTPException(status_code=400, detail="Category not found")
        source.category_id = payload.category_id
    db.commit()
    db.refresh(source)
    return _to_out(source, _video_count(db, source_id))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    source = _get_source_or_404(db, source_id)

    referenced = (
        db.query(UploadHistory.id)
        .join(DriveVideo, DriveVideo.id == UploadHistory.drive_video_id)
        .filter(DriveVideo.source_id == source_id)
        .first()
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source contains videos with upload history. Disable the source instead of deleting it so historical records and duplicate protection remain intact.",
        )
    db.query(DriveVideo).filter(DriveVideo.source_id == source_id).delete(synchronize_session=False)
    db.delete(source)
    db.commit()
    return None


@router.get("/{source_id}/videos", response_model=list[DriveVideoOut])
def list_videos(source_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    _get_source_or_404(db, source_id)
    videos = (
        db.query(DriveVideo)
        .filter(DriveVideo.source_id == source_id)
        .order_by(DriveVideo.discovered_at.desc())
        .all()
    )
    return videos


@router.post("/{source_id}/scan", response_model=ScanResult)
def scan_source(source_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """
    Discovers video files in this source's Drive folder and upserts them
    into drive_videos, keyed by (source_id, drive_file_id) -- never by
    filename. Safe to run repeatedly: existing files are updated in place
    (filename/size/checksum can change without the file ID changing),
    new files are inserted, and nothing is ever duplicated because of the
    DB-level UNIQUE(source_id, drive_file_id) constraint.

    On any Drive-side failure (folder deleted, not shared, auth/config
    problem), the error is recorded on the source and returned in the
    response rather than raising a 500 -- scanning a broken source is an
    expected, recoverable event, not a server error.
    """
    source = _get_source_or_404(db, source_id)

    try:
        video_files = list_video_files(source.drive_folder_id)
    except DriveSourceError as exc:
        source.last_scan_error = str(exc)
        source.last_scanned_at = datetime.now(timezone.utc)
        db.commit()
        return ScanResult(
            new_videos=0,
            updated_videos=0,
            total_valid_videos=_video_count(db, source_id),
            error=str(exc),
        )

    existing_by_file_id = {
        v.drive_file_id: v
        for v in db.query(DriveVideo).filter(DriveVideo.source_id == source_id).all()
    }

    new_count = 0
    updated_count = 0
    seen_file_ids = set()

    for f in video_files:
        seen_file_ids.add(f["id"])
        drive_file_id = f["id"]
        filename = f.get("name", "untitled")
        mime_type = f.get("mimeType", "")
        size_bytes = int(f["size"]) if f.get("size") else None
        checksum = f.get("md5Checksum")
        duration_seconds = f.get("durationSeconds")

        video = existing_by_file_id.get(drive_file_id)
        if video is None:
            db.add(
                DriveVideo(
                    source_id=source_id,
                    drive_file_id=drive_file_id,
                    filename=filename,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    checksum=checksum,
                    duration_seconds=duration_seconds,
                    is_valid_video=True,
                )
            )
            new_count += 1
        else:
            changed = (
                video.filename != filename
                or video.mime_type != mime_type
                or video.size_bytes != size_bytes
                or video.checksum != checksum
                or video.duration_seconds != duration_seconds
            )
            if changed or not video.is_valid_video:
                video.filename = filename
                video.mime_type = mime_type
                video.size_bytes = size_bytes
                video.checksum = checksum
                video.duration_seconds = duration_seconds
                video.is_valid_video = True
                updated_count += 1

    # A successful complete Drive listing means records absent from it are no
    # longer usable candidates (deleted/moved/inaccessible). Keep the rows for
    # historical upload references, but make them ineligible instead of deleting
    # them. This preserves duplicate history while preventing repeated failures.
    for video in existing_by_file_id.values():
        if video.drive_file_id not in seen_file_ids and video.is_valid_video:
            video.is_valid_video = False
            updated_count += 1

    source.last_scan_error = None
    source.last_scanned_at = datetime.now(timezone.utc)
    db.commit()

    return ScanResult(
        new_videos=new_count,
        updated_videos=updated_count,
        total_valid_videos=_video_count(db, source_id),
        error=None,
    )
