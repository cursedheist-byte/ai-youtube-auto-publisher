"""
Full database schema, as agreed in the architecture document.

Phase 1 only WRITES to `users`. The other tables are created now so the
schema is stable and future phases (Drive discovery, YouTube OAuth, AI
metadata, automation) are pure additions of logic on top of an unchanging
data model — not schema churn.

The duplicate-prevention guarantee lives here at the database level:
UploadHistory has UNIQUE(drive_video_id, youtube_channel_id).
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class AccessMode(str, enum.Enum):
    OWN = "own"
    ADMIN = "admin"

class AccessCodeStatus(str, enum.Enum):
    UNUSED = "unused"
    REDEEMED = "redeemed"
    REVOKED = "revoked"

class SourceStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    drive_sources: Mapped[list["DriveSource"]] = relationship(back_populates="category")

class ChannelStatus(str, enum.Enum):
    CONNECTED = "connected"
    REVOKED = "revoked"
    ERROR = "error"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class RunStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NO_ELIGIBLE_VIDEOS = "no_eligible_videos"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=UserRole.USER,
        nullable=False,
    )
    access_mode: Mapped[AccessMode] = mapped_column(
        Enum(AccessMode, name="access_mode", values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        default=AccessMode.OWN, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    drive_sources: Mapped[list["DriveSource"]] = relationship(back_populates="owner_admin")
    youtube_channels: Mapped[list["YouTubeChannel"]] = relationship(back_populates="user")
    credentials: Mapped["UserCredential | None"] = relationship(back_populates="user", uselist=False)
    access_grant: Mapped["AccessGrant | None"] = relationship(back_populates="user", uselist=False)

class UserCredential(Base):
    __tablename__ = "user_credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    google_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped["User"] = relationship(back_populates="credentials")

class AccessCode(Base):
    __tablename__ = "access_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[AccessCodeStatus] = mapped_column(Enum(AccessCodeStatus, name="access_code_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=AccessCodeStatus.UNUSED, nullable=False)
    channel_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    daily_video_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

class AccessGrant(Base):
    __tablename__ = "access_grants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    access_code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("access_codes.id"), unique=True, nullable=False)
    channel_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    daily_video_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="access_grant")

class DailyUploadQuota(Base):
    __tablename__ = "daily_upload_quotas"
    __table_args__ = (UniqueConstraint("user_id", "quota_date", name="uq_daily_quota_user_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    quota_date: Mapped[date] = mapped_column(Date, nullable=False)
    reserved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

class DriveSource(Base):
    __tablename__ = "drive_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    drive_folder_id: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=SourceStatus.ACTIVE, nullable=False
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set whenever a scan fails (folder deleted/inaccessible/auth error), cleared on the next successful scan.
    last_scan_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner_admin: Mapped["User"] = relationship(back_populates="drive_sources")
    category: Mapped["Category | None"] = relationship(back_populates="drive_sources")
    videos: Mapped[list["DriveVideo"]] = relationship(back_populates="source")


class DriveVideo(Base):
    __tablename__ = "drive_videos"
    __table_args__ = (UniqueConstraint("source_id", "drive_file_id", name="uq_source_drive_file"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drive_sources.id"), nullable=False)
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_valid_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source: Mapped["DriveSource"] = relationship(back_populates="videos")
    upload_history: Mapped[list["UploadHistory"]] = relationship(back_populates="drive_video")


class YouTubeChannel(Base):
    __tablename__ = "youtube_channels"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    youtube_channel_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted at the application layer before being written here (Phase 3).
    oauth_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, name="channel_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=ChannelStatus.CONNECTED, nullable=False
    )
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="youtube_channels")
    settings: Mapped["AutomationSettings"] = relationship(back_populates="channel", uselist=False)
    runs: Mapped[list["AutomationRun"]] = relationship(back_populates="channel")
    upload_history: Mapped[list["UploadHistory"]] = relationship(back_populates="channel")


class AutomationSettings(Base):
    __tablename__ = "automation_settings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("youtube_channels.id"), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_upload_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    channel: Mapped["YouTubeChannel"] = relationship(back_populates="settings")
    category: Mapped["Category | None"] = relationship()

class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("channel_id", "run_date", name="uq_channel_run_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("youtube_channels.id"), nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="run_status"), nullable=False)
    videos_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_uploaded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    channel: Mapped["YouTubeChannel"] = relationship(back_populates="runs")
    upload_history: Mapped[list["UploadHistory"]] = relationship(back_populates="run")


class UploadHistory(Base):
    __tablename__ = "upload_history"
    __table_args__ = (
        # THE core duplicate-prevention guarantee, enforced by the database itself.
        UniqueConstraint("drive_video_id", "channel_id", name="uq_drive_video_channel"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_runs.id"), nullable=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("youtube_channels.id"), nullable=False)
    drive_video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drive_videos.id"), nullable=False)
    youtube_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded list
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=UploadStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    youtube_privacy_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    youtube_processing_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    youtube_status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["AutomationRun | None"] = relationship(back_populates="upload_history")
    channel: Mapped["YouTubeChannel"] = relationship(back_populates="upload_history")
    drive_video: Mapped["DriveVideo"] = relationship(back_populates="upload_history")
    failed_upload: Mapped["FailedUpload"] = relationship(back_populates="upload_history_entry", uselist=False)


class FailedUpload(Base):
    __tablename__ = "failed_uploads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    upload_history_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_history.id"), unique=True, nullable=False)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    upload_history_entry: Mapped["UploadHistory"] = relationship(back_populates="failed_upload")


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = _uuid_pk()
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    browser_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
