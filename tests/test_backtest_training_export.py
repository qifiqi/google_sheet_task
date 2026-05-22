from app.routes.backtest_training import _build_global_preview_workbook


def test_global_preview_workbook_adds_summary_sheet_first():
    payload = {
        "task": {"stock_code": "TEST", "name": "单品回测"},
        "groups": [
            {
                "group_label": "2026-2023 年",
                "year": "2026-2023",
                "period": "",
                "columns": [
                    {
                        "column_key": "result_1",
                        "result_id": 1,
                        "header": "2.5/5",
                        "model_name": "C3",
                        "success": True,
                        "raw_metrics": {
                            "I15": "12%",
                            "I17": "-8%",
                            "I18": "5%",
                            "I20": "-10%",
                        },
                    },
                    {
                        "column_key": "result_2",
                        "result_id": 2,
                        "header": "3/5",
                        "model_name": "C5",
                        "success": True,
                        "raw_metrics": {
                            "D2": "20%",
                            "D4": "-6%",
                            "D5": "7%",
                            "D7": "-9%",
                        },
                    },
                ],
                "rows": [],
            }
        ],
    }

    workbook = _build_global_preview_workbook(payload)
    sheet = workbook.worksheets[0]

    assert sheet.title == "汇总"
    assert workbook.sheetnames[1] == "2026-2023 年"
    assert sheet["A1"].value == "周期"
    assert sheet["B1"].value == "名称"
    assert sheet["C1"].value == "2.5/5"
    assert sheet["D1"].value == "3/5"
    assert sheet["A2"].value == "2026-2023"
    assert sheet["B2"].value == "指数回报"
    assert sheet["C2"].value == "5.00%"
    assert sheet["D2"].value == "7.00%"
    assert sheet["C3"].value == "12.00%"
    assert sheet["D3"].value == "20.00%"
    assert sheet["B4"].value == "超额回报"
    assert sheet["C4"].value == "7.00%"
    assert sheet["D4"].value == "13.00%"
    assert sheet["C5"].value == "-10.00%"
    assert sheet["D5"].value == "-9.00%"
    assert sheet["C6"].value == "-8.00%"
    assert sheet["D6"].value == "-6.00%"
    assert sheet["B7"].value == "超额回撤"
    assert sheet["C7"].value == "2.00%"
    assert sheet["D7"].value == "3.00%"
    assert sheet["A1"].fill.fgColor.rgb == "00F7E1A1"
    assert sheet["B2"].fill.fgColor.rgb == "00F7E1A1"
