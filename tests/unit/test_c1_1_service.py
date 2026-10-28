from datetime import date, timedelta

import pytest

from app.services.google_sheet_tasks.base import (
    calculate_index_returns_from_closes,
    parse_range_start,
)
from app.services.google_sheet_tasks.check_policy import (
    C1_1_INVALID,
    C7_INVALID,
    normalize_check_values,
)
from app.services.google_sheet_tasks.c1_1 import C1_1Service, _annualized_collapsed
from app.services.google_sheet_tasks.result_payload import build_c1_1_summary_fields
from app.services.kline_service import KlineService


def _kline_rows(day_count=31, vwap_base=11.0, first_date=None):
    first_date = first_date or date(2026, 1, 1)
    rows = []
    for offset in range(day_count):
        current_date = first_date + timedelta(days=offset)
        rows.append({
            "stock_date": current_date.isoformat(),
            "open": 10,
            "high": 14,
            "low": 8,
            "close": 12,
            "vwap": vwap_base,
        })
    return rows


def _stub_kline_fetching(service, rows, monkeypatch):
    monkeypatch.setattr(
        "app.services.google_sheet_tasks.base.upsert_stock_metadata_in_session",
        lambda _payload: None,
    )
    # 内置K线库不桩会真实请求内网服务
    service.kline_service.read_internal_kline_data = lambda **_kwargs: []
    service.kline_service.write_internal_kline_data = lambda rows, **_kwargs: []
    monkeypatch.setattr(
        service.dfcf_api,
        "get_search_list_by_stock_code",
        lambda _stock_code, _limit: [{"code": _stock_code, "market": "1", "shortName": "测试股票", "status": 10}],
    )
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: rows,
    )


# ---- 共享小工具 ----

def test_parse_range_start_extracts_column_and_row():
    assert parse_range_start("AZ2:AZ26") == ("AZ", 2)
    assert parse_range_start("K2") == ("K", 2)


def test_calculate_index_returns_from_closes_is_cumulative():
    rows = [
        {"close": 10},
        {"close": 11},
        {"close": 9},
    ]
    returns = calculate_index_returns_from_closes(rows)
    assert returns[0] == 0
    assert abs(returns[1] - 0.1) < 1e-12
    assert abs(returns[2] + 0.1) < 1e-12


def test_calculate_index_returns_rejects_invalid_close():
    with pytest.raises(ValueError):
        calculate_index_returns_from_closes([{"close": 10}, {"close": 0}])


# ---- build_price_rows 补 vwap ----

def test_build_price_rows_random_price_includes_vwap(monkeypatch):
    monkeypatch.setattr(
        "app.services.kline_service.random.uniform",
        lambda low, high: low,
    )
    projected = KlineService.build_price_rows(
        _kline_rows(2),
        "random_price",
        include_ohlc=True,
        random_price_range="high_low",
    )

    assert all(row["vwap"] == 11.0 for row in projected)
    assert projected[0]["stock_val"] == 8


# ---- C1_1 布局 ----

def test_c1_1_layout_defaults():
    layout = C1_1Service._get_c1_1_layout({})

    assert layout["start_row"] == 2
    assert layout["date_column"] == "AA"
    assert layout["open_column"] == "AB"
    assert layout["high_column"] == "AC"
    assert layout["low_column"] == "AD"
    assert layout["close_column"] == "AE"
    assert layout["vwap_column"] == "AF"
    assert layout["ext_column"] == "AG"
    assert layout["output_range"] == "F2:F26"
    assert layout["output_column_k"] == "K"


def test_c1_1_layout_supports_config_overrides():
    layout = C1_1Service._get_c1_1_layout({
        "c1_1_kline_start_row": 3,
        "c1_1_kline_date_column": "ba",
        "c1_1_output_range": "P2:P26",
        "c1_1_output_column_k": "M",
    })

    assert layout["start_row"] == 3
    assert layout["date_column"] == "BA"
    assert layout["output_range"] == "P2:P26"
    assert layout["output_column_k"] == "M"


# ---- 无参数展开 + 随机分组 ----

def test_c1_1_expand_without_parameters_builds_random_groups(monkeypatch):
    service = C1_1Service({}, "task-id")
    _stub_kline_fetching(service, _kline_rows(), monkeypatch)
    batch = service._prepare_batch({
        "kline_source": "auto",
        "price_mode": "random_price",
        "count_mode": "total",
        "market_type": "cn",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "date_range_mode": [],
        "exclude_recent_years": [],
        "random_price_range": "high_low",
        "random_group_count": 2,
        "kline_data_source": "dfcf",
    })

    combinations, _column_length, kline_map = service._expand_parameters(
        "600000", [["600000"]], batch
    )

    assert len(combinations) == 2
    assert [item["random_group"] for item in combinations] == [1, 2]
    assert all("A1" not in item and "B1" not in item for item in combinations)
    assert all(str(item["stock_code"]).startswith("600000") for item in combinations)
    assert len(kline_map) == 2
    for kline in kline_map.values():
        assert all(8 <= row["stock_val"] <= 14 for row in kline)
        assert all(row["vwap"] == 11.0 for row in kline)


def test_c1_1_expand_supports_recent_and_full_year_windows(monkeypatch):
    service = C1_1Service({}, "task-id")
    _stub_kline_fetching(
        service,
        _kline_rows(day_count=1600, first_date=date(2022, 1, 3)),
        monkeypatch,
    )
    batch = service._prepare_batch({
        "kline_source": "auto",
        "price_mode": "random_price",
        "count_mode": "n_plus_1",
        "market_type": "cn",
        "start_date": "2022-01-03",
        "end_date": "2026-10-20",
        "date_range_mode": ["full", "recent"],
        "exclude_recent_years": [1],
        "random_price_range": "high_low",
        "random_group_count": 1,
        "kline_data_source": "dfcf",
    })

    combinations, _column_length, kline_map = service._expand_parameters(
        "600000", [["600000"]], batch
    )

    keys = {str(item["kline_key"]) for item in combinations}
    assert len(keys) >= 3
    assert any("random" in key for key in keys)
    assert all("A1" not in item and "B1" not in item for item in combinations)


def test_c1_1_prepare_batch_rejects_non_random_price():
    service = object.__new__(C1_1Service)

    with pytest.raises(ValueError, match="随机价格"):
        service._prepare_batch({"kline_source": "auto", "price_mode": "vwap_price"})


# ---- 结果块字段映射 ----

def test_c1_1_summary_fields_map_block_in_order():
    values = [
        "2020/01/02", "2025/06/05", "387.89%", "33.89%", "-43.55%", "2022/10/14",
        "166.72%", "19.80%", "-45.75%", "2022/10/14", "11.76%", "4.07%",
        "", "", 3.13, "2022/10/14", 0.94, 0, "", "", "", "1.74%", 2.70, "", "",
    ]

    fields = build_c1_1_summary_fields(lambda offset: values[offset])

    assert fields["start_date"] == "2020/01/02"
    assert fields["end_date"] == "2025/06/05"
    assert abs(fields["return_rate"] - 3.8789) < 1e-12
    assert abs(fields["annualized_rate"] - 0.3389) < 1e-12
    assert abs(fields["maxdd"] + 0.4355) < 1e-12
    assert fields["maxdd_date"] == "2022/10/14"
    assert abs(fields["index_rate"] - 1.6672) < 1e-12
    assert fields["max_actual_leverage"] == 3.13
    assert fields["max_leverage_date"] == "2022/10/14"
    assert fields["delvg_count"] == 0
    assert abs(fields["avg_volatility"] - 0.0174) < 1e-12
    assert fields["ref_xm"] == 2.70
    assert "ref_x_min" in fields


def test_c1_1_invalid_predicate_allows_empty_cells():
    normalized = normalize_check_values(
        {"F20": "", "F21": "-"},
        invalid_predicate=C1_1_INVALID,
    )
    assert normalized == {"F20": ""}


def test_c1_1_result_payload_uses_summary_block():
    service = object.__new__(C1_1Service)
    service.task_id = "task-c1_1"
    result_cells = {f"F{2 + offset}": value for offset, value in enumerate([
        "2020/01/02", "2025/06/05", "387.89%", "33.89%", "-43.55%", "2022/10/14",
        "166.72%", "19.80%", "-45.75%", "2022/10/14", "11.76%", "4.07%",
        None, None, "3.13", "2022/10/14", "0.94", 0, None, None, None, "1.74%", "2.70", None, None,
    ])}
    result = {
        **result_cells,
        "metrics_payload": {"metrics": {"index_sharpe_ratio": 1.2}},
        "_return_date": [],
    }
    combination = {
        "stock_code": "600000",
        "kline": [],
        "c1_1_output_range": "F2:F26",
    }

    payload = service._build_stock_param_result_payload("C1_1 测试", 0, combination, result)

    assert payload["stock_code"] == "600000"
    assert abs(payload["return_rate"] - 3.8789) < 1e-12
    assert payload["start_date"] == "2020/01/02"
    assert payload["max_leverage_date"] == "2022/10/14"
    assert payload["index_sharpe_ratio"] == 1.2


# ---- custom K线（AA-AF 读回，仅写 ext） ----

class _C1_1CustomSheet:
    title = "C1_1.0.1"
    spreadsheet_id = "c1_1-custom-sheet"

    def __init__(self):
        self.clear_calls = []
        self.update_payloads = []

    def get_last_row(self, column):
        assert column == "AA"
        return 3

    def get_range(self, range_a1):
        assert range_a1 == "AA2:AF3"
        return {
            "AA2": "2026-01-01", "AB2": 10, "AC2": 14, "AD2": 8, "AE2": 12, "AF2": 11,
            "AA3": "2026-01-02", "AB3": 12, "AC3": 15, "AD3": 11, "AE3": 13, "AF3": 12,
        }


class _C1_1ExecuteSheet:
    title = "C1_1.0.1"
    spreadsheet_id = "c1_1-execute-sheet"

    def __init__(self, initial_block, result_block):
        self.clear_calls = []
        self.update_payloads = []
        self.update_input_options = []
        self._initial_block = dict(initial_block)
        self._result_block = dict(result_block)

    def get_last_row(self, column):
        assert column in {"AA", "AB", "AC", "AD", "AE", "AF", "AG"}
        return 3

    def clear_range(self, range_a1):
        self.clear_calls.append(range_a1)

    def get_range(self, range_a1):
        assert range_a1 == "F2:F26"
        return dict(self._initial_block)

    def update_jumped_cells(self, payload, value_input_option='RAW'):
        self.update_payloads.append(dict(payload))
        self.update_input_options.append(value_input_option)

    def get_ranges(self, ranges):
        assert ranges == ["F2:F26", "K2:K3"]
        return {
            "F2:F26": dict(self._result_block),
            "K2:K3": {"K2": "10%", "K3": "20%"},
        }


def test_c1_1_execute_writes_ohlc_vwap_ext(monkeypatch):
    initial_block = {f"F{row}": "" for row in range(2, 27)}
    result_block = {f"F{row}": value for row, value in zip(range(2, 27), [
        "2020/01/02", "2025/06/05", "387.89%", "33.89%", "-43.55%", "2022/10/14",
        "166.72%", "19.80%", "-45.75%", "2022/10/14", "11.76%", "4.07%",
        "", "", "3.13", "2022/10/14", "0.94", 0, "", "", "", "1.74%", "2.70", "", "",
    ])}
    sheet = _C1_1ExecuteSheet(initial_block, result_block)
    service = C1_1Service({"kline_source": "auto", "market_type": "cn"}, "task-id")
    service.google_sheets = [sheet]
    analysis_rows = []
    service.performance_analyzer = type(
        "XPL",
        (), {"get_return_analysis_v1": lambda _self, rows: (analysis_rows.extend(rows) or {}, {})},
    )()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)

    kline = [
        {"stock_date": "2026-01-01", "stock_val": 8.5, "open": 10, "high": 14, "low": 8, "close": 12, "vwap": 11},
        {"stock_date": "2026-01-02", "stock_val": 9.5, "open": 12, "high": 15, "low": 11, "close": 13, "vwap": 12},
    ]
    success, _result = service._execute_parameter_combination(
        10,
        {"stock_code": "600000", "kline_key": "2026-2026", "random_group": 1},
        {"combination": {}},
        {"kline_source": "auto", "market_type": "cn"},
        {"2026-2026": kline},
    )

    assert success is True
    assert sheet.clear_calls == ["AA2:AG12"]
    assert sheet.update_input_options == ["USER_ENTERED"]
    assert sheet.update_payloads[0] == {
        "AA2": "2026-01-01",
        "AB2": 10,
        "AC2": 14,
        "AD2": 8,
        "AE2": 12,
        "AF2": 11,
        "AG2": 8.5,
        "AA3": "2026-01-02",
        "AB3": 12,
        "AC3": 15,
        "AD3": 11,
        "AE3": 13,
        "AF3": 12,
        "AG3": 9.5,
    }
    assert analysis_rows[0] == {"date": "2026-01-01", "index_return": 0.0, "start_return": 0.1}
    # 指数统一取 AG 列随机价（stock_val）累计口径，与表内 Index Return 汇总同源
    assert abs(analysis_rows[1]["index_return"] - (9.5 / 8.5 - 1)) < 1e-12
    assert analysis_rows[1]["start_return"] == 0.2


def test_c1_1_annualized_collapsed_threshold():
    assert _annualized_collapsed("-100.00%")
    assert _annualized_collapsed(-100)
    assert not _annualized_collapsed("-99.99%")
    assert not _annualized_collapsed(None)
    assert not _annualized_collapsed("#NUM!")


def test_c1_1_total_loss_passes_without_signal_change(monkeypatch):
    block = {f"F{row}": "" for row in range(2, 27)}
    block.update({"F5": "-100.00%", "F6": "-100.00%"})
    sheet = _C1_1ExecuteSheet(dict(block), dict(block))
    service = C1_1Service({"kline_source": "auto", "market_type": "cn"}, "task-id")
    service.google_sheets = [sheet]
    service.performance_analyzer = type(
        "XPL",
        (), {"get_return_analysis_v1": lambda _self, rows: ({}, {})},
    )()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)

    kline = [
        {"stock_date": "2026-01-01", "stock_val": 8.5, "open": 10, "high": 14, "low": 8, "close": 12, "vwap": 11},
        {"stock_date": "2026-01-02", "stock_val": 9.5, "open": 12, "high": 15, "low": 11, "close": 13, "vwap": 12},
    ]
    success, _result = service._execute_parameter_combination(
        10,
        {"stock_code": "600000", "kline_key": "2026-2026", "random_group": 1},
        {"combination": {}},
        {"kline_source": "auto", "market_type": "cn"},
        {"2026-2026": kline},
    )

    assert success is True


# ---- 结果块字段映射 ----


def test_c1_1_custom_kline_reads_ohlc_and_vwap():
    service = C1_1Service({"kline_source": "custom"}, "task-id")
    service.google_sheets = [_C1_1CustomSheet()]
    monkey_min = lambda *args, **kwargs: 1
    service._get_min_kline_rows = monkey_min

    kline_map = service._load_custom_kline_map({"kline_source": "custom"})
    rows = kline_map["custom"]

    assert len(rows) == 2
    assert rows[0]["stock_date"] == "2026-01-01"
    assert rows[0]["open"] == 10
    assert rows[0]["close"] == 12
    assert rows[0]["vwap"] == 11


def test_c7_invalid_still_rejects_empty():
    with pytest.raises(Exception):
        normalize_check_values({"AI4": ""}, invalid_predicate=C7_INVALID)


# ---- 创建配置归一化 ----

def test_c1_1_creation_normalizes_random_price():
    from app.services.task.creation import _normalize_c1_1_random_price_config

    normalized = _normalize_c1_1_random_price_config({
        "market_type": "cn",
        "random_price_range": "OPEN_CLOSE",
        "random_group_count": "3",
    })

    assert normalized["price_mode"] == "random_price"
    assert normalized["random_price_range"] == "open_close"
    assert normalized["random_group_count"] == 3


def test_c1_1_creation_keeps_custom_mode_without_price_mode():
    from app.services.task.creation import _normalize_c1_1_random_price_config

    normalized = _normalize_c1_1_random_price_config({
        "kline_source": "custom",
        "price_mode": None,
        "random_price_range": "high_low",
        "random_group_count": 2,
    })

    assert normalized.get("price_mode") is None


def test_c1_1_creation_rejects_invalid_random_range():
    from app.exceptions import ValidationError
    from app.services.task.creation import _normalize_c1_1_random_price_config

    with pytest.raises(ValidationError):
        _normalize_c1_1_random_price_config({"random_price_range": "mid_low"})


def test_c1_1_creation_normalizes_random_series_mode():
    from app.services.task.creation import _normalize_c1_1_random_price_config

    normalized = _normalize_c1_1_random_price_config({
        "random_series_mode": " FULL_TRUNCATE ",
    })
    assert normalized["random_series_mode"] == "full_truncate"

    defaulted = _normalize_c1_1_random_price_config({})
    assert defaulted["random_series_mode"] == "per_window"


def test_c1_1_creation_rejects_invalid_random_series_mode():
    from app.exceptions import ValidationError
    from app.services.task.creation import _normalize_c1_1_random_price_config

    with pytest.raises(ValidationError):
        _normalize_c1_1_random_price_config({"random_series_mode": "by_year"})


def test_c7_creation_pops_random_series_mode_when_not_random_price():
    from app.services.task.creation import _normalize_c7_random_price_config

    normalized = _normalize_c7_random_price_config({
        "price_mode": "sp_price",
        "random_price_range": "high_low",
        "random_group_count": 2,
        "random_series_mode": "full_truncate",
    })

    assert "random_series_mode" not in normalized
    assert "random_price_range" not in normalized
    assert "random_group_count" not in normalized


def test_c1_1_task_config_shape_validation():
    from app.schemas.task_configs import validate_task_config_shape

    shape = validate_task_config_shape("google_sheet_C1_1", {
        "sheets": [{"spreadsheet_id": "s1"}],
        "parameters": [["600000"]],
        "price_mode": "random_price",
        "random_group_count": 2,
    })

    assert shape["sheets"][0]["spreadsheet_id"] == "s1"
    assert shape["random_group_count"] == 2
    assert shape["price_mode"] == "random_price"
