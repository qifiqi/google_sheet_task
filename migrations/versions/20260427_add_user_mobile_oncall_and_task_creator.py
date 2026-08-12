"""add user mobile/oncall and task creator

Revision ID: 20260427_add_user_mobile_oncall_and_task_creator
Revises: 20260415_add_user_token_version
Create Date: 2026-04-27 15:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260427_add_user_mobile_oncall_and_task_creator"
down_revision = "20260415_add_user_token_version"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mobile", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("is_alert_oncall", sa.Boolean(), nullable=True))

    user_table = sa.table(
        "user",
        sa.column("is_alert_oncall", sa.Boolean()),
    )
    op.execute(
        user_table.update()
        .where(user_table.c.is_alert_oncall.is_(None))
        .values(is_alert_oncall=False)
    )

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "is_alert_oncall",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_tasks_created_by_user_id"), ["created_by_user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_created_by_user_id"))
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("is_alert_oncall")
        batch_op.drop_column("mobile")
