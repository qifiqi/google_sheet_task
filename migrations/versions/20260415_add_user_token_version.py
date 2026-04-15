"""add token_version to user

Revision ID: 20260415_add_user_token_version
Revises: 20260402_add_token_task_type
Create Date: 2026-04-15 16:45:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260415_add_user_token_version"
down_revision = "20260402_add_token_task_type"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("token_version", sa.Integer(), nullable=True))

    op.execute("UPDATE `user` SET token_version = 0 WHERE token_version IS NULL")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "token_version",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0",
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("token_version")
