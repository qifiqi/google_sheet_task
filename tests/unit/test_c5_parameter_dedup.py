from app.services.google_sheet_service_C5 import GoogleSheetService


def test_c5_resume_starts_after_last_completed_combination():
    assert GoogleSheetService._get_resume_start_index(0, 6) == 0
    assert GoogleSheetService._get_resume_start_index(5, 6) == 5
    assert GoogleSheetService._get_resume_start_index(6, 6) == 6


def test_c5_deduplicates_same_parameters_and_kline_period():
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
    assert "跳过重复 C5 参数组合" in logs[0]
