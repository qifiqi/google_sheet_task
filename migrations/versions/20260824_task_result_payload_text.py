"""widen task result JSON columns for long C7/C-series payloads.

Revision ID: 20260824_task_result_payload_text
Revises: 20260824_task_log_message_text
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_task_result_payload_text"
down_revision = "20260824_task_log_message_text"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    bind = op.get_bind()
    table_name = "t_param_task_results"
    if not _table_exists(bind, table_name):
        return

    dialect_name = bind.dialect.name
    if dialect_name == "mysql":
        # TEXT 的 MySQL 上限约 64 KiB，C7 结果可能超过该限制。
        columns = {
            column["name"]
            for column in sa.inspect(bind).get_columns(table_name)
        }
        definitions = []
        if "result" in columns:
            definitions.append("MODIFY COLUMN result MEDIUMTEXT NULL")
        if "parameters" in columns:
            definitions.append("MODIFY COLUMN parameters MEDIUMTEXT NULL")
        if "error_message" in columns:
            definitions.append("MODIFY COLUMN error_message TEXT NULL")
        if definitions:
            bind.execute(sa.text(
                f"ALTER TABLE {table_name} {', '.join(definitions)}"
            ))
    elif dialect_name == "postgresql":
        columns = {
            column["name"]
            for column in sa.inspect(bind).get_columns(table_name)
        }
        for column_name in ("result", "parameters", "error_message"):
            if column_name in columns:
                bind.execute(sa.text(
                    f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE TEXT"
                ))


def downgrade():
    bind = op.get_bind()
    table_name = "t_param_task_results"
    if not _table_exists(bind, table_name):
        return

    if bind.dialect.name == "mysql":
        bind.execute(sa.text(
            f"ALTER TABLE {table_name} "
            "MODIFY COLUMN result TEXT NULL, "
            "MODIFY COLUMN parameters TEXT NULL, "
            "MODIFY COLUMN error_message TEXT NULL"
        ))
