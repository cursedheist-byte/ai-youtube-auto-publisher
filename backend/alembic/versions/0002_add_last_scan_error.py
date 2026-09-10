"""add last_scan_error to drive_sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drive_sources", sa.Column("last_scan_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("drive_sources", "last_scan_error")
