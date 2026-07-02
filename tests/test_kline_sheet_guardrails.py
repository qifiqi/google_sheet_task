from datetime import datetime, timedelta

import pytest

from app.services.google_sheet_service import GoogleSheetService as C3GoogleSheetService
from app.services.google_sheet_service_C4 import GoogleSheetService as C4GoogleSheetService
from app.services.google_sheet_service_C5 import GoogleSheetService as C5GoogleSheetService


def _kline_rows(start_date, end_date):
    current = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    rows = []
    while current <= end:
        rows.append({
            "stock_date": current.strftime("%Y-%m-%d"),
            "stock_kp": 9,
            "stock_sp": 10,
        })
        current += timedelta(days=1)
    return rows


class _FakeSheet:
    title = "fake-sheet"

    def __init__(self):
        self.updates = []

    def update_jumped_cells(self, cell_updates):
        self.updates.append(cell_updates)


def _c3_config(end_date):
    return {
        "stock_code": "600000",
        "year_n": "1y",
        "price_mode": "sp_price",
        "end_date": end_date,
        "market_type": "cn",
        "C3_commission_cell": "B5",
        "c3_input_column_d": "D",
        "c3_input_column_e": "E",
    }


def test_c3_allows_historical_end_date_before_latest_kline():
    service = C3GoogleSheetService({}, "task-id")
    service.google_sheet = _FakeSheet()
    service.dfcf_api.get_search_list_by_stock_code = lambda *_args, **_kwargs: [{"market": "1"}]
    service.dfcf_api.get_stock_kline_data = (
        lambda *_args, **_kwargs: _kline_rows("2023-01-01", "2025-12-31")
    )

    service.cell_kline_data(_c3_config("2024-04-23"))

    updated = service.google_sheet.updates[0]
    assert updated["D2"] == "2023-04-24"
    assert updated["E2"] == 10
    assert service.kline[-1]["stock_date"] == "2024-04-23"


def test_c3_rejects_end_date_after_latest_kline_without_writing_sheet():
    service = C3GoogleSheetService({}, "task-id")
    service.google_sheet = _FakeSheet()
    service.dfcf_api.get_search_list_by_stock_code = lambda *_args, **_kwargs: [{"market": "1"}]
    service.dfcf_api.get_stock_kline_data = (
        lambda *_args, **_kwargs: _kline_rows("2023-01-01", "2025-12-31")
    )

    with pytest.raises(Exception, match="不在K线数据范围"):
        service.cell_kline_data(_c3_config("2026-01-05"))

    assert service.google_sheet.updates == []


def test_c3_empty_kline_does_not_write_sheet():
    service = C3GoogleSheetService({}, "task-id")
    service.google_sheet = _FakeSheet()
    service.dfcf_api.get_search_list_by_stock_code = lambda *_args, **_kwargs: [{"market": "1"}]
    service.dfcf_api.get_stock_kline_data = lambda *_args, **_kwargs: []

    with pytest.raises(ValueError, match="没有可用K线数据"):
        service.cell_kline_data(_c3_config("2024-04-23"))

    assert service.google_sheet.updates == []


def test_c4_execute_parameter_combination_reraises_sheet_errors():
    service = C4GoogleSheetService({}, "task-id")

    class BrokenSheet:
        title = "broken"

        def clear_range(self, _range):
            raise RuntimeError("sheet unavailable")

    service.google_sheets = [BrokenSheet()]

    with pytest.raises(RuntimeError, match="sheet unavailable"):
        service._execute_parameter_combination(
            10,
            {"kline": [{"stock_date": "2024-01-01", "stock_val": 10}]},
            {
                "c4_input_column_a": "A",
                "c4_input_column_b": "B",
                "c4_output_range_1": "D2:D3",
                "c4_output_range_2": "E2:E3",
                "c4_output_column_j": "J",
                "c4_output_column_l": "L",
            },
        )


def test_c5_recent_mode_skips_empty_ranges_and_raises_when_none_left():
    service = C5GoogleSheetService({}, "task-id")
    service.dfcf_api.get_search_list_by_stock_code = lambda *_args, **_kwargs: [{"market": "1"}]
    service.dfcf_api.get_stock_kline_data = (
        lambda *_args, **_kwargs: _kline_rows("2024-01-01", "2024-12-31")
    )

    with pytest.raises(ValueError, match="没有可执行K线组合"):
        service._get_all_parameters(
            "600000",
            "n_plus_1",
            "sp_price",
            "2024-12-31",
            "2024-01-01",
            "cn",
            ["recent"],
            [1],
            [["600000"], [1], [2]],
        )
