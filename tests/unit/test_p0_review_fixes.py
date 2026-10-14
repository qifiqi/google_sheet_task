"""2026-10-11 审查修复回归。

覆盖两类"单测全绿但生产路径必挂"的收敛回归：
1. JSON 清洗收敛到 formatting.sanitize_json_value 后的残留 self._sanitize_json_value
   调用（C3 结果摘要 / 多品固定产品缓存写入，修复前 AttributeError）；
2. 内置K线回填仓储 upsert_stock_data 的 payload 绑定（partial + run_in_executor
   位置实参，keyword-only 修复前 TypeError）；
3. 敏感配置掩码回显（***）不得写库覆盖真实值。
"""

import json
from types import SimpleNamespace

from app.repositories import backtest_repository
from app.services.backtest_multi_product_service import BacktestMultiProductService
from app.services.config_manager import _is_masked_echo
from app.services.google_sheet_tasks.c3 import C3Service
from app.services.kline_service import KlineService
from app.utils import ding_talk_notifier


def _bare(service_cls):
    """跳过 __init__ 构造裸实例：仅测纯方法路径，不触碰配置/网络。"""
    return object.__new__(service_cls)


def test_c3_result_summary_sanitize_survives_nan_payload():
    summary_json = _bare(C3Service)._summarize_result_for_log({
        "I15": float("nan"), "B6": "12.3%",
    })
    data = json.loads(summary_json)
    assert data["I15"] is None
    assert data["B6"] == "12.3%"


def test_c3_return_analysis_summary_sanitize_survives_inf_payload():
    summary_json = _bare(C3Service)._summarize_return_analysis_for_log(
        {"index_annualized_return": float("inf"), "start_annualized_return": 0.12},
        {},
        row_count=3,
        read_elapsed=0.5,
        performance_analysis_elapsed=0.25,
    )
    data = json.loads(summary_json)
    assert data["flat_result"]["index_annualized_return"] is None
    assert data["flat_result"]["start_annualized_return"] == 0.12


def test_multi_product_fixed_product_cache_write_sanitize(monkeypatch):
    recorded = {}

    def fake_insert(batch_id, cache_key, fields, commit=True):
        recorded.update(fields)
        return True

    monkeypatch.setattr(backtest_repository, "insert_product_cache_if_absent", fake_insert)
    service = _bare(BacktestMultiProductService)
    service.task_id = "task-review-fix"

    service._save_fixed_product_cache(
        {
            "fixed_product_batch_id": "batch-review",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        {"is_fixed": True, "stock_code": "600000", "market_type": "cn", "sheet": {}},
        ["2024"],
        {"model_metrics": {"sharpe": float("nan")}},
        return_date=None,
        step_index=0,
    )

    data = json.loads(recorded["result_json"])
    assert data["model_metrics"]["sharpe"] is None


class _FakeRemoteMarketApi:
    """remote_api StockData/StockDataUs 控制器替身：记录读写调用。"""

    def __init__(self):
        self.reads = []
        self.rows = []

    def get_data_all_list(self, payload):
        self.reads.append(payload)
        return [{"stock_date": "2024-01-01"}]

    def modify_or_add(self, payload):
        self.rows.append(payload)
        return True


class _FakeStockApi:
    def __init__(self):
        self.stock_data = _FakeRemoteMarketApi()
        self.stock_data_us = _FakeRemoteMarketApi()


def _kline_rows():
    return [{
        "stock_date": "2024-01-01", "stock_name": "浦发银行",
        "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5,
        "volume": 1000, "amount": 10500, "pct_change": 0.5, "change": 0.05,
    }]


def test_write_internal_kline_data_backfills_via_remote_api():
    """A股回填必须路由到 stock_data 控制器，且 wire 字段翻译仍在 kline_service。"""
    fake = _FakeStockApi()
    service = KlineService(dfcf_api=SimpleNamespace(), stock_api=fake)

    service.write_internal_kline_data(
        _kline_rows(), market_type="cn", stock_code="600000", adjust_type="forward",
    )

    assert fake.stock_data.reads, "回填前应先经 stock_data 查询区间窗口"
    assert fake.stock_data_us.rows == []
    # 内部 open → wire stock_open
    assert fake.stock_data.rows[0]["stock_open"] == 10.0
    assert fake.stock_data.rows[0]["stock_close"] == 10.5


def test_write_internal_kline_data_us_routes_to_stock_data_us():
    """美股（非纯数字代码）回填必须路由到 stock_data_us 控制器。"""
    fake = _FakeStockApi()
    service = KlineService(dfcf_api=SimpleNamespace(), stock_api=fake)

    rows = _kline_rows()
    rows[0]["stock_code"] = "AAPL"
    service.write_internal_kline_data(
        rows, market_type="us", stock_code="AAPL", adjust_type="forward",
    )

    assert fake.stock_data_us.reads, "美股应查询 stock_data_us"
    assert fake.stock_data.rows == []
    assert fake.stock_data_us.rows[0]["stock_open"] == 10.0
    assert fake.stock_data_us.rows[0]["stock_date"] == "2024-01-01"


def test_masked_echo_detection_scope():
    assert _is_masked_echo("backtest_training_token_id", "***")
    assert _is_masked_echo("ding_secret", "***")
    # 非敏感键的 *** 是合法业务值，不属于回显
    assert not _is_masked_echo("some_other_key", "***")
    # 敏感键的真实值不受影响
    assert not _is_masked_echo("ding_secret", "real-secret-value")


def test_preview_metrics_recalc_none_does_not_override_legacy(monkeypatch):
    """重算出的 None（V1 出口已 NaN→None）不得覆盖历史有限指标。

    resolve_preview_metrics 的守卫只挡 float 非有限值时，None 会覆盖
    历史值（如 legacy excess_sharp 升级来的 excess_sharpe=3.92）。
    """
    from app.services.performance_analysis import historical_metrics

    legacy_core = {"calculate_metrics": {"excess_sharp": 3.92}}

    def fake_recalc(_rows):
        return SimpleNamespace(metrics={"excess_sharpe": None, "excess_sortino": 33.44})

    monkeypatch.setattr(
        "app.services.performance_analysis.facade.calculate_v1_metrics", fake_recalc
    )
    merged = historical_metrics.resolve_preview_metrics(
        legacy_core,
        return_rows=[
            {"date": "2025-01-01", "index_return": 0.0, "start_return": 0.0},
            {"date": "2025-01-02", "index_return": -0.02, "start_return": -0.01},
        ],
    )

    assert merged["excess_sharpe"] == 3.92
    assert merged["excess_sortino"] == 33.44
