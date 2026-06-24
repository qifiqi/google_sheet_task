"""add task result summary index

Revision ID: 20260522_summary_index
Revises: 20260518_nav_menu
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_summary_index"
down_revision = "20260518_nav_menu"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_result_summary_index",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_result_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=True),
        sa.Column("stock_code", sa.String(length=64), nullable=True),
        sa.Column("model_key", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("year_label", sa.String(length=64), nullable=True),
        sa.Column("kline_range", sa.String(length=128), nullable=True),
        sa.Column("parameter_summary", sa.Text(), nullable=True),
        sa.Column("best_metric_name", sa.String(length=100), nullable=True),
        sa.Column("best_metric_value", sa.Float(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("is_best", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result_timestamp", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_result_id"], ["task_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_result_id", "model_key", name="uk_result_summary_result_model"),
    )
    op.create_index("idx_result_summary_type_stock_best", "task_result_summary_index", ["task_type", "stock_code", "is_best"])
    op.create_index("idx_result_summary_task_best", "task_result_summary_index", ["task_id", "is_best"])
    op.create_index("idx_result_summary_best_metric", "task_result_summary_index", ["best_metric_value"])
    op.create_index("idx_result_summary_created_at", "task_result_summary_index", ["created_at"])
    op.create_index(op.f("ix_task_result_summary_index_task_id"), "task_result_summary_index", ["task_id"])
    op.create_index(op.f("ix_task_result_summary_index_task_result_id"), "task_result_summary_index", ["task_result_id"])
    op.create_index(op.f("ix_task_result_summary_index_task_type"), "task_result_summary_index", ["task_type"])
    op.create_index(op.f("ix_task_result_summary_index_stock_code"), "task_result_summary_index", ["stock_code"])
    op.create_index(op.f("ix_task_result_summary_index_year_label"), "task_result_summary_index", ["year_label"])
    op.create_index(op.f("ix_task_result_summary_index_is_best"), "task_result_summary_index", ["is_best"])
    op.create_index(op.f("ix_task_result_summary_index_result_timestamp"), "task_result_summary_index", ["result_timestamp"])


def downgrade():
    op.drop_table("task_result_summary_index")
