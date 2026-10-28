# -*- coding: utf-8 -*-
"""N+1 近年/整年参数展开骨架的区间生成回归（2026-10 修复）。

覆盖两个行为约定：
1. K线首日截断只收缩单个近年窗口的起点，不得减少近年区间总数
   （此前按截断后的起点年份重算 total_years，近3年/近5年整段消失）；
2. N+1 模式始终保留全区间组合（"+1"），与近年/年份窗口重合时按签名去重
   （此前 N+1+近年 直接跳过全区间，数据截断时连"总数"窗口都跑不出来）。
"""

from datetime import date, timedelta

from app.services.google_sheet_tasks.c5 import C5Service as C5GoogleSheetService


def _make_rows(first_date: str, last_date: str) -> list[dict]:
    rows = []
    current = date.fromisoformat(first_date)
    end = date.fromisoformat(last_date)
    while current <= end:
        rows.append({
            "stock_code": "159934.SZ",
            "stock_date": current.isoformat(),
            "open": 1.0,
            "close": 1.5,
            "high": 2.0,
            "low": 0.5,
            "vwap": 1.2,
            "volume": 1000,
            "amount": 1000.0,
        })
        current += timedelta(days=1)
    return rows


class _StubKlineService:
    """只实现骨架用到的两个入口：取数与投影（投影按区间/年份过滤）。"""

    def __init__(self, first_date, last_date):
        self._rows = _make_rows(first_date, last_date)

    def get_kline_data(self, stock_code, market_type, limit, **kwargs):
        return list(self._rows)

    def build_price_rows(self, rows, price_mode, *, start_date=None, end_date=None,
                         year=None, **kwargs):
        selected = rows
        if year is not None:
            selected = [row for row in selected if row["stock_date"][:4] == str(year)]
        else:
            if start_date:
                selected = [row for row in selected if row["stock_date"] >= start_date]
            if end_date:
                selected = [row for row in selected if row["stock_date"] <= end_date]
        return list(selected)


def _expand(service, date_range_mode, exclude_recent_years,
            start_date="2021-09-30", end_date="2026-09-30"):
    return service._expand_auto_year_parameters(
        "159934.SZ",
        "n_plus_1",
        "ohlc_price",
        end_date,
        start_date,
        "cn",
        date_range_mode,
        exclude_recent_years,
        [["159934.SZ"], [10], [1]],
    )


def _make_service(app_factory, kline_first_date):
    service = C5GoogleSheetService({}, "task-id")
    service._log_info = lambda *args, **kwargs: None
    service.kline_service = _StubKlineService(kline_first_date, "2026-09-30")
    return service


def test_recent_spans_keep_configured_count_when_kline_truncated(app_factory):
    """K线只有 2024-02-07 起：近3年/近5年不得消失，截断后与全区间同窗口并去重为一组。"""
    with app_factory.app_context():
        service = _make_service(app_factory, "2024-02-07")

        data, _, kline_map = _expand(service, ["recent"], [0.5, 2, 4])

    keys = {combination["kline_key"] for combination in data}
    assert keys == {"2026-2025", "2026-2024"}
    assert len(data) == 2
    assert kline_map["2026-2024"][0]["stock_date"] == "2024-02-07"
    assert kline_map["2026-2025"][0]["stock_date"] == "2025-09-30"


def test_recent_spans_dedupe_into_full_range_when_data_covers_config(app_factory):
    """数据覆盖配置区间时保持原有窗口集合；近5年与全区间重合，去重为一组。"""
    with app_factory.app_context():
        service = _make_service(app_factory, "2020-06-01")

        data, _, kline_map = _expand(service, ["recent"], [0.5, 2, 4])

    keys = {combination["kline_key"] for combination in data}
    assert keys == {"2026-2025", "2026-2023", "2026-2021"}
    assert len(data) == 3
    assert kline_map["2026-2021"][0]["stock_date"] == "2021-09-30"


def test_full_range_group_survives_when_all_recent_spans_excluded(app_factory):
    """近年窗口全部被移除时，N+1 仍保留全区间组合兜底。"""
    with app_factory.app_context():
        service = _make_service(app_factory, "2024-02-07")

        data, _, kline_map = _expand(service, ["recent"], [0.5, 1, 2, 3, 4, 5])

    assert [combination["kline_key"] for combination in data] == ["2026-2024"]
    assert kline_map["2026-2024"][0]["stock_date"] == "2024-02-07"


def test_full_year_mode_keeps_year_windows_plus_full_range(app_factory):
    """N+1 整年模式回归：各年份窗口 + 全区间组合。"""
    with app_factory.app_context():
        service = _make_service(app_factory, "2024-02-07")

        data, _, _ = _expand(service, ["full"], [])

    keys = {combination["kline_key"] for combination in data}
    assert keys == {2024, 2025, 2026, "2026-2024"}
    assert len(data) == 4
