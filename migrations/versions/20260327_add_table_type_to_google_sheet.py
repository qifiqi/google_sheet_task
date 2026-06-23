"""add table_type to google_sheet

Revision ID: 20260327_add_table_type
Revises:
Create Date: 2026-03-27 12:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260327_add_table_type"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("google_sheet", schema=None) as batch_op:
        batch_op.add_column(sa.Column("table_type", sa.String(length=20), nullable=True))

    op.execute("UPDATE google_sheet SET table_type = 'c3' WHERE table_type IS NULL OR table_type = ''")

    with op.batch_alter_table("google_sheet", schema=None) as batch_op:
        batch_op.alter_column("table_type", existing_type=sa.String(length=20), nullable=False)
        batch_op.create_index("ix_google_sheet_table_type", ["table_type"], unique=False)


def downgrade():
    with op.batch_alter_table("google_sheet", schema=None) as batch_op:
        batch_op.drop_index("ix_google_sheet_table_type")
        batch_op.drop_column("table_type")
