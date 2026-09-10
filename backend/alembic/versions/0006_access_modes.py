# credential modes, access codes, and daily quotas
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0006_access_modes"
down_revision = "0005_categories"
branch_labels = None
depends_on = None

def upgrade():
    # Create the named PostgreSQL enums explicitly. Setting create_type=False
    # prevents SQLAlchemy from trying to create them a second time when the
    # table columns are created below.
    access_mode = postgresql.ENUM("own", "admin", name="access_mode", create_type=False)
    access_mode.create(op.get_bind(), checkfirst=True)
    code_status = postgresql.ENUM("unused", "redeemed", "revoked", name="access_code_status", create_type=False)
    code_status.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("access_mode", access_mode, nullable=False, server_default="own"))
    op.create_table("user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("google_client_id", sa.Text()), sa.Column("google_client_secret", sa.Text()), sa.Column("openrouter_api_key", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("access_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
        sa.Column("redeemed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("status", code_status, nullable=False, server_default="unused"),
        sa.Column("channel_limit", sa.Integer(), nullable=False, server_default="1"), sa.Column("daily_video_limit", sa.Integer(), nullable=False, server_default="2"))
    op.create_index("ix_access_codes_code_hash", "access_codes", ["code_hash"])
    op.create_table("access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("access_code_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("access_codes.id"), unique=True, nullable=False),
        sa.Column("channel_limit", sa.Integer(), nullable=False, server_default="1"), sa.Column("daily_video_limit", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("daily_upload_quotas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("reserved_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("successful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "quota_date", name="uq_daily_quota_user_date"))

def downgrade():
    op.drop_table("daily_upload_quotas"); op.drop_table("access_grants"); op.drop_index("ix_access_codes_code_hash", table_name="access_codes"); op.drop_table("access_codes"); op.drop_table("user_credentials"); op.drop_column("users", "access_mode")
    postgresql.ENUM(name="access_code_status").drop(op.get_bind(), checkfirst=True); postgresql.ENUM(name="access_mode").drop(op.get_bind(), checkfirst=True)
