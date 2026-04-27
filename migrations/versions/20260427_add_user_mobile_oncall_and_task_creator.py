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

    op.execute("UPDATE `user` SET is_alert_oncall = 0 WHERE is_alert_oncall IS NULL")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "is_alert_oncall",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        )

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_tasks_created_by_user_id"), ["created_by_user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_tasks_created_by_user_id_user",
            "user",
            ["created_by_user_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint("fk_tasks_created_by_user_id_user", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_tasks_created_by_user_id"))
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("is_alert_oncall")
        batch_op.drop_column("mobile")
