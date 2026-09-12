"""use a portable Google Sheet registry uniqueness key

Revision ID: 20260811_add_google_sheet_registry_scope
Revises: 20260811_remove_unused_indexes
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_add_google_sheet_registry_scope"
down_revision = "20260811_remove_unused_indexes"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("google_sheet")}
    if "registry_scope" not in columns:
        op.add_column(
            "google_sheet",
            sa.Column("registry_scope", sa.String(length=32), nullable=True),
        )

    google_sheet = sa.table(
        "google_sheet",
        sa.column("table_type", sa.String(length=20)),
        sa.column("registry_scope", sa.String(length=32)),
    )
    op.execute(
        google_sheet.update()
        .where(google_sheet.c.registry_scope.is_(None))
        .values(
            registry_scope=sa.case(
                (
                    google_sheet.c.table_type.in_(("c3", "c4", "c5", "c7")),
                    "c_series",
                ),
                else_=google_sheet.c.table_type,
            )
        )
    )

    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("google_sheet")}
    if "uk_google_sheet_spreadsheet_registry_scope" not in index_names:
        op.create_index(
            "uk_google_sheet_spreadsheet_registry_scope",
            "google_sheet",
            ["spreadsheet_id", "registry_scope"],
            unique=True,
        )


def downgrade():
    bind = op.get_bind()
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("google_sheet")}
    if "uk_google_sheet_spreadsheet_registry_scope" in index_names:
        op.drop_index("uk_google_sheet_spreadsheet_registry_scope", table_name="google_sheet")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("google_sheet")}
    if "registry_scope" in columns:
        op.drop_column("google_sheet", "registry_scope")
