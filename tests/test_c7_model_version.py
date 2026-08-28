from datetime import date, timedelta

from app.services.google_sheet_client import GoogleSheet
from app.services.kline_service import KlineService
from app.services.google_sheet_service_C7 import GoogleSheetService


class _C7V03Sheet:
    title = "C7.0.3"
    spreadsheet_id = "c7-v03-sheet"

    def __init__(self):
        self.clear_calls = []
        self.update_payloads = []
        self.analysis_rows = []

    def get_last_row(self, column):
        assert column in {"CC", "CD", "CE", "CF", "CG"}
        return 4

    def clear_range(self, range_a1):
        self.clear_calls.append(range_a1)

    def get_range(self, range_a1):
        assert range_a1 == "D2:D3"
        return {"D2": "0", "D3": "0"}

    def update_jumped_cells(self, payload):
        self.update_payloads.append(dict(payload))

    def get_ranges(self, ranges):
        if ranges == ["D2:D3", "G1:H1"]:
            return {
                "D2:D3": {"D2": "1", "D3": "2"},
                "G1:H1": {"G1": "xm:1", "H1": "ml:2"},
            }
        assert ranges == ["E2:E3", "L2:L3"]
        return {
            "E2:E3": {"E2": "3", "E3": "4"},
            "L2:L3": {"L2": "#DIV/0!", "L3": "40%"},
        }


def _c7_v03_config():
    return {
        "sheets": [{"spreadsheet_id": "c7-v03-sheet", "c7_model_version": "c7_0_3"}],
        "c7_parameter_positions": ["A1", "B1"],
        "c7_check_positions": ["G1", "H1"],
        "c7_0_3_kline_start_row": 2,
        "c7_0_3_kline_date_column": "CC",
        "c7_0_3_kline_open_column": "CD",
        "c7_0_3_kline_high_column": "CE",
        "c7_0_3_kline_low_column": "CF",
        "c7_0_3_kline_close_column": "CG",
        "c7_0_3_output_range_1": "D2:D3",
        "c7_0_3_output_range_2": "E2:E3",
        "c7_0_3_output_column_j": "J",
        "c7_0_3_output_column_l": "L",
        "market_type": "cn",
    }


def test_c7_v03_uses_ohlc_layout_and_c5_result_range(monkeypatch):
    service = GoogleSheetService({}, "task-id")
    sheet = _C7V03Sheet()
    service.google_sheets = [sheet]
    service.xpl = type(
        "XPL",
        (), {"get_return_analysis_v1": lambda _self, rows: (sheet.analysis_rows.extend(rows) or {}, {})},
    )()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)

    kline_map = {
        "2026-2025": [
            {
                "stock_date": "2025-01-01",
                "stock_val": 10,
                "open": 9,
                "high": 11,
                "low": 8,
                "close": 10,
            },
            {
                "stock_date": "2025-01-02",
                "stock_val": 11,
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 11,
            },
        ]
    }

    success, _result = service._execute_parameter_combination(
        10,
        {"A1": "1", "B1": "2", "stock_code": "600000", "Kline_key": "2026-2025"},
        {"combination": {}},
        _c7_v03_config(),
        kline_map,
    )

    assert success is True
    assert sheet.clear_calls == ["CC2:CG12"]
    assert sheet.update_payloads[0] == {
        "A1": "xm:1",
        "B1": "ml:2",
        "CC2": "2025-01-01",
        "CD2": 9,
        "CE2": 11,
        "CF2": 8,
        "CG2": 10,
        "CC3": "2025-01-02",
        "CD3": 10,
        "CE3": 12,
        "CF3": 9,
        "CG3": 11,
    }
    assert sheet.analysis_rows[0] == {
        "date": "2025-01-01",
        "index_return": 0.0,
        "start_return": 0,
    }
    assert sheet.analysis_rows[1]["date"] == "2025-01-02"
    assert abs(sheet.analysis_rows[1]["index_return"] - 0.1) < 1e-12
    assert sheet.analysis_rows[1]["start_return"] == 0.4


def test_c7_v03_result_payload_uses_c5_metric_cells():
    service = object.__new__(GoogleSheetService)
    service.task_id = "task-c7-v03"

    payload = service._build_stock_param_result_payload(
        "C7.0.3 测试",
        0,
        {"A1": "1", "B1": "2", "kline": [], "c7_model_version": "c7_0_3"},
        {"C7.0.3": {"D2": "10%", "D3": "11%", "D4": "-5%", "D5": "7%", "D6": "8%", "D7": "-6%"}},
    )

    assert payload["return_rate"] == 0.1
    assert payload["annualized_rate"] == 0.11
    assert payload["maxdd"] == -0.05
    assert payload["index_rate"] == 0.07


def test_c7_v03_rewrites_kline_when_stock_changes(monkeypatch):
    service = GoogleSheetService({}, "task-id")
    sheet = _C7V03Sheet()
    service.google_sheets = [sheet]
    service.xpl = type(
        "XPL",
        (), {"get_return_analysis_v1": lambda _self, rows: ({}, {})},
    )()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)

    kline = [{
        "stock_date": "2025-01-01",
        "stock_val": 10,
        "open": 9,
        "high": 11,
        "low": 8,
        "close": 10,
    }, {
        "stock_date": "2025-01-02",
        "stock_val": 11,
        "open": 10,
        "high": 12,
        "low": 9,
        "close": 11,
    }]
    success, _result = service._execute_parameter_combination(
        10,
        {"A1": "1", "B1": "2", "stock_code": "600001", "Kline_key": "2026-2025"},
        {"combination": {"stock_code": "600000", "Kline_key": "2026-2025"}},
        _c7_v03_config(),
        {"2026-2025": kline},
    )

    assert success is True
    assert sheet.clear_calls == ["CC2:CG12"]
    assert sheet.update_payloads[0]["CC2"] == "2025-01-01"


def test_c7_model_version_falls_back_to_sheet_title():
    service = GoogleSheetService({}, "task-id")
    sheet = type("Sheet", (), {"spreadsheet_id": "sheet-v03", "title": "C7.0.3.v20260729"})()
    config = {"sheets": [{"spreadsheet_id": "sheet-v03"}]}

    assert service._get_c7_model_version(config, sheet) == "c7_0_3"


def test_get_last_row_supports_multi_letter_column():
    google_sheet = object.__new__(GoogleSheet)
    google_sheet.worksheet = type(
        "Worksheet",
        (), {"col_values": lambda _self, column_number: ["header", "value"] if column_number == 81 else []},
    )()

    assert google_sheet.get_last_row("CC") == 2


def test_c7_deduplicates_same_parameters_and_kline_period():
    service = object.__new__(GoogleSheetService)
    logs = []
    service._log_info = logs.append
    same_kline = [
        {"stock_date": "2021-08-05"},
        {"stock_date": "2026-08-05"},
    ]

    combinations = [
        {"stock_code": "688235", "A1": "2.3", "B1": "3", "Kline_key": "full"},
        {"stock_code": "688235", "A1": "2.3", "B1": "3", "Kline_key": "recent_5"},
        {"stock_code": "688235", "A1": "2.3", "B1": "4", "Kline_key": "recent_5"},
    ]

    result = service._deduplicate_parameter_combinations(
        combinations,
        {"full": same_kline, "recent_5": same_kline},
    )

    assert result == [combinations[0], combinations[2]]
    assert len(logs) == 1
    assert "跳过重复 C7 参数组合" in logs[0]


def test_c7_resume_starts_after_last_completed_combination():
    assert GoogleSheetService._get_resume_start_index(0, 6) == 0
    assert GoogleSheetService._get_resume_start_index(5, 6) == 5
    assert GoogleSheetService._get_resume_start_index(6, 6) == 6


def test_c7_random_price_builds_requested_high_low_groups(monkeypatch):
    service = GoogleSheetService({}, "task-id")
    rows = []
    first_date = date(2026, 1, 1)
    for offset in range(31):
        current_date = first_date + timedelta(days=offset)
        rows.append({
            "stock_date": current_date.isoformat(),
            "open": 10,
            "high": 14,
            "low": 8,
            "close": 12,
            "vwap": 11,
        })

    monkeypatch.setattr(
        "app.services.google_sheet_service_C7.upsert_stock_metadata_in_session",
        lambda _payload: None,
    )
    monkeypatch.setattr(
        service.dfcf_api,
        "get_search_list_by_stock_code",
        lambda _stock_code, _limit: [{"market": "1", "shortName": "测试股票"}],
    )
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: rows,
    )
    combinations, _column_length, kline_map = service._get_all_parameters(
        "600000",
        "total",
        "random_price",
        "2026-01-31",
        "2026-01-01",
        "cn",
        [],
        [],
        [["600000"], [1], [2]],
        random_price_range="high_low",
        random_group_count=2,
    )

    assert len(combinations) == 2
    assert [item["random_group"] for item in combinations] == [1, 2]
    assert len(kline_map) == 2
    assert all(8 <= row["stock_val"] <= 14 for kline in kline_map.values() for row in kline)


def test_c7_random_open_close_handles_close_above_open(monkeypatch):
    monkeypatch.setattr(
        "app.services.kline_service.random.uniform",
        lambda low, high: (low, high),
    )

    projected = KlineService.build_price_rows(
        [
            {
                "stock_date": "2026-01-01",
                "open": 10,
                "high": 13,
                "low": 8,
                "close": 12,
            }
        ],
        "random_price",
        include_ohlc=True,
        random_price_range="open_close",
    )[0]

    assert projected["stock_val"] == (10, 12)


def test_c7_random_groups_are_stable_for_task_restart():
    service = object.__new__(GoogleSheetService)
    service.task_id = "task-random-price"
    combinations = [{
        "stock_code": "600000",
        "A1": 1,
        "B1": 2,
        "year": "2026-2025",
        "Kline_key": "2026-2025",
    }]
    kline_map = {
        "2026-2025": [{
            "stock_date": "2026-01-01",
            "open": 10,
            "high": 14,
            "low": 8,
            "close": 12,
            "stock_val": 12,
        }]
    }

    first = service._expand_random_price_groups(
        combinations, kline_map, "random_price", "high_low", 2
    )
    second = service._expand_random_price_groups(
        combinations, kline_map, "random_price", "high_low", 2
    )

    assert first == second


def test_c7_uses_first_available_kline_when_listing_is_newer_than_start_date(monkeypatch):
    service = GoogleSheetService({}, "task-id")
    logs = []
    first_date = date(2021, 12, 15)
    rows = []
    for offset in range(30):
        current_date = first_date + timedelta(days=offset)
        rows.append({
            "stock_date": current_date.isoformat(),
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10,
            "vwap": 10,
        })
    rows.append({
        "stock_date": "2026-08-05",
        "open": 11,
        "high": 12,
        "low": 10,
        "close": 11,
        "vwap": 11,
    })

    monkeypatch.setattr(
        "app.services.google_sheet_service_C7.upsert_stock_metadata_in_session",
        lambda _payload: None,
    )
    monkeypatch.setattr(service, "_log_info", logs.append)
    monkeypatch.setattr(
        service.dfcf_api,
        "get_search_list_by_stock_code",
        lambda _stock_code, _limit: [{"market": "1", "shortName": "测试股票"}],
    )
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: rows,
    )

    _combinations, _column_length, kline_map = service._get_all_parameters(
        "688235",
        "total",
        "ohlc_price",
        "2026-08-05",
        "2021-08-05",
        "cn",
        [],
        [],
        [["688235"], [1], [2]],
    )

    kline = next(iter(kline_map.values()))
    assert kline[0]["stock_date"] == "2021-12-15"
    assert kline[-1]["stock_date"] == "2026-08-05"
    assert any("将从 2021-12-15 开始回测" in message for message in logs)
