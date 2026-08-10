"""remove all database foreign keys

Revision ID: 20260810_remove_all_foreign_keys
Revises: 20260531_summary_period_key
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_remove_all_foreign_keys"
down_revision = "20260531_summary_period_key"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in inspector.get_table_names():
        foreign_keys = inspector.get_foreign_keys(table_name)
        if not foreign_keys:
            continue

        # SQLite does not expose a name for inline/legacy foreign keys. A
        # batch rebuild is the only portable way to remove those constraints.
        if bind.dialect.name == "sqlite":
            reflected = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
            for constraint in list(reflected.constraints):
                if isinstance(constraint, sa.ForeignKeyConstraint):
                    reflected.constraints.remove(constraint)
            with op.batch_alter_table(
                table_name,
                copy_from=reflected,
                recreate="always",
            ):
                pass
            continue

        with op.batch_alter_table(table_name) as batch_op:
            for foreign_key in foreign_keys:
                name = foreign_key.get("name")
                if name:
                    batch_op.drop_constraint(name, type_="foreignkey")


def downgrade():
    # Foreign-key-free schema is intentional. Re-adding constraints requires
    # validating current data and a separately approved schema migration.
    pass
