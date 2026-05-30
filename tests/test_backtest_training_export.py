from app.routes.backtest_training import _build_global_preview_workbook, _extract_summary_rows


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


def test_single_global_preview_derives_year_max_excess_drawdown_with_string_years():
    calculate_metrics = {
        "excess_returns": [
            {
                "year": "2024",
                "index_annualized_return": 0.10,
                "start_annualized_return": 0.18,
                "annualized_return_diff": 0.08,
                "start_end_date": "2024-01-01 00:00:00/2024-12-31 00:00:00",
            },
            {
                "year": "all",
                "index_annualized_return": 0.10,
                "start_annualized_return": 0.18,
                "annualized_return_diff": 0.08,
                "start_end_date": "2024-01-01 00:00:00/2024-12-31 00:00:00",
            },
        ],
        "index_profit_annual": 1,
        "start_profit_annual": 1,
        "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "index_sharpe_ratios": {"all": {"avg_monthly_return": 0.01, "sharpe_ratio": 1}},
        "start_sharpe_ratios": {"all": {"avg_monthly_return": 0.02, "sharpe_ratio": 2}},
        "index_monthly_return_volatility": 0.03,
        "start_monthly_return_volatility": 0.04,
        "outperform_year": 1,
        "monthly_excess_return_percentage": [{"year": "all", "excess_return": 1}],
        "monthly_excess_returns": [{
            "date": "2024-01",
            "start_monthly_return": 0.02,
            "monthly_excess_return_diff": 0.01,
        }],
        "monthly_excess_volatility": 0.01,
        "index_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.10}],
        },
        "start_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.06}],
            "total_maximum_drawdown": {"drawdown": 0.06},
        },
        "excess_drawdown_winning_rate": 1,
        "index_kama_ratio": [{"year": "all", "kama_ratio": 1}],
        "start_kama_ratio": [{"year": "all", "kama_ratio": 2}],
        "index_sotino_ratio": [{"year": "all", "sotino_ratio": 1}],
        "start_sotino_ratio": [{"year": "all", "sotino_ratio": 2}],
        "excess_sharp": 1,
        "excess_of_promissory_note": 1,
        "start_maximum_number_of_backtest_repair_days": 3,
        "excess_maximum_number_of_backtest_repair_days": 2,
    }

    _period_text, rows = _extract_summary_rows(calculate_metrics, "C3")

    drawdown_row = next(row for row in rows if row["metric"] == "年最大超额回撤")
    assert drawdown_row["model_value"] == "4.00%"
