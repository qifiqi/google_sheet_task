"""C1.1 真实价取值（random_price_range=开盘/收盘/最高/最低）单元测试。

AG 列除随机价外支持直接写真实字段：kp_price/sp_price/high_price/low_price，
不参与随机生成、不展开随机分组。
"""

from types import SimpleNamespace

from app.services.google_sheet_tasks.base import BaseGoogleSheetService
from app.services.kline_service import KlineService, REAL_PRICE_RANGE_FIELDS


def _fake_service():
    """纯内存路径所需的最小实例属性（不落随机K线快照）。"""
    return SimpleNamespace(task_id="t-test", _persist_random_snapshots=False)


def _kline_rows():
    return [
        {
            "stock_date": "2024-01-02",
            "stock_val": 11,
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "vwap": 10.5,
        },
        {
            "stock_date": "2024-01-03",
            "stock_val": 12,
            "open": 11,
            "high": 13,
            "low": 10,
            "close": 12,
            "vwap": 11.5,
        },
    ]


def test_real_price_range_fields_mapping():
    assert REAL_PRICE_RANGE_FIELDS == {
        "kp_price": "open",
        "sp_price": "close",
        "high_price": "high",
        "low_price": "low",
    }


def test_build_price_rows_real_range_writes_field_without_random():
    for range_value, field in REAL_PRICE_RANGE_FIELDS.items():
        rows = KlineService.build_price_rows(
            _kline_rows(),
            "random_price",
            include_ohlc=True,
            random_price_range=range_value,
        )
        assert [row["stock_val"] for row in rows] == [
            kline[field] for kline in _kline_rows()
        ], range_value
        # OHLC 列保持原值，写入 Sheet 的 K线块不受影响
        assert rows[0]["open"] == 10 and rows[0]["high"] == 12


def test_build_price_rows_real_range_ignores_generator():
    import random as random_module

    rows = KlineService.build_price_rows(
        _kline_rows(),
        "random_price",
        include_ohlc=True,
        random_price_range="sp_price",
        random_generator=random_module.Random(42),
    )
    assert [row["stock_val"] for row in rows] == [11, 12]


def test_expand_random_price_groups_real_range_keeps_single_combination():
    combinations = [{"stock_code": "600000", "kline_key": "2024-2024"}]
    kline_data_map = {"2024-2024": _kline_rows()}
    data, grouped_map = BaseGoogleSheetService._expand_random_price_groups(
        _fake_service(),
        combinations,
        kline_data_map,
        "random_price",
        "sp_price",
        3,
    )
    # 真实价无随机分组：组合不展开，stock_val 重写为所选真实字段
    assert data == combinations
    assert set(grouped_map) == {"2024-2024"}
    assert [row["stock_val"] for row in grouped_map["2024-2024"]] == [11, 12]


def test_expand_random_price_groups_random_range_still_expands():
    combinations = [{"stock_code": "600000", "kline_key": "2024-2024"}]
    kline_data_map = {"2024-2024": _kline_rows()}
    data, grouped_map = BaseGoogleSheetService._expand_random_price_groups(
        _fake_service(),
        combinations,
        kline_data_map,
        "random_price",
        "high_low",
        2,
    )
    assert len(data) == 2
    assert {item["random_group"] for item in data} == {1, 2}
    assert set(grouped_map) == {"2024-2024:random-1", "2024-2024:random-2"}
