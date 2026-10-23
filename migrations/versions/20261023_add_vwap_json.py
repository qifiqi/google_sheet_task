"""ensure t_param_task_kline_sources.vwap_json exists

Revision ID: 20261023_add_vwap_json
Revises: 20261021_task_kline_snapshots
Create Date: 2026-10-23

20261021 在首次提交后于同一 revision 内补了 vwap_json。已执行过旧版迁移的库
不会重新建表，_table_exists 命中后也不会补列；这里按列存在性做一次幂等修复。
"""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20261023_add_vwap_json"
down_revision = "20261021_task_kline_snapshots"
branch_labels = None
depends_on = None

_TABLE = "t_param_task_kline_sources"


def _medium_text():
    return sa.Text().with_variant(mysql.MEDIUMTEXT, "mysql")


def _columns(bind):
    if _TABLE not in sa.inspect(bind).get_table_names():
        return {}
    return {column["name"]: column for column in sa.inspect(bind).get_columns(_TABLE)}


def _backfill_nulls(bind):
    rows = bind.execute(
        sa.text(f"SELECT id, row_count FROM {_TABLE} WHERE vwap_json IS NULL")
    ).fetchall()
    if not rows:
        return
    bind.execute(
        sa.text(f"UPDATE {_TABLE} SET vwap_json = :payload WHERE id = :id"),
        [
            {
                "payload": json.dumps([None] * max(int(row_count or 0), 0)),
                "id": row_id,
            }
            for row_id, row_count in rows
        ],
    )


def _set_not_null(bind):
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.alter_column(
                "vwap_json", existing_type=_medium_text(), nullable=False
            )
        return
    op.alter_column(_TABLE, "vwap_json", existing_type=_medium_text(), nullable=False)


def upgrade():
    bind = op.get_bind()
    columns = _columns(bind)
    if not columns:
        return

    column = columns.get("vwap_json")
    if column is None:
        op.add_column(_TABLE, sa.Column("vwap_json", _medium_text(), nullable=True))
        column = {"nullable": True}

    _backfill_nulls(bind)
    if column["nullable"]:
        _set_not_null(bind)


def downgrade():
    # vwap_json 属于 20261021 的现行表结构，降级不删除，避免误伤新建库。
    pass
