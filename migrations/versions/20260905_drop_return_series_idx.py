"""drop unused ix_task_results_return_series_id

Revision ID: 20260905_drop_return_series_idx
Revises: 20260905_restore_active_idx
Create Date: 2026-09-05

依据 docs/design/api-model-query-audit/02-index-audit.md §3：
- ix_task_results_return_series_id 零查询引用——return_series_id 仅作为值读出
  （按 TaskResultReturn 主键取收益序列），且 app/startup.py:162 启动期自动重建；
- 同步动作（本迁移配套的代码变更，非迁移职责）：
  删除 startup.py:162 的 _ensure_model_index 调用与 models index=True 声明。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260905_drop_return_series_idx"
down_revision = "20260905_restore_active_idx"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing_names = {index["name"] for index in inspector.get_indexes("t_param_task_results")}
    if "ix_task_results_return_series_id" in existing_names:
        op.drop_index(
            "ix_task_results_return_series_id",
            table_name="t_param_task_results",
        )


def downgrade():
    # Index removal is intentional. Re-adding indexes should follow current
    # production query evidence, rather than restoring obsolete definitions
    # （沿用 20260811 先例：不回补陈旧定义）。
    pass
