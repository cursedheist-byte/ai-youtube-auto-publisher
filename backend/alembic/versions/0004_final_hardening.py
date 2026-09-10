"""final hardening: OAuth state, upload status/timestamps, stable duplicate guard"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_final_hardening"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("drive_videos", "size_bytes", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)
    op.execute("ALTER TYPE upload_status ADD VALUE IF NOT EXISTS 'uncertain'")
    op.add_column("upload_history", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("upload_history", sa.Column("youtube_privacy_status", sa.String(20), nullable=True))
    op.add_column("upload_history", sa.Column("youtube_processing_status", sa.String(30), nullable=True))
    op.add_column("upload_history", sa.Column("youtube_status_checked_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("browser_binding_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("state_hash", name="uq_oauth_state_hash"),
    )
    op.create_index("ix_oauth_states_state_hash", "oauth_states", ["state_hash"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])

    # Preserve the existing local (DriveVideo PK, channel) guard and add a DB-level
    # stable Drive-file guard. A trigger is used because the same Drive file can
    # legitimately be discovered through more than one source/folder record.
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_duplicate_drive_file_channel_upload()
    RETURNS trigger AS $$
    DECLARE stable_file_id text;
    BEGIN
        SELECT drive_file_id INTO stable_file_id FROM drive_videos WHERE id = NEW.drive_video_id;
        IF stable_file_id IS NULL THEN
            RAISE EXCEPTION 'drive video % does not exist', NEW.drive_video_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(stable_file_id || ':' || NEW.channel_id::text, 0));
        IF EXISTS (
            SELECT 1
            FROM upload_history uh
            JOIN drive_videos dv ON dv.id = uh.drive_video_id
            WHERE uh.channel_id = NEW.channel_id
              AND dv.drive_file_id = stable_file_id
              AND uh.id <> COALESCE(NEW.id, '00000000-0000-0000-0000-000000000000'::uuid)
        ) THEN
            RAISE EXCEPTION 'duplicate Drive file % for YouTube channel %', stable_file_id, NEW.channel_id USING ERRCODE = 'unique_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_prevent_duplicate_drive_file_channel_upload
    BEFORE INSERT OR UPDATE OF drive_video_id, channel_id ON upload_history
    FOR EACH ROW EXECUTE FUNCTION prevent_duplicate_drive_file_channel_upload();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_duplicate_drive_file_channel_upload ON upload_history")
    op.execute("DROP FUNCTION IF EXISTS prevent_duplicate_drive_file_channel_upload()")
    op.drop_index("ix_oauth_states_expires_at", table_name="oauth_states")
    op.drop_index("ix_oauth_states_state_hash", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_column("upload_history", "youtube_status_checked_at")
    op.drop_column("upload_history", "youtube_processing_status")
    op.drop_column("upload_history", "youtube_privacy_status")
    op.drop_column("upload_history", "last_attempt_at")
    # PostgreSQL enum values cannot be safely removed in-place without recreating
    # the type; leave the value present on downgrade rather than risking data loss.
    op.alter_column("drive_videos", "size_bytes", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True)
