"""add stock metadata

Revision ID: 20260528_stock_metadata
Revises: 20260525_returns_json
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260528_stock_metadata"
down_revision = "20260525_returns_json"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stock_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_code", sa.String(length=64), nullable=False),
        sa.Column("stock_name", sa.String(length=255), nullable=False),
        sa.Column("market_type", sa.String(length=20), nullable=False),
        sa.Column("exchange_market", sa.String(length=50), nullable=True),
        sa.Column("security_type_name", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_code", "market_type", name="uk_stock_metadata_code_market_type"),
    )
    op.create_index(op.f("ix_stock_metadata_stock_code"), "stock_metadata", ["stock_code"])
    op.create_index(op.f("ix_stock_metadata_market_type"), "stock_metadata", ["market_type"])
    op.create_index(op.f("ix_stock_metadata_created_at"), "stock_metadata", ["created_at"])
    op.create_index("idx_stock_metadata_name", "stock_metadata", ["stock_name"])
    op.create_index("idx_stock_metadata_exchange_market", "stock_metadata", ["exchange_market"])
    op.add_column("task_result_summary_index", sa.Column("stock_name", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_task_result_summary_index_stock_name"), "task_result_summary_index", ["stock_name"])


def downgrade():
    op.drop_index(op.f("ix_task_result_summary_index_stock_name"), table_name="task_result_summary_index")
    op.drop_column("task_result_summary_index", "stock_name")
    op.drop_index("idx_stock_metadata_exchange_market", table_name="stock_metadata")
    op.drop_index("idx_stock_metadata_name", table_name="stock_metadata")
    op.drop_index(op.f("ix_stock_metadata_created_at"), table_name="stock_metadata")
    op.drop_index(op.f("ix_stock_metadata_market_type"), table_name="stock_metadata")
    op.drop_index(op.f("ix_stock_metadata_stock_code"), table_name="stock_metadata")
    op.drop_table("stock_metadata")
