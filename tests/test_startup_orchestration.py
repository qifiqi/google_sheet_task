from contextlib import nullcontext

from app import startup


class _FakeApp:
    def app_context(self):
        return nullcontext()


def test_bootstrap_runs_startup_stages_in_order(monkeypatch):
    calls = []

    for name in (
        '_prepare_runtime_directories',
        'initialize_logging',
        '_initialize_database_schema',
        '_recover_runtime_resources',
        '_initialize_system_metadata',
        'check_and_cleanup_dead_tasks',
        '_start_background_components',
    ):
        monkeypatch.setattr(
            startup,
            name,
            lambda *args, _name=name: calls.append(_name),
        )

    startup.bootstrap_app(_FakeApp())

    assert calls == [
        '_prepare_runtime_directories',
        'initialize_logging',
        '_initialize_database_schema',
        '_recover_runtime_resources',
        '_initialize_system_metadata',
        'check_and_cleanup_dead_tasks',
        '_start_background_components',
    ]
