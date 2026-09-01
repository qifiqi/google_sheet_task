from datetime import date, timedelta
from pathlib import Path

import matplotlib.image as mpimg

from app.services import strategy_backtest_report_charts as charts


def _chart_data() -> dict:
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(24)]
    return {
        "dates": dates,
        "index_nav": [1 + index * 0.01 for index in range(24)],
        "strategy_nav": [1 + index * 0.012 for index in range(24)],
        "excess_nav": [index * 0.002 for index in range(24)],
        "annual_returns": {"years": ["2024", "2025"], "index": [0.1, -0.02], "strategy": [0.15, 0.04]},
        "index_daily_returns": [-0.02, -0.01, 0.0, 0.01, 0.02],
        "strategy_daily_returns": [-0.01, 0.0, 0.01, 0.02, 0.03],
        "monthly_excess_returns": [-0.03, -0.01, 0.0, 0.02, 0.04],
    }


def test_generate_report_charts_outputs_all_pngs_with_static_fonts(tmp_path: Path):
    paths = charts.generate_report_charts(_chart_data(), tmp_path)

    assert set(paths) == {"累计净值曲线", "最大回撤曲线", "超额收益曲线", "分年度收益", "日收益分布", "月度超额分布"}
    assert charts.FONT_REGULAR_PATH.is_file()
    assert charts.FONT_BOLD_PATH.is_file()
    for path in paths.values():
        image = mpimg.imread(path)
        assert image.shape[:2] == (760, 1440)


def test_generate_report_charts_handles_constant_and_missing_annual_data(tmp_path: Path):
    data = _chart_data()
    data.update({
        "index_nav": [1.0],
        "strategy_nav": [1.0],
        "excess_nav": [0.0],
        "annual_returns": {},
        "index_daily_returns": [],
        "strategy_daily_returns": [],
        "monthly_excess_returns": [],
    })

    paths = charts.generate_report_charts(data, tmp_path)

    assert all(Path(path).is_file() for path in paths.values())
