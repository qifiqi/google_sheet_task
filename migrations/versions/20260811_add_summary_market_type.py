"""store summary market type with portable query support

Revision ID: 20260811_add_summary_market_type
Revises: 20260811_add_google_sheet_registry_scope
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_add_summary_market_type"
down_revision = "20260811_add_google_sheet_registry_scope"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("task_result_summary_index")
    }
    if "market_type" not in columns:
        op.add_column(
            "task_result_summary_index",
            sa.Column("market_type", sa.String(length=8), nullable=True),
        )

    summary_index = sa.table(
        "task_result_summary_index",
        sa.column("id", sa.Integer()),
        sa.column("stock_code", sa.String(length=64)),
        sa.column("market_type", sa.String(length=8)),
    )
    rows = bind.execute(
        sa.select(summary_index.c.id, summary_index.c.stock_code).where(
            sa.or_(
                summary_index.c.market_type.is_(None),
                summary_index.c.market_type == "",
            )
        )
    )
    for row_id, stock_code in rows:
        market_type = "cn" if str(stock_code or "").strip().isdigit() else "us"
        bind.execute(
            summary_index.update()
            .where(summary_index.c.id == row_id)
            .values(market_type=market_type)
        )
    index_names = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("task_result_summary_index")
    }
    if "idx_result_summary_type_market_best" not in index_names:
        op.create_index(
            "idx_result_summary_type_market_best",
            "task_result_summary_index",
            ["task_type", "market_type", "is_best"],
        )


def downgrade():
    bind = op.get_bind()
    index_names = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("task_result_summary_index")
    }
    if "idx_result_summary_type_market_best" in index_names:
        op.drop_index("idx_result_summary_type_market_best", table_name="task_result_summary_index")
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("task_result_summary_index")
    }
    if "market_type" in columns:
        op.drop_column("task_result_summary_index", "market_type")
