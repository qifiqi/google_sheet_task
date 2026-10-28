"""随机价组合数服务端精算：编排、custom 公式与估算不落快照。"""

import pytest

from app.exceptions import ValidationError
from app.services.google_sheet_tasks.combination_estimate import (
    estimate_combination_count,
)


class _StubService:
    """模拟真实服务：_prepare_batch 返回 batch，_expand_parameters 按产品返回组合。"""

    _persist_random_snapshots = True

    def __init__(self, config, windows):
        self.config = config
        self.windows = windows
        self.calls = []

    def _prepare_batch(self, config_data):
        return {"kline_source": config_data.get("kline_source", "auto")}

    def _expand_parameters(self, outer_param, parameters, batch):
        self.calls.append(outer_param)
        rows = [{"stock_date": "2026-01-0%d" % (i + 1)} for i in range(self.windows)]
        return rows, len(rows) + 20, {}


def _factory(service, captured):
    def make(task_type, config, task_id):
        captured["task_type"] = task_type
        captured["task_id"] = task_id
        return service

    return make


def test_auto_estimate_sums_combinations_per_product():
    service = _StubService({}, windows=6)
    captured = {}
    result = estimate_combination_count(
        "google_sheet_C7",
        {
            "kline_source": "auto",
            "parameters": [["600000", "000001"], [1, 2], [3]],
        },
        service_factory=_factory(service, captured),
    )

    # 2 个产品 × 6 个窗口 = 12
    assert result["estimated_count"] == 12
    assert result["source"] == "server"
    assert service.calls == ["600000", "000001"]
    assert captured["task_type"] == "google_sheet_c7"  # 工厂收到归一小写类型
    assert captured["task_id"].startswith("estimate-")


def test_estimate_service_disables_snapshot_persistence():
    service = _StubService({}, windows=1)
    estimate_combination_count(
        "google_sheet_C7",
        {"kline_source": "auto", "parameters": [["600000"]]},
        service_factory=lambda task_type, config, task_id: service,
    )
    assert service._persist_random_snapshots is False


def test_custom_mode_uses_configured_formula_without_sheet_read():
    # C1_1 custom：产品数 × 随机组数（占位内层，参数列表不参与；custom 固定随机展开，不看 price_mode）
    assert estimate_combination_count(
        "google_sheet_C1_1",
        {
            "kline_source": "custom",
            "random_group_count": 4,
            "parameters": [["A", "B", "C"], [1, 2], [3]],
        },
        service_factory=lambda *args: pytest.fail("custom 不应实例化服务"),
    ) == {"estimated_count": 12, "source": "formula"}

    # C5 custom：产品 2 × A1 3 × B1 2 = 12（custom 无随机分组）
    assert estimate_combination_count(
        "google_sheet_C5",
        {
            "kline_source": "custom",
            "parameters": [["A", "B"], [1, 2, 3], [4, 5]],
        },
        service_factory=lambda *args: pytest.fail("custom 不应实例化服务"),
    ) == {"estimated_count": 12, "source": "formula"}

    # C7 custom 携带 random_price 配置：执行路径不展开随机组，公式同样不计组数
    assert estimate_combination_count(
        "google_sheet_C7",
        {
            "kline_source": "custom",
            "price_mode": "random_price",
            "random_group_count": 4,
            "parameters": [["A", "B"], [1, 2, 3], [4, 5]],
        },
        service_factory=lambda *args: pytest.fail("custom 不应实例化服务"),
    ) == {"estimated_count": 12, "source": "formula"}


def test_empty_products_rejected():
    with pytest.raises(ValidationError, match="产品"):
        estimate_combination_count(
            "google_sheet_C7",
            {"kline_source": "auto", "parameters": [[]]},
            service_factory=lambda *args: None,
        )


def test_kline_failure_degrades_to_unavailable():
    class _FailingService(_StubService):
        def _expand_parameters(self, outer_param, parameters, batch):
            raise RuntimeError("K线数据不足")

    service = _FailingService({}, windows=0)
    result = estimate_combination_count(
        "google_sheet_C7",
        {"kline_source": "auto", "parameters": [["600000"]]},
        service_factory=lambda task_type, config, task_id: service,
    )

    assert result["available"] is False
    assert "K线数据不足" in result["message"]
