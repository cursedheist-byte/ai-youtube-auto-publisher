'''add categories and category-aware selection'''
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0005_categories"
down_revision = "0004_final_hardening"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_categories_name"),
        sa.UniqueConstraint("normalized_name", name="uq_categories_normalized_name"),
    )
    op.create_index("ix_categories_normalized_name", "categories", ["normalized_name"])
    op.add_column("drive_sources", sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True))
    op.add_column("automation_settings", sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("automation_settings", "category_id")
    op.drop_column("drive_sources", "category_id")
    op.drop_index("ix_categories_normalized_name", table_name="categories")
    op.drop_table("categories")
