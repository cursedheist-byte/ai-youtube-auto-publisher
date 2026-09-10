"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Needed so gen_random_uuid() is available for server-side defaults on PK columns.
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "user", name="user_role"), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "drive_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("drive_folder_id", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", name="source_status"), nullable=False, server_default="active"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "drive_videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drive_sources.id"), nullable=False),
        sa.Column("drive_file_id", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_valid_video", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("source_id", "drive_file_id", name="uq_source_drive_file"),
    )

    op.create_table(
        "youtube_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("youtube_channel_id", sa.String(255), nullable=False, unique=True),
        sa.Column("channel_title", sa.String(255), nullable=False),
        sa.Column("oauth_access_token", sa.Text, nullable=True),
        sa.Column("oauth_refresh_token", sa.Text, nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("connected", "revoked", "error", name="channel_status"),
            nullable=False,
            server_default="connected",
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "automation_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("youtube_channels.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("daily_upload_count", sa.Integer, nullable=False, server_default="2"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("youtube_channels.id"), nullable=False),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column(
            "status",
            sa.Enum("success", "partial", "failed", "no_eligible_videos", name="run_status"),
            nullable=False,
        ),
        sa.Column("videos_attempted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("videos_uploaded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("channel_id", "run_date", name="uq_channel_run_date"),
    )

    op.create_table(
        "upload_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automation_runs.id"), nullable=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("youtube_channels.id"), nullable=False),
        sa.Column("drive_video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drive_videos.id"), nullable=False),
        sa.Column("youtube_video_id", sa.String(255), nullable=True),
        sa.Column("generated_title", sa.String(500), nullable=True),
        sa.Column("generated_description", sa.Text, nullable=True),
        sa.Column("generated_tags", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "uploading", "success", "failed", name="upload_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # The core duplicate-prevention guarantee, enforced by the database itself.
        sa.UniqueConstraint("drive_video_id", "channel_id", name="uq_drive_video_channel"),
    )

    op.create_table(
        "failed_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "upload_history_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("upload_history.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("failure_reason", sa.Text, nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("failed_uploads")
    op.drop_table("upload_history")
    op.drop_table("automation_runs")
    op.drop_table("automation_settings")
    op.drop_table("youtube_channels")
    op.drop_table("drive_videos")
    op.drop_table("drive_sources")
    op.drop_table("users")

    for enum_name in ("upload_status", "run_status", "channel_status", "source_status", "user_role"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
