"""restore hot-path indexes wrongly removed by 20260811

Revision ID: 20260905_restore_active_idx
Revises: 20260824_task_result_payload_text
Create Date: 2026-09-05

依据 docs/design/api-model-query-audit/02-index-audit.md §4：
- scheduled_tasks(is_active, next_run_time)（原名 idx_active_next_run）：
  调度 worker find_due 每 tick 热路径（is_active AND is_running=false AND
  next_run_time<=now ORDER BY next_run_time），20260811 误删后全表扫描；
- backtest_product_result_cache(source_task_id)（原名
  ix_backtest_product_result_cache_source_task_id）：缓存失效
  filter_by(source_task_id=task_id) 在用，同名索引在 20260811 被误删。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260905_restore_active_idx"
down_revision = "20260824_task_result_payload_text"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_active_next_run",
        "t_param_scheduled_tasks",
        ["is_active", "next_run_time"],
    )
    op.create_index(
        "ix_backtest_product_result_cache_source_task_id",
        "t_param_backtest_product_result_cache",
        ["source_task_id"],
    )


def downgrade():
    # 恢复的是 20260811 误删的在用索引；回滚即再次移除（与误删状态一致）。
    op.drop_index(
        "ix_backtest_product_result_cache_source_task_id",
        table_name="t_param_backtest_product_result_cache",
    )
    op.drop_index("idx_active_next_run", table_name="t_param_scheduled_tasks")
