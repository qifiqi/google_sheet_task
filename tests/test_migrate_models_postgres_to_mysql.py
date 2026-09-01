import pytest

from app.extensions import db
from tests.scripts.migrate_models_postgres_to_mysql import (
    TABLE_ORDER,
    database_url,
    model_table_names,
    prepare_rows,
)


def test_mysql_url_without_driver_uses_pymysql():
    url = database_url("mysql://root:password@127.0.0.1:3306/app", "mysql")
    assert url.drivername == "mysql+pymysql"


def test_database_url_rejects_wrong_backend():
    with pytest.raises(ValueError, match="Expected a mysql"):
        database_url("postgresql://user:password@localhost/app", "mysql")


def test_model_table_list_covers_every_declared_table():
    assert set(model_table_names()) == set(db.metadata.tables)
    assert model_table_names()[: len(TABLE_ORDER)] == list(TABLE_ORDER)


def test_prepare_rows_normalizes_imported_boolean_text():
    rows = list(prepare_rows("navigation_menu_items", [{"is_visible": "t"}]))
    assert rows == [{"is_visible": True}]

    rows = list(prepare_rows("navigation_menu_items", [{"is_visible": "f"}]))
    assert rows == [{"is_visible": False}]
