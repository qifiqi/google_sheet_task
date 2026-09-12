from contextlib import nullcontext

from app import startup


class _FakeApp:
    def app_context(self):
        return nullcontext()


def _patch_bootstrap_stages(monkeypatch, calls):
    for name in (
        '_prepare_runtime_directories',
        'initialize_logging',
        '_recover_runtime_resources',
        'init_config',
        'check_and_cleanup_dead_tasks',
        '_start_background_components',
    ):
        monkeypatch.setattr(
            startup,
            name,
            lambda *args, _name=name, _calls=calls: _calls.append(_name),
        )


def test_bootstrap_runs_startup_stages_in_order(monkeypatch):
    calls = []
    _patch_bootstrap_stages(monkeypatch, calls)

    startup.bootstrap_app(_FakeApp())

    assert calls == [
        '_prepare_runtime_directories',
        'initialize_logging',
        '_recover_runtime_resources',
        'init_config',
        'check_and_cleanup_dead_tasks',
        '_start_background_components',
    ]


def test_bootstrap_does_not_seed_rbac_or_navigation(monkeypatch):
    """启动编排只补 SystemConfig 默认值；admin/角色/权限路由/导航种子必须手动 `flask init-rbac`。"""
    _patch_bootstrap_stages(monkeypatch, [])
    seeded = []
    monkeypatch.setattr(startup, 'init_config', lambda *args: seeded.append('config'))
    monkeypatch.setattr(startup, 'init_rbac', lambda *args: seeded.append('rbac'))
    monkeypatch.setattr(startup, 'init_navigation_menu', lambda *args: seeded.append('navigation'))

    startup.bootstrap_app(_FakeApp())

    assert seeded == ['config']
