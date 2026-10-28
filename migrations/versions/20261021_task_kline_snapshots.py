"""add random-price kline source/series snapshots and result links

Revision ID: 20261021_task_kline_snapshots
Revises: 20260905_drop_stale_indexes
Create Date: 2026-10-21

MySQL 5.7 兼容：只新建小表，不对 t_param_task_results 做大表 ALTER；
结果与快照的关联落在 t_param_task_result_kline_links。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20261021_task_kline_snapshots"
down_revision = "20260905_drop_stale_indexes"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    return table_name in sa.inspect(bind).get_table_names()


def _medium_text():
    return sa.Text().with_variant(mysql.MEDIUMTEXT, "mysql")


def upgrade():
    bind = op.get_bind()

    if not _table_exists(bind, "t_param_task_kline_sources"):
        op.create_table(
            "t_param_task_kline_sources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("stock_code", sa.String(length=64), nullable=False),
            sa.Column("stock_name", sa.String(length=255), nullable=True),
            sa.Column("market_type", sa.String(length=16), nullable=True),
            sa.Column("kline_key", sa.String(length=64), nullable=False),
            sa.Column("data_source", sa.String(length=32), nullable=True),
            sa.Column("adjust_type", sa.String(length=16), nullable=True),
            sa.Column("start_date", sa.String(length=10), nullable=True),
            sa.Column("end_date", sa.String(length=10), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("dates_json", _medium_text(), nullable=False),
            sa.Column("open_json", _medium_text(), nullable=False),
            sa.Column("high_json", _medium_text(), nullable=False),
            sa.Column("low_json", _medium_text(), nullable=False),
            sa.Column("close_json", _medium_text(), nullable=False),
            sa.Column("vwap_json", _medium_text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "task_id",
                "stock_code",
                "kline_key",
                name="uk_task_kline_source",
            ),
            comment="随机价格K线源快照表",
        )

    if not _table_exists(bind, "t_param_task_random_series"):
        op.create_table(
            "t_param_task_random_series",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("stock_code", sa.String(length=64), nullable=False),
            sa.Column("kline_key", sa.String(length=64), nullable=False),
            sa.Column("dataset_key", sa.String(length=128), nullable=False),
            sa.Column("random_group", sa.Integer(), nullable=False),
            sa.Column("price_mode", sa.String(length=32), nullable=False),
            sa.Column("random_price_range", sa.String(length=16), nullable=False),
            sa.Column("seed", sa.String(length=512), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("values_json", _medium_text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "task_id",
                "stock_code",
                "kline_key",
                "random_price_range",
                "random_group",
                name="uk_task_random_series_dataset",
            ),
            comment="随机价格K线序列表",
        )
        op.create_index(
            "idx_task_random_series_source_id",
            "t_param_task_random_series",
            ["source_id"],
        )

    if not _table_exists(bind, "t_param_task_result_kline_links"):
        op.create_table(
            "t_param_task_result_kline_links",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("result_id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("series_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "result_id",
                name="uk_task_result_kline_link_result",
            ),
            comment="任务结果随机K线关联表",
        )
        op.create_index(
            "idx_task_result_kline_links_task_id",
            "t_param_task_result_kline_links",
            ["task_id"],
        )
        op.create_index(
            "idx_task_result_kline_links_series_id",
            "t_param_task_result_kline_links",
            ["series_id"],
        )


def downgrade():
    bind = op.get_bind()

    if _table_exists(bind, "t_param_task_result_kline_links"):
        op.drop_index(
            "idx_task_result_kline_links_series_id",
            table_name="t_param_task_result_kline_links",
        )
        op.drop_index(
            "idx_task_result_kline_links_task_id",
            table_name="t_param_task_result_kline_links",
        )
        op.drop_table("t_param_task_result_kline_links")

    if _table_exists(bind, "t_param_task_random_series"):
        op.drop_index(
            "idx_task_random_series_source_id",
            table_name="t_param_task_random_series",
        )
        op.drop_table("t_param_task_random_series")

    if _table_exists(bind, "t_param_task_kline_sources"):
        op.drop_table("t_param_task_kline_sources")
