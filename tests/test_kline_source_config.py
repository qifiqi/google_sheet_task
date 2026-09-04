import pytest

from app.domain_constants import GoogleSheetTokenTaskType
from app.services.google_sheet_service_C5 import GoogleSheetService as C5GoogleSheetService
from app.services.google_sheet_service_C7 import GoogleSheetService as C7GoogleSheetService
from app.services.task.creation import TaskCreationMixin


class _TaskCreation(TaskCreationMixin):
    pass


def test_task_config_accepts_tdx_kline_source():
    normalized = _TaskCreation()._normalize_task_config_for_type(
        "google_sheet",
        {"kline_data_source": "tdx"},
    )

    assert normalized["kline_data_source"] == "tdx"


class _CustomKlineSheet:
    def get_last_row(self, column):
        assert column == "A"
        return 31

    def get_range(self, range_name):
        assert range_name == "A2:B31"
        values = {}
        for index in range(30):
            row_num = index + 2
            values[f"A{row_num}"] = f"2024-01-{index + 1:02d}"
            values[f"B{row_num}"] = 10 + index
        return values


def test_c5_custom_kline_config_normalizes_disabled_options():
    config = {
        "kline_source": "custom",
        "count_mode": "total",
        "parameters": [["600000"], ["p1"]],
        "sheets": [{"spreadsheet_id": "sheet-id"}],
    }

    normalized = _TaskCreation()._normalize_task_config_for_type("google_sheet_C5", config)

    assert normalized["kline_source"] == "custom"
    assert normalized["count_mode"] == "total"
    assert normalized["market_type"] == "custom"
    assert normalized["price_mode"] is None
    assert normalized["kline_adjustment"] is None
    assert normalized["date_range_mode"] == []
    assert normalized["exclude_recent_years"] == []
    assert normalized["start_date"] is None
    assert normalized["end_date"] is None
    assert normalized["token_task_type"] == GoogleSheetTokenTaskType.GOOGLE_SHEET.value


def test_c7_rejects_invalid_kline_source():
    with pytest.raises(ValueError, match="kline_source"):
        _TaskCreation()._normalize_task_config_for_type(
            "google_sheet_C7",
            {"kline_source": "manual"},
        )


def test_c7_random_price_config_uses_defaults_and_validates_group_count():
    normalized = _TaskCreation()._normalize_task_config_for_type(
        "google_sheet_C7",
        {"kline_source": "auto", "price_mode": "random_price"},
    )

    assert normalized["random_price_range"] == "high_low"
    assert normalized["random_group_count"] == 1

    with pytest.raises(ValueError, match="随机组数"):
        _TaskCreation()._normalize_task_config_for_type(
            "google_sheet_C7",
            {
                "kline_source": "auto",
                "price_mode": "random_price",
                "random_group_count": 0,
            },
        )

    with pytest.raises(ValueError, match="随机组数"):
        _TaskCreation()._normalize_task_config_for_type(
            "google_sheet_C7",
            {
                "kline_source": "auto",
                "price_mode": "random_price",
                "random_group_count": 1.5,
            },
        )


def test_c7_random_price_rejects_c7_0_3_sheet():
    with pytest.raises(ValueError, match="C7.0.2"):
        _TaskCreation()._normalize_task_config_for_type(
            "google_sheet_C7",
            {
                "kline_source": "auto",
                "price_mode": "random_price",
                "sheets": [{"spreadsheet_id": "sheet-id", "c7_model_version": "c7_0_3"}],
            },
        )


@pytest.mark.parametrize("service_cls", [C5GoogleSheetService, C7GoogleSheetService])
def test_custom_kline_parameters_use_existing_sheet_kline_without_auto_conversion(app_factory, service_cls):
    with app_factory.app_context():
        service = service_cls({}, "task-id")
        service.google_sheets = [_CustomKlineSheet()]

        custom_kline = service._get_custom_kline_data("A", "B")
        combinations, column_length, kline_map = service._get_custom_parameters(
            "SOXX",
            [["SOXX"], [1, 2], [3]],
            {"custom": custom_kline},
        )

    assert len(custom_kline) == 30
    assert len(combinations) == 2
    assert column_length == 50
    assert kline_map == {"custom": custom_kline}
    assert {combination["Kline_key"] for combination in combinations} == {"custom"}
    assert [combination["A1"] for combination in combinations] == [1, 2]


def test_custom_kline_rejects_market_selection():
    with pytest.raises(ValueError, match="A股/美股"):
        _TaskCreation()._normalize_task_config_for_type(
            "google_sheet_C5",
            {
                "kline_source": "custom",
                "count_mode": "total",
                "market_type": "cn",
            },
        )
