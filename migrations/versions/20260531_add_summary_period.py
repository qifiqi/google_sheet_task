"""add period key to task result summary index

Revision ID: 20260531_summary_period_key
Revises: 20260530_backtest_cache_locks
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa


revision = "20260531_summary_period_key"
down_revision = "20260530_backtest_cache_locks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_result_summary_index",
        sa.Column("period_key", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "idx_result_summary_period_key",
        "task_result_summary_index",
        ["period_key"],
    )


def downgrade():
    op.drop_index("idx_result_summary_period_key", table_name="task_result_summary_index")
    op.drop_column("task_result_summary_index", "period_key")
