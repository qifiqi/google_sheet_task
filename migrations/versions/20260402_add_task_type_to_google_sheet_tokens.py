"""add task_type to google_sheet_tokens

Revision ID: 20260402_add_token_task_type
Revises: 20260327_add_table_type
Create Date: 2026-04-02 12:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260402_add_token_task_type"
down_revision = "20260327_add_table_type"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("google_sheet_tokens", schema=None) as batch_op:
        batch_op.add_column(sa.Column("task_type", sa.String(length=50), nullable=True))

    op.execute(
        "UPDATE google_sheet_tokens SET task_type = 'google_sheet' "
        "WHERE task_type IS NULL OR task_type = ''"
    )

    with op.batch_alter_table("google_sheet_tokens", schema=None) as batch_op:
        batch_op.alter_column("task_type", existing_type=sa.String(length=50), nullable=False)
        batch_op.create_index("ix_google_sheet_tokens_task_type", ["task_type"], unique=False)


def downgrade():
    with op.batch_alter_table("google_sheet_tokens", schema=None) as batch_op:
        batch_op.drop_index("ix_google_sheet_tokens_task_type")
        batch_op.drop_column("task_type")
