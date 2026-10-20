"""C31 拆分子任务时保留 per-sheet 扩展键。"""
from app.services.task.creation import _build_c31_child_sheet


def test_c31_child_sheet_preserves_extension_keys():
    sheet = {
        "spreadsheet_id": "sid",
        "sheet_name": "data",
        "title": "策略-1y-1]",
        "sort_n": 1,
        "year_n": "1y",
        "c3_input_column_a": "D",
        "c3_output_column_d": "E",
        "extension_key": "kept",
    }

    payload = _build_c31_child_sheet(sheet, "sid", "data", "策略-1y-1]")

    assert payload["c3_input_column_a"] == "D"
    assert payload["c3_output_column_d"] == "E"
    assert payload["extension_key"] == "kept"
    assert payload["spreadsheet_id"] == "sid"
    assert payload["sheet_name"] == "data"
    assert "sort_n" not in payload
    assert "year_n" not in payload
