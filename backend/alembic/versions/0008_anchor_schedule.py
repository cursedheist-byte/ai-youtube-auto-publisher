"""Admin anchor times for daily automation (Asia/Kolkata by default).

Adds the `automation_schedule` table (exactly one row: two anchor times)
and extends `automation_runs` with a `slot_index` so a channel can have one
run per anchor per day. Existing single-run data keeps slot_index=0 and stays
unique via (channel_id, run_date, slot_index); the old (channel_id, run_date)
uniqueness is replaced. No existing rows are dropped.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_anchor_schedule"
down_revision = "0007_align_model_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("anchor_1", sa.String(5), nullable=False),
        sa.Column("anchor_2", sa.String(5), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("singleton", name="uq_automation_schedule_singleton"),
    )
    op.add_column(
        "automation_runs",
        sa.Column("slot_index", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    # Old uniqueness was (channel_id, run_date); new per-anchor uniqueness:
    op.drop_constraint("uq_channel_run_date", "automation_runs", type_="unique")
    op.create_unique_constraint(
        "uq_channel_run_slot", "automation_runs", ["channel_id", "run_date", "slot_index"]
    )


def downgrade():
    # Collapse multi-slot runs back to one row per (channel_id, run_date):
    # keep the lowest slot_index per group.
    op.execute(
        """
        DELETE FROM automation_runs a
        USING automation_runs b
        WHERE a.channel_id = b.channel_id
          AND a.run_date = b.run_date
          AND a.slot_index > b.slot_index
        """
    )
    op.drop_constraint("uq_channel_run_slot", "automation_runs", type_="unique")
    op.create_unique_constraint(
        "uq_channel_run_date", "automation_runs", ["channel_id", "run_date"]
    )
    op.drop_column("automation_runs", "slot_index")
    op.drop_table("automation_schedule")
