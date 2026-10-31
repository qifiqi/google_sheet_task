# -*- coding: utf-8 -*-
"""任务维度股票代码提取：统一读 stock_codes 投影，不再依赖任务名解析。"""

import json

import pytest

from app.models import Task
from app.schemas.task_configs import primary_stock_code
from app.services.model_summary.extractor import _extract_stock_code


class TestPrimaryStockCode:
    def test_prefers_first_projected_code(self):
        assert primary_stock_code({"stock_codes": ["ABBV", "ADI"]}) == "ABBV"

    def test_skips_blank_codes(self):
        assert primary_stock_code({"stock_codes": ["", "  ", "SOXX"]}) == "SOXX"

    def test_falls_back_to_execution_field(self):
        assert primary_stock_code({"stock_code": "GLD.US"}) == "GLD.US"

    def test_empty_when_nothing_declared(self):
        assert primary_stock_code({"stock_codes": []}) == ""
        assert primary_stock_code({}) == ""


class TestExtractorUsesProjection:
    @pytest.mark.parametrize("task_type, name, expected", [
        ("google_sheet_C7", "C7.0.2-美股个股-20-4", "ABBV.US"),
        ("google_sheet_C5", "C5-AMD-超威半导体-3.15%-sp", "AMD.US"),
        ("google_sheet", "GLD-bdl-1y-0", "GLD.US"),
    ])
    def test_config_projection_wins_over_task_name(self, task_type, name, expected):
        task = Task(id="t-extract", name=name, task_type=task_type, config=json.dumps({
            "sheets": [{"spreadsheet_id": "s"}],
            "market_type": "en",
            "stock_codes": ["ABBV", "ADI"] if task_type == "google_sheet_C7" else (
                ["AMD"] if task_type == "google_sheet_C5" else ["GLD"]
            ),
        }))
        assert _extract_stock_code(task, {}) == expected

    def test_parameters_stock_code_still_wins(self):
        task = Task(id="t-extract-2", name="C7.0.2-美股个股-20-4", task_type="google_sheet_C7",
                    config=json.dumps({"stock_codes": ["ABBV", "ADI"], "market_type": "en"}))
        assert _extract_stock_code(task, {"stock_code": "XBI"}) == "XBI.US"
