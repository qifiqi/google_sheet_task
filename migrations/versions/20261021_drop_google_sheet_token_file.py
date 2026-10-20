"""drop deprecated google_sheet_tokens.token_file column

Revision ID: 20261021_drop_google_sheet_token_file
Revises: 20260905_drop_stale_indexes
Create Date: 2026-10-21

本地凭据已改为 token_context 内存构造，token_file 不再承载任何数据。
远端表仍可能保留该兼容列，由 HTTP 仓储写入唯一 legacy 占位值。
"""
from alembic import op
import sqlalchemy as sa


revision = "20261021_drop_google_sheet_token_file"
down_revision = "20260905_drop_stale_indexes"
branch_labels = None
depends_on = None

_TABLE = "t_param_google_sheet_tokens"


def _columns(inspector):
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    if "token_file" not in _columns(inspector):
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column("token_file")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    if "token_file" in _columns(inspector):
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        # 历史列无法恢复原唯一值；降级只恢复列形态，唯一约束需人工补。
        batch_op.add_column(sa.Column("token_file", sa.String(length=500), nullable=True))
