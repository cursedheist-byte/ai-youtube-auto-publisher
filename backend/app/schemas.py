import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, ConfigDict, Field

from app.models import SourceStatus, UserRole
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    created_at: datetime
    updated_at: datetime
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminDashboard(BaseModel):
    total_drive_sources: int
    total_discovered_videos: int
    connected_youtube_channels: int
    todays_uploads: int
    failed_uploads: int
    automation_status: str


class AutomationScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    anchor_1: str
    anchor_2: str
    timezone: str
    updated_at: datetime


class AutomationScheduleUpdate(BaseModel):
    anchor_1: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    anchor_2: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


# --- Drive sources ---


class DriveSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    folder_link: str = Field(min_length=1, description="Full Drive folder URL or a bare folder ID")
    category_id: uuid.UUID


class DriveSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: SourceStatus | None = None
    category_id: uuid.UUID | None = None


class DriveSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    drive_folder_id: str
    category_id: uuid.UUID | None
    category_name: str | None
    status: SourceStatus
    video_count: int
    last_scanned_at: datetime | None
    last_scan_error: str | None
    created_at: datetime


class DriveVideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    drive_file_id: str
    filename: str
    mime_type: str
    size_bytes: int | None
    checksum: str | None
    duration_seconds: int | None
    is_valid_video: bool
    discovered_at: datetime


class ScanResult(BaseModel):
    new_videos: int
    updated_videos: int
    total_valid_videos: int
    error: str | None = None


# --- YouTube channels ---


class YouTubeChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    youtube_channel_id: str
    channel_title: str
    status: str
    connected_at: datetime


class AutomationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: uuid.UUID
    enabled: bool
    daily_upload_count: int
    category_id: uuid.UUID | None


class SlotPlanOut(BaseModel):
    slot_index: int
    scheduled_at_utc: datetime


class AutomationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    daily_upload_count: int | None = Field(default=None, ge=1, le=10)
    category_id: uuid.UUID | None = None


class ChannelWithSettingsOut(BaseModel):
    channel: YouTubeChannelOut
    settings: AutomationSettingsOut


class OAuthStartOut(BaseModel):
    authorization_url: str


# --- Uploads / automation ---

class EligibleVideoOut(BaseModel):
    id: uuid.UUID
    filename: str
    source_name: str
    size_bytes: int | None
    duration_seconds: int | None


class UploadHistoryOut(BaseModel):
    id: uuid.UUID
    drive_video_id: uuid.UUID
    drive_file_id: str
    filename: str
    youtube_video_id: str | None
    generated_title: str | None
    generated_description: str | None
    generated_tags: list[str]
    status: str
    error_message: str | None
    uploaded_at: datetime | None
    last_attempt_at: datetime | None
    youtube_privacy_status: str | None
    youtube_processing_status: str | None
    youtube_status_checked_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, row):
        import json
        try:
            tags = json.loads(row.generated_tags or "[]")
            if not isinstance(tags, list):
                tags = []
        except (TypeError, ValueError):
            tags = []
        return cls(
            id=row.id,
            drive_video_id=row.drive_video_id,
            drive_file_id=row.drive_video.drive_file_id,
            filename=row.drive_video.filename,
            youtube_video_id=row.youtube_video_id,
            generated_title=row.generated_title,
            generated_description=row.generated_description,
            generated_tags=tags,
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            error_message=row.error_message,
            uploaded_at=row.uploaded_at,
            last_attempt_at=row.last_attempt_at,
            youtube_privacy_status=row.youtube_privacy_status,
            youtube_processing_status=row.youtube_processing_status,
            youtube_status_checked_at=row.youtube_status_checked_at,
            created_at=row.created_at,
        )


class UploadNowRequest(BaseModel):
    drive_video_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None


class UploadNowResult(BaseModel):
    status: str
    message: str
    upload: UploadHistoryOut


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_date: date
    status: str
    videos_attempted: int
    videos_uploaded: int
    notes: str | None
    started_at: datetime | None
    finished_at: datetime | None
    slot_index: int = 0


class CredentialSettingsUpdate(BaseModel):
    google_client_id: str | None = Field(default=None, max_length=500)
    google_client_secret: str | None = Field(default=None, max_length=2000)
    openrouter_api_key: str | None = Field(default=None, max_length=2000)

class CredentialSettingsOut(BaseModel):
    access_mode: str
    google_client_id_configured: bool
    google_client_secret_configured: bool
    openrouter_api_key_configured: bool
    daily_video_limit: int | None = None
    channel_limit: int | None = None
class AccessCodeRedeem(BaseModel):
    code: str = Field(min_length=20, max_length=200)

class AccessCodeCreated(BaseModel):
    code: str
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
class AccessCodeOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    redeemed_at: datetime | None
    redeemed_by_user_id: uuid.UUID | None
    expires_at: datetime | None
    status: str
    channel_limit: int
    daily_video_limit: int
