"""C1_1 vwap 开关：配置归一、行情派生、批次读取与 custom 源剥离。"""

from datetime import date, timedelta

from app.extensions import db
from app.models import Task
from app.repositories import task_kline_snapshot_repository
from app.services.google_sheet_tasks.c1_1 import C1_1Service
from app.services.kline_service import KlineService
from app.services.task.creation import TaskCreationMixin
from app.services.task_kline_snapshot_service import task_kline_snapshot_service


class _TaskCreation(TaskCreationMixin):
    pass


def _normalize(config):
    return _TaskCreation()._normalize_task_config_for_type(
        "google_sheet_C1_1",
        {"kline_source": "auto", "sheets": [{"spreadsheet_id": "sheet-1"}], **config},
    )


def _rows(count=31):
    first = date(2026, 1, 1)
    return [
        {
            "stock_date": (first + timedelta(days=offset)).isoformat(),
            "open": 10.0,
            "high": 14.0,
            "low": 8.0,
            "close": 12.0,
            "volume": 100.0,
            "amount": 1100.0,
        }
        for offset in range(count)
    ]


def _make_service(task_id, *, vwap_enabled):
    service = object.__new__(C1_1Service)
    service.task_id = task_id
    service.config = {"market_type": "cn"}
    service._random_price_range = "high_low"
    service._random_group_count = 1
    service._vwap_enabled = vwap_enabled
    service._dedupe_label = "C1_1"
    service._log_info = lambda *_args, **_kwargs: None
    service._log_warning = lambda *_args, **_kwargs: None
    return service


def test_vwap_enabled_defaults_true():
    assert _normalize({})["c1_1_vwap_enabled"] is True


def test_vwap_disabled_accepts_bool_and_string_false():
    assert _normalize({"c1_1_vwap_enabled": False})["c1_1_vwap_enabled"] is False
    assert _normalize({"c1_1_vwap_enabled": "false"})["c1_1_vwap_enabled"] is False


def test_prepare_batch_reads_vwap_switch(monkeypatch):
    class _Cfg:
        def get_config(self, key, default=None):
            return default

    from app.services.google_sheet_tasks import base as base_module

    monkeypatch.setattr(base_module, "get_config_manager", lambda: _Cfg())

    service = _make_service("task-vwap-batch", vwap_enabled=True)
    batch_off = service._prepare_batch({
        "kline_source": "auto", "price_mode": "random_price", "c1_1_vwap_enabled": False,
    })
    assert batch_off["vwap_enabled"] is False
    assert service._vwap_enabled is False

    batch_on = service._prepare_batch({"kline_source": "auto", "price_mode": "random_price"})
    assert batch_on["vwap_enabled"] is True


def test_normalize_rows_skips_vwap_derivation_when_disabled():
    row = {"stock_date": "2026-01-02", "open": 10.0, "high": 14.0, "low": 8.0,
           "close": 12.0, "volume": 100.0, "amount": 1100.0}
    derived = KlineService._normalize_rows([row], "600000.SH", "测试", "dfcf")
    assert derived[0]["vwap"] == 11.0

    skipped = KlineService._normalize_rows(
        [row], "600000.SH", "测试", "dfcf", include_vwap=False
    )
    assert skipped[0]["vwap"] is None


def test_c1_1_custom_source_strips_vwap_when_disabled(app_factory):
    with app_factory.app_context():
        task = Task(
            id="task-c1_1-vwap-off", name="t", task_type="google_sheet_C1_1",
            status="completed", config="{}",
        )
        db.session.add(task)
        db.session.commit()
        rows = _rows()
        for row in rows:
            row["vwap"] = 11.0

        service = _make_service(task.id, vwap_enabled=False)
        data, _length, _map = service._get_custom_parameters(
            "600000", [["600000"]], {"custom": rows}
        )

        source = task_kline_snapshot_repository.get_source(task.id, "600000", "custom")
        series = task_kline_snapshot_repository.get_series_by_id(data[0]["kline_series_id"])
        merged = task_kline_snapshot_service.merge_rows(source, series)
        assert all(row["vwap"] is None for row in merged)
