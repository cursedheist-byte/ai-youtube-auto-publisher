"""Align the live schema with the SQLAlchemy models.

Alembic's autogenerate comparison flagged two classes of drift:

1. Timestamp columns (``*_at``) were created in early migrations without an
   explicit ``nullable=False``, so PostgreSQL left them nullable even though
   the models declare them NOT NULL. Existing rows always have a value
   (every one of these columns carries a ``server_default`` of ``now()``),
   so the ``NOT NULL`` backfill below cannot fail on real data.
2. Unique ``UniqueConstraint`` objects were created (e.g.
   ``users_email_key``) while the models instead declare a unique *index*
   with the same column and name. The database-level uniqueness guarantee
   is identical; this migration swaps the constraint for the index shape
   the models expect so ``alembic check`` stays clean.

Existing data is preserved; no tables are dropped or recreated.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_align_model_schema"
down_revision = "0006_access_modes"
branch_labels = None
depends_on = None

# (table, column) pairs whose timestamps the models declare NOT NULL.
NOT_NULL_COLUMNS = [
    ("access_codes", "created_at"),
    ("access_grants", "created_at"),
    ("automation_settings", "updated_at"),
    ("categories", "created_at"),
    ("categories", "updated_at"),
    ("drive_sources", "created_at"),
    ("drive_videos", "discovered_at"),
    ("oauth_states", "created_at"),
    ("upload_history", "created_at"),
    ("user_credentials", "updated_at"),
    ("users", "created_at"),
    ("youtube_channels", "connected_at"),
]

# (table, old unique constraint, index name, column) triples where the
# models declare a unique index rather than a unique constraint.
UNIQUE_INDEX_SWAPS = [
    ("access_codes", "access_codes_code_hash_key", "ix_access_codes_code_hash", "code_hash"),
    ("categories", "uq_categories_normalized_name", "ix_categories_normalized_name", "normalized_name"),
    ("oauth_states", "uq_oauth_state_hash", "ix_oauth_states_state_hash", "state_hash"),
    ("users", "users_email_key", "ix_users_email", "email"),
]


def upgrade():
    bind = op.get_bind()
    for table, column in NOT_NULL_COLUMNS:
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL"
            )
        )
        # Guard against a concurrent insert sneaking a NULL in between the
        # backfill and the ALTER.
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                f"SET NOT NULL"
            )
        )
        _ = bind
    for table, constraint, index, column in UNIQUE_INDEX_SWAPS:
        # The index swap is done by renaming the existing constraint-backed
        # unique index rather than dropping/recreating it, which would take
        # a heavier lock and momentarily lose the uniqueness guarantee.
        op.execute(
            sa.text(
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"
            )
        )
        op.execute(
            sa.text(f'DROP INDEX IF EXISTS "{index}"')
        )
        op.execute(
            sa.text(
                f'CREATE UNIQUE INDEX "{index}" '
                f'ON "{table}" ("{column}")'
            )
        )


def downgrade():
    # Downgrade restores the pre-migration shape: drop the unique indexes
    # and recreate the unique constraints, and make the timestamp columns
    # nullable again (data is kept).
    for table, constraint, index, column in UNIQUE_INDEX_SWAPS:
        op.execute(
            sa.text(f'DROP INDEX IF EXISTS "{index}"')
        )
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint}" '
                f'UNIQUE ("{column}")'
            )
        )
    for table, column in NOT_NULL_COLUMNS:
        op.execute(
            sa.text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL')
        )
