"""remove 13 unused/redundant indexes (api-model-query-audit 02 §3)

Revision ID: 20260905_drop_stale_indexes
Revises: 20260905_drop_return_series_idx
Create Date: 2026-09-05

依据 docs/design/api-model-query-audit/02-index-audit.md §2/§3 逐条判定：
- 布尔单列（is_best/is_in_use/is_visible/is_active）基数≈2 优化器不选；
- uk 左前缀冗余（google_sheet.spreadsheet_id）；
- 零查询引用（*_name、stock_code/stock_name、success_timestamp 组合）；
- 查询形态不匹配（navigation parent_sort：实际全局 ORDER BY sort_order,id）。
物理表名带 t_param_ 前缀（models __tablename__）；索引名为 Flask-SQLAlchemy
ix_<table>_<column> 约定 + 显式命名两个 idx_*。
配套代码变更：models index=True/__table_args__ 摘除、startup.py:357-358 补建删除。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260905_drop_stale_indexes"
down_revision = "20260905_drop_return_series_idx"
branch_labels = None
depends_on = None


STALE_INDEXES = {
    "t_param_task_results": (
        "idx_success_timestamp",
    ),
    "t_param_task_results_return": (
        "ix_t_param_task_results_return_stock_code",
        "ix_t_param_task_results_return_stock_name",
    ),
    "t_param_task_result_summary_index": (
        "ix_t_param_task_result_summary_index_is_best",
    ),
    "t_param_google_sheet": (
        "ix_t_param_google_sheet_spreadsheet_id",
        "ix_t_param_google_sheet_is_in_use",
        "ix_t_param_google_sheet_name",
    ),
    "t_param_google_sheet_tokens": (
        "ix_t_param_google_sheet_tokens_name",
    ),
    "t_param_scheduled_tasks": (
        "ix_t_param_scheduled_tasks_name",
        "ix_t_param_scheduled_tasks_is_active",
        "ix_t_param_scheduled_tasks_created_at",
    ),
    "t_param_navigation_menu_items": (
        "idx_navigation_menu_parent_sort",
        "ix_t_param_navigation_menu_items_is_visible",
    ),
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table_name, index_names in STALE_INDEXES.items():
        existing_names = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name in index_names:
            if index_name in existing_names:
                op.drop_index(index_name, table_name=table_name)


def downgrade():
    # Index removal is intentional. Re-adding indexes should follow current
    # production query evidence, rather than restoring obsolete definitions
    # （沿用 20260811 先例：不回补陈旧定义）。
    pass
