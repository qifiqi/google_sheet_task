from types import SimpleNamespace

import pytest

from app.services.export_file_service import build_task_export


def test_c7_export_reads_shifted_metric_cells():
    task = SimpleNamespace(id="task-c7", name="C7 导出", task_type="google_sheet_C7")
    results = [
        {
            "id": 1,
            "task_id": "task-c7",
            "step_index": 0,
            "success": True,
            "parameters": {
                "A1": "2",
                "B1": "ml-a",
                "stock_code": "600000",
                "kline": [
                    {"stock_date": "2024-01-01"},
                    {"stock_date": "2024-12-31"},
                ],
            },
            "result": {
                "sheet-id__模型A": {
                    "D8": "10%",
                    "D9": "11%",
                    "D10": "-5%",
                    "D11": "7%",
                    "D12": "8%",
                    "D13": "-6%",
                    "D21": "unused",
                    "D23": "1.23%",
                    "D26": "2.34%",
                    "flat_result": {
                        "start_monthly_std_dev": 0.1111,
                        "index_monthly_std_dev": 0.2222,
                        "index_sharpe_ratio": 1.5,
                        "start_sharpe_ratio": 2.5,
                    },
                },
            },
        }
    ]

    export = build_task_export(task, results)
    sheet = export.workbook.active
    row = [cell.value for cell in sheet[2]]

    assert row[:10] == [
        2,
        "ml-a",
        0.03,
        0.01,
        0.1,
        0.11,
        -0.05,
        0.07,
        0.08,
        -0.06,
    ]
    assert row[10:] == pytest.approx([
        0.0123,
        0.0234,
        0.1111,
        0.2222,
        1.5,
        2.5,
    ])
