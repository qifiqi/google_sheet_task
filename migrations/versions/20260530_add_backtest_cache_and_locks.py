"""add backtest fixed product cache and database locks

Revision ID: 20260530_backtest_cache_locks
Revises: 20260528_stock_metadata
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_backtest_cache_locks"
down_revision = "20260528_stock_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backtest_product_result_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("returns_json", sa.Text(), nullable=True),
        sa.Column("source_task_id", sa.String(length=36), nullable=True),
        sa.Column("source_step_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "cache_key", name="uk_backtest_product_cache_batch_key"),
    )
    op.create_index(
        op.f("ix_backtest_product_result_cache_batch_id"),
        "backtest_product_result_cache",
        ["batch_id"],
    )
    op.create_index(
        op.f("ix_backtest_product_result_cache_cache_key"),
        "backtest_product_result_cache",
        ["cache_key"],
    )
    op.create_index(
        op.f("ix_backtest_product_result_cache_created_at"),
        "backtest_product_result_cache",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_backtest_product_result_cache_source_task_id"),
        "backtest_product_result_cache",
        ["source_task_id"],
    )

    op.create_table(
        "backtest_sheet_run_locks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("spreadsheet_id", name="uk_backtest_sheet_run_locks_spreadsheet_id"),
    )
    op.create_index(
        op.f("ix_backtest_sheet_run_locks_spreadsheet_id"),
        "backtest_sheet_run_locks",
        ["spreadsheet_id"],
    )
    op.create_index(op.f("ix_backtest_sheet_run_locks_task_id"), "backtest_sheet_run_locks", ["task_id"])


def downgrade():
    op.drop_index(op.f("ix_backtest_sheet_run_locks_task_id"), table_name="backtest_sheet_run_locks")
    op.drop_index(op.f("ix_backtest_sheet_run_locks_spreadsheet_id"), table_name="backtest_sheet_run_locks")
    op.drop_table("backtest_sheet_run_locks")

    op.drop_index(op.f("ix_backtest_product_result_cache_source_task_id"), table_name="backtest_product_result_cache")
    op.drop_index(op.f("ix_backtest_product_result_cache_created_at"), table_name="backtest_product_result_cache")
    op.drop_index(op.f("ix_backtest_product_result_cache_cache_key"), table_name="backtest_product_result_cache")
    op.drop_index(op.f("ix_backtest_product_result_cache_batch_id"), table_name="backtest_product_result_cache")
    op.drop_table("backtest_product_result_cache")
