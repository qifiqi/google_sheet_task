from sqlalchemy.exc import OperationalError

from app.utils.db_monitor import DatabaseMonitor
from app.utils.db_retry import DatabaseLockError, safe_db_operation


def test_database_monitor_uses_sqlalchemy_inspector(app_factory):
    app = app_factory
    with app.app_context():
        indexes = DatabaseMonitor.check_indexes()

        assert "tasks" in indexes
        assert DatabaseMonitor.get_database_size()["type"] == "sqlite"
        assert not DatabaseMonitor.vacuum_database()["success"]


def test_safe_db_operation_retries_transient_database_errors(monkeypatch):
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(None, None, Exception("deadlock detected"))
        return "done"

    monkeypatch.setattr("app.utils.db_retry.time.sleep", lambda _delay: None)

    assert safe_db_operation(operation, max_attempts=2) == "done"
    assert attempts == 2


def test_safe_db_operation_preserves_non_transient_errors():
    def operation():
        raise OperationalError(None, None, Exception("invalid SQL syntax"))

    try:
        safe_db_operation(operation, max_attempts=2)
    except OperationalError:
        pass
    else:
        raise AssertionError("non-transient database errors must not be retried")


def test_safe_db_operation_raises_domain_error_after_retries(monkeypatch):
    monkeypatch.setattr("app.utils.db_retry.time.sleep", lambda _delay: None)

    def operation():
        raise OperationalError(None, None, Exception("lock wait timeout"))

    try:
        safe_db_operation(operation, max_attempts=2)
    except DatabaseLockError:
        pass
    else:
        raise AssertionError("exhausted transient errors must raise DatabaseLockError")
