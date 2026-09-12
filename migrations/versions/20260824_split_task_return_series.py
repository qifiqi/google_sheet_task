"""split task return series columns

Revision ID: 20260824_split_task_return_series
Revises: 20260811_remove_unused_indexes
"""

from alembic import op
import sqlalchemy as sa
import json
from datetime import date, datetime


revision = "20260824_split_task_return_series"
down_revision = "20260811_add_summary_market_type"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = next(
        (name for name in ("t_param_task_results_return", "task_results_return")
         if name in inspector.get_table_names()),
        None,
    )
    if not table_name:
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}

    with op.batch_alter_table(table_name) as batch_op:
        if "stock_code" not in columns:
            batch_op.add_column(sa.Column("stock_code", sa.String(20), nullable=True))
        if "stock_name" not in columns:
            batch_op.add_column(sa.Column("stock_name", sa.String(20), nullable=True))
        if "start_return_date" not in columns:
            batch_op.add_column(sa.Column("start_return_date", sa.Date(), nullable=True))
        if "end_return_date" not in columns:
            batch_op.add_column(sa.Column("end_return_date", sa.Date(), nullable=True))
        if "return_length" not in columns:
            batch_op.add_column(sa.Column("return_length", sa.Integer(), nullable=True))
        for name in ("stock_date", "index_return", "start_return"):
            if name not in columns:
                batch_op.add_column(sa.Column(name, sa.Text(), nullable=True))
        if "stock_date" in columns:
            batch_op.alter_column("stock_date", existing_type=sa.String(50), type_=sa.Text())
        if "index_return" in columns:
            batch_op.alter_column("index_return", existing_type=sa.Float(), type_=sa.Text())
        if "start_return" in columns:
            batch_op.alter_column("start_return", existing_type=sa.Float(), type_=sa.Text())

    # Backfill metadata from the legacy JSON payload before enforcing NOT NULL.
    legacy_json_column = "returns_json" in columns
    select_json = ", returns_json" if legacy_json_column else ""
    rows = list(bind.execute(sa.text(
        f"SELECT id, stock_code, stock_name, stock_date{select_json} FROM {table_name}"
    )).mappings())
    for row in rows:
        dates = []
        index_returns = []
        start_returns = []
        try:
            payload = json.loads(row["returns_json"] or "{}") if legacy_json_column else {}
            if isinstance(payload, dict):
                dates = payload.get("dates") or []
                index_returns = payload.get("index_returns") or []
                start_returns = payload.get("start_returns") or []
        except (TypeError, ValueError):
            pass
        if not dates and row["stock_date"]:
            try:
                existing_dates = json.loads(row["stock_date"])
                dates = existing_dates if isinstance(existing_dates, list) else [row["stock_date"]]
            except (TypeError, ValueError):
                dates = [row["stock_date"]]
        parsed_dates = []
        for value in dates:
            try:
                parsed_dates.append(datetime.strptime(str(value)[:10], "%Y-%m-%d").date())
            except (TypeError, ValueError):
                continue
        if not parsed_dates and row["stock_date"]:
            try:
                parsed_dates = [datetime.strptime(str(row["stock_date"])[:10], "%Y-%m-%d").date()]
            except ValueError:
                pass
        bind.execute(
            sa.text(
                f"UPDATE {table_name} SET stock_code=:stock_code, stock_name=:stock_name, "
                "start_return_date=:start_return_date, end_return_date=:end_return_date, "
                "return_length=:return_length, stock_date=:stock_date, "
                "index_return=:index_return, start_return=:start_return WHERE id=:id"
            ),
            {
                "id": row["id"],
                "stock_code": row["stock_code"] or "UNKNOWN",
                "stock_name": row["stock_name"] or "未知股票",
                "start_return_date": min(parsed_dates) if parsed_dates else date(1970, 1, 1),
                "end_return_date": max(parsed_dates) if parsed_dates else date(1970, 1, 1),
                "return_length": len(dates),
                "stock_date": json.dumps(dates, ensure_ascii=False),
                "index_return": json.dumps(index_returns, ensure_ascii=False),
                "start_return": json.dumps(start_returns, ensure_ascii=False),
            },
        )

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column("stock_code", existing_type=sa.String(20), nullable=False)
        batch_op.alter_column("stock_name", existing_type=sa.String(20), nullable=False)
        batch_op.alter_column("start_return_date", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("end_return_date", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("return_length", existing_type=sa.Integer(), nullable=False)
        if "returns_json" in columns:
            batch_op.drop_column("returns_json")

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
    for column in ("stock_code", "stock_name"):
        index_name = f"ix_{table_name}_{column}"
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, [column])


def downgrade():
    with op.batch_alter_table("t_param_task_results_return") as batch_op:
        batch_op.add_column(sa.Column("returns_json", sa.Text(), nullable=True))
        batch_op.drop_column("return_length")
        batch_op.drop_column("end_return_date")
        batch_op.drop_column("start_return_date")
