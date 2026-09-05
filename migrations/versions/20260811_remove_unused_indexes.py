"""remove unused and redundant indexes

Revision ID: 20260811_remove_unused_indexes
Revises: 20260810_remove_all_foreign_keys
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_remove_unused_indexes"
down_revision = "20260810_remove_all_foreign_keys"
branch_labels = None
depends_on = None


UNUSED_INDEXES = {
    "tasks": ("ix_tasks_status", "ix_tasks_task_type"),
    "task_logs": ("idx_level_timestamp", "ix_task_logs_level", "ix_task_logs_task_id"),
    "task_results": ("ix_task_results_step_index", "ix_task_results_success", "ix_task_results_task_id"),
    "backtest_product_result_cache": (
        "ix_backtest_product_result_cache_batch_id",
        "ix_backtest_product_result_cache_cache_key",
        "ix_backtest_product_result_cache_created_at",
        "ix_backtest_product_result_cache_source_task_id",
    ),
    "backtest_sheet_run_locks": ("ix_backtest_sheet_run_locks_spreadsheet_id",),
    "task_result_summary_index": (
        "ix_task_result_summary_index_stock_code",
        "ix_task_result_summary_index_stock_name",
        "ix_task_result_summary_index_task_id",
        "ix_task_result_summary_index_task_result_id",
        "ix_task_result_summary_index_task_type",
        "ix_task_result_summary_index_year_label",
    ),
    "stock_metadata": (
        "idx_stock_metadata_exchange_market",
        "idx_stock_metadata_name",
        "ix_stock_metadata_created_at",
        "ix_stock_metadata_market_type",
        "ix_stock_metadata_stock_code",
    ),
    "task_templates": ("ix_task_templates_name",),
    "google_sheet_tokens": ("ix_google_sheet_tokens_is_active",),
    "google_sheet": ("ix_google_sheet_is_active",),
    "navigation_menu_items": ("ix_navigation_menu_items_parent_key",),
    "scheduled_tasks": (
        "idx_active_next_run",
        "idx_type_active",
        "ix_scheduled_tasks_is_running",
        "ix_scheduled_tasks_next_run_time",
    ),
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table_name, index_names in UNUSED_INDEXES.items():
        existing_names = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name in index_names:
            if index_name in existing_names:
                op.drop_index(index_name, table_name=table_name)


def downgrade():
    # Index removal is intentional. Re-adding indexes should follow current
    # production query evidence, rather than restoring obsolete definitions.
    pass
