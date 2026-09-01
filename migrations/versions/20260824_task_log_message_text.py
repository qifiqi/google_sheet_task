"""widen task log messages to TEXT.

Revision ID: 20260824_task_log_message_text
Revises: 20260824_split_task_return_series
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_task_log_message_text"
down_revision = "20260824_split_task_return_series"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "t_param_task_logs"
    if table_name not in inspector.get_table_names():
        return

    message_column = next(
        (column for column in inspector.get_columns(table_name) if column["name"] == "message"),
        None,
    )
    if message_column is None:
        return

    op.alter_column(
        table_name,
        "message",
        existing_type=message_column["type"],
        type_=sa.Text(),
        existing_nullable=message_column.get("nullable", True),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "t_param_task_logs"
    if table_name not in inspector.get_table_names():
        return

    message_column = next(
        (column for column in inspector.get_columns(table_name) if column["name"] == "message"),
        None,
    )
    if message_column is None:
        return

    # 255 is the legacy MySQL column size. Truncate before narrowing to avoid
    # failing the downgrade on databases that already contain long messages.
    bind.execute(sa.text(
        f"UPDATE {table_name} SET message = LEFT(message, 255)"
    ))
    op.alter_column(
        table_name,
        "message",
        existing_type=message_column["type"],
        type_=sa.String(length=255),
        existing_nullable=message_column.get("nullable", True),
    )
