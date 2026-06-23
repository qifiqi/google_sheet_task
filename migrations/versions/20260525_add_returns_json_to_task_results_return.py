"""add return series json

Revision ID: 20260525_returns_json
Revises: 20260522_summary_index
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_returns_json"
down_revision = "20260522_summary_index"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task_results_return") as batch_op:
        batch_op.add_column(sa.Column("returns_json", sa.Text(), nullable=True))
    with op.batch_alter_table("task_results") as batch_op:
        batch_op.add_column(sa.Column("return_series_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_task_results_return_series_id", ["return_series_id"])
        batch_op.create_foreign_key(
            "fk_task_results_return_series_id",
            "task_results_return",
            ["return_series_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("task_results") as batch_op:
        batch_op.drop_constraint("fk_task_results_return_series_id", type_="foreignkey")
        batch_op.drop_index("ix_task_results_return_series_id")
        batch_op.drop_column("return_series_id")
    with op.batch_alter_table("task_results_return") as batch_op:
        batch_op.drop_column("returns_json")
