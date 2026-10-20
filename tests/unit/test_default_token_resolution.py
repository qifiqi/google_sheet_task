"""默认 Token 解析：任务 token_id > default_token_id > 首个可用 Token。"""
from app.repositories.http_backend.base import RemoteRecord
from app.services import google_sheet_token_service as token_service_module


class _FakeTokenRepo:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def get_entity(self, token_id):
        for row in self.rows:
            if int(row["id"]) == int(token_id):
                return RemoteRecord(row)
        return None

    def list_entities_ordered(self, task_type=None):
        return [RemoteRecord(row) for row in self.rows]

    def list_active_entities(self, task_type=None):
        return [
            RemoteRecord(row)
            for row in self.rows
            if row.get("is_active")
        ]

    def commit(self):
        pass

    def flush(self):
        pass


def _service(monkeypatch, default_token_id=None):
    repo = _FakeTokenRepo(
        [
            {
                "id": 1,
                "name": "first",
                "task_type": "google_sheet",
                "is_active": True,
                "max_usage_count": 0,
                "current_in_use_count": 0,
            },
            {
                "id": 2,
                "name": "default",
                "task_type": "google_sheet",
                "is_active": True,
                "max_usage_count": 0,
                "current_in_use_count": 0,
            },
        ]
    )
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(
        service, "_get_default_token_id", lambda: int(default_token_id or 0)
    )
    monkeypatch.setattr(
        service,
        "_build_live_usage_snapshot",
        lambda: {"token_usage": {}, "current_total": 0},
    )
    return service


def test_default_token_preferred_over_first_active(monkeypatch):
    service = _service(monkeypatch, default_token_id=2)

    token = service.resolve_task_token({})

    assert token.id == 2


def test_explicit_task_token_beats_default(monkeypatch):
    service = _service(monkeypatch, default_token_id=2)

    token = service.resolve_task_token({"token_id": 1})

    assert token.id == 1


def test_invalid_default_falls_back_to_available_token(monkeypatch):
    service = _service(monkeypatch, default_token_id=999)

    token = service.resolve_task_token({})

    assert token.id in {1, 2}


def test_token_json_field_removed_from_task_config_schema():
    from app.schemas.task_configs import TokenRefFields

    assert "token_json" not in TokenRefFields.model_fields


class _FakeTaskRepo:
    def __init__(self, rows):
        self.rows = rows

    def list_id_config_by_status(self, status):
        return self.rows


def _service_with_rows(monkeypatch, rows, default_token_id=None, snapshot=None):
    repo = _FakeTokenRepo(rows)
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(
        service, "_get_default_token_id", lambda: int(default_token_id or 0)
    )
    monkeypatch.setattr(
        service,
        "_build_live_usage_snapshot",
        lambda: snapshot or {"token_usage": {}, "current_total": 0},
    )
    return service


def test_default_token_at_capacity_falls_back(monkeypatch):
    service = _service_with_rows(
        monkeypatch,
        [
            {"id": 1, "name": "default", "task_type": "google_sheet", "is_active": True, "max_usage_count": 1},
            {"id": 2, "name": "spare", "task_type": "google_sheet", "is_active": True, "max_usage_count": 0},
        ],
        default_token_id=1,
        snapshot={"token_usage": {1: 1}, "current_total": 1},
    )

    token = service.resolve_task_token({})

    assert token.id == 2


def test_explicit_inactive_token_is_rejected(monkeypatch):
    import pytest
    from app.exceptions import ValidationError

    service = _service_with_rows(
        monkeypatch,
        [{"id": 1, "name": "off", "task_type": "google_sheet", "is_active": False}],
    )

    with pytest.raises(ValidationError):
        service.resolve_task_token({"token_id": 1})


def test_explicit_token_wrong_task_type_is_rejected(monkeypatch):
    import pytest
    from app.exceptions import ValidationError

    service = _service_with_rows(
        monkeypatch,
        [{"id": 1, "name": "backtest", "task_type": "backtest_training", "is_active": True}],
    )

    with pytest.raises(ValidationError):
        service.resolve_task_token(
            {"token_id": 1, "token_task_type": "google_sheet"}
        )


def test_snapshot_counts_default_token_for_task_without_token_id(monkeypatch):
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(service, "_get_default_token_id", lambda: 2)
    monkeypatch.setattr(
        token_service_module,
        "task_repository",
        _FakeTaskRepo([{"config": '{"token_type": "file"}'}]),
    )

    snapshot = service._build_live_usage_snapshot()

    assert snapshot["token_usage"] == {2: 1}
    assert snapshot["current_total"] == 1
