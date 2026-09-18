"""export_backtest_word 的 RPT-M 载荷合并：弹窗元数据/运行参数覆盖任务默认值。

RPT-M 请求在服务端按任务重建 payload（metadata 来自任务配置、runtime_params
缺省即 rf=0），请求携带的 metadata/runtime_params 此前会被丢弃；多品全局预览
导出弹窗新增价格类型/无风险利率后，请求值需要合并进重建载荷（请求优先），
经 _runtime_params 进入 V1 引擎重算夏普并展示在报告元数据行。
"""

from io import BytesIO

from app.schemas.backtest import StrategyBacktestReportSchema
from app.services.export_service import export_service


def _request(**overrides) -> StrategyBacktestReportSchema:
    data = {
        "report_type": "RPT-M",
        "task_id": "T-MP-1",
        "group_key": "0",
        "ratios": [
            {"product_index": 0, "ratio": 60},
            {"product_index": 1, "ratio": 40},
        ],
        "metadata": {"risk_free_rate": "3.00%"},
        "runtime_params": {"risk_free_rate": 0.03},
    }
    data.update(overrides)
    return StrategyBacktestReportSchema.model_validate(data)


def _sample_returns() -> list[dict]:
    """最小合法累计收益序列（Schema 仅校验来源存在，报告生成另有 normalization）。"""
    return [
        {"date": "2024-01-02", "index_return": 0.01, "start_return": 0.02},
        {"date": "2024-01-03", "index_return": 0.015, "start_return": 0.025},
    ]


def _stub_rebuilt_payload(monkeypatch, captured):
    rebuilt = StrategyBacktestReportSchema.model_validate({
        "report_type": "RPT-M",
        "products": [{
            "stock_code": "QQQ.US",
            "product_name": "纳指ETF",
            "ratio": "60.00%",
            "returns": _sample_returns(),
        }, {
            "stock_code": "SOXX.US",
            "product_name": "半导体ETF",
            "ratio": "40.00%",
            "returns": _sample_returns(),
        }],
        "metadata": {"model_version": "c3", "price_type": "开盘价"},
    })

    def fake_builder(task_id, group_key, ratios_override=None):
        captured["builder_args"] = (task_id, group_key, ratios_override)
        return rebuilt

    def fake_cache(payload, builder, ttl_seconds=None, meta=None):
        captured["payload"] = payload
        captured["cache_meta"] = meta
        return "r.docx", BytesIO(b"data"), 4

    monkeypatch.setattr(
        "app.services.export_service.build_multi_product_global_preview_word_payload",
        fake_builder,
    )
    monkeypatch.setattr(
        "app.services.export_service.get_or_build_word_export",
        fake_cache,
    )


def test_rpt_m_merges_request_metadata_and_runtime_params(monkeypatch):
    captured = {}
    _stub_rebuilt_payload(monkeypatch, captured)

    generated = export_service.export_backtest_word(_request(
        metadata={"risk_free_rate": "3.00%", "price_type": "收盘价"},
    ))

    assert generated.filename == "r.docx"
    assert captured["builder_args"][0] == "T-MP-1"
    payload = captured["payload"]
    # 请求元数据覆盖任务默认值，任务自带字段保留。
    assert payload.metadata["risk_free_rate"] == "3.00%"
    assert payload.metadata["price_type"] == "收盘价"
    assert payload.metadata["model_version"] == "c3"
    # 运行参数进入重建载荷（原本缺省），驱动 V1 引擎按 rf 重算夏普。
    assert payload.runtime_params == {"risk_free_rate": 0.03}


def test_rpt_m_without_options_keeps_task_built_payload(monkeypatch):
    captured = {}
    _stub_rebuilt_payload(monkeypatch, captured)

    export_service.export_backtest_word(_request(metadata={}, runtime_params={}))

    payload = captured["payload"]
    # 未传弹窗配置时与历史行为一致：任务元数据原样、rf 缺省 0。
    assert payload.metadata == {"model_version": "c3", "price_type": "开盘价"}
    assert payload.runtime_params == {}
