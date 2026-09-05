"""Backward-compatible entry point for the model-based PostgreSQL restore.

Use ``scripts.migrate_models_postgres_to_mysql`` for new integrations.  URLs
are always supplied through arguments or environment variables; this module
contains no deployment credentials and no second copy of migration logic.
"""

from tests.scripts.migrate_models_postgres_to_mysql import (
    configured_url,
    model_table_names,
    restore,
)


TABLE_NAMES = model_table_names()


def postgres_url():
    """Return the configured PostgreSQL source URL."""
    return configured_url(None, "PG_SOURCE_URL", "postgresql")


def mysql_url():
    """Return the configured MySQL target URL."""
    return configured_url(None, "MYSQL_TARGET_URL", "mysql")


def main():
    restore(
        postgres_url(),
        mysql_url(),
        batch_size=5000,
        create_schema=False,
        dry_run=False,
    )


if __name__ == "__main__":
    main()
