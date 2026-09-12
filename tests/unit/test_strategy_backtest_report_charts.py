import csv
from datetime import date, timedelta
from pathlib import Path

import matplotlib.image as mpimg
from matplotlib.colors import to_rgb

from app.services import strategy_backtest_report_charts as charts

# 真实组合收益夹具（累计收益率），用于验证刻度逻辑在真实数据范围下的表现。
FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "组合收益.csv"


def _load_fixture_returns() -> dict:
    """加载组合收益 CSV 并按服务语义转为图表序列。

    累计收益率加 1 即净值；日收益按净值复利差分；月度超额取每月最后
    一天净值差分后相减（与服务端 monthly_excess_return_diff 一致）。
    """
    rows = []
    with FIXTURE_CSV.open(encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            rows.append((date.fromisoformat(row["date"]), float(row["index_return"]), float(row["start_return"])))
    index_nav = [1.0 + row[1] for row in rows]
    strategy_nav = [1.0 + row[2] for row in rows]
    index_daily = [index_nav[offset] / index_nav[offset - 1] - 1 for offset in range(1, len(rows))]
    strategy_daily = [strategy_nav[offset] / strategy_nav[offset - 1] - 1 for offset in range(1, len(rows))]
    month_last = {}
    for offset, (current_date, _, _) in enumerate(rows):
        month_last[(current_date.year, current_date.month)] = offset
    monthly_excess = []
    previous = None
    for offset in sorted(month_last.values()):
        index_month = index_nav[offset] / index_nav[previous] - 1 if previous is not None else index_nav[offset] - 1.0
        strategy_month = (
            strategy_nav[offset] / strategy_nav[previous] - 1 if previous is not None else strategy_nav[offset] - 1.0
        )
        monthly_excess.append(strategy_month - index_month)
        previous = offset
    return {
        "index_nav": index_nav,
        "strategy_nav": strategy_nav,
        "index_daily": index_daily,
        "strategy_daily": strategy_daily,
        "monthly_excess": monthly_excess,
    }


def _chart_data() -> dict:
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(24)]
    index_nav = [1 + index * 0.01 for index in range(24)]
    strategy_nav = [1 + index * 0.012 for index in range(24)]

    def drawdown(values: list[float]) -> list[float]:
        peak, result = values[0], []
        for value in values:
            peak = max(peak, value)
            result.append(value / peak - 1)
        return result

    return {
        "dates": dates,
        "index_nav": index_nav,
        "strategy_nav": strategy_nav,
        # 回撤序列由服务端 _build_chart_data 预先算好，画图模块只消费。
        "index_drawdown": drawdown(index_nav),
        "strategy_drawdown": drawdown(strategy_nav),
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


def test_symmetric_histogram_limit_centers_positive_and_negative_values():
    limit = charts._symmetric_histogram_limit([-0.03, 0.05])

    assert limit == 0.05 * 1.05
    assert -limit < -0.03 < 0 < 0.05 < limit


def test_symmetric_histogram_limit_keeps_zero_data_visible():
    assert charts._symmetric_histogram_limit([0.0, 0.0]) == 0.0105


def test_symmetric_histogram_limit_ignores_rare_extremes():
    # 500 个 ±1% 内的样本 + 1 个 30% 极端值：分位数定轴，极值不再撑大范围。
    series = [0.01, -0.01] * 250 + [0.30]
    assert charts._symmetric_histogram_limit(series) == 0.0105
    assert charts._symmetric_histogram_limit([-0.30] + [0.01, -0.01] * 250) == 0.0105


def test_dual_histogram_uses_shared_zero_centered_core_limits(monkeypatch, tmp_path: Path):
    captured = {}

    def capture_figure(figure, path):
        captured["limits"] = [axis.get_xlim() for axis in figure.axes]

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    charts._draw_dual_histogram(
        tmp_path / "daily.png",
        "日收益率分布",
        {"index": [-0.02, 0.01], "strategy": [-0.01, 0.05]},
    )

    limit = charts._symmetric_histogram_limit([-0.02, 0.01, -0.01, 0.05])
    # 两个面板共用以 0 为中心的核心区间，便于左右对比。
    assert captured["limits"] == [(-limit, limit), (-limit, limit)]


def test_percent_tick_step_adapts_to_data_range():
    # 常规日收益范围（约 ±6.6%）每 2% 一个刻度，与报告样例一致。
    assert charts._percent_tick_step(0.066) == 0.02
    # 范围放大/缩小时步长随之增减，不写死 2%。
    assert charts._percent_tick_step(0.63) == 0.2
    assert charts._percent_tick_step(0.0105) == 0.0025
    # 月度超额 y 轴放宽预算：约 18%~20% 的跨度落到模板样式的 2.5% 间隔。
    assert charts._percent_tick_step(0.1822, max_intervals=8) == 0.025
    assert charts._percent_tick_step(0.202, max_intervals=8) == 0.025


def test_percent_tick_formatter_shows_plain_numbers_without_percent_sign():
    formatter = charts._percent_tick_formatter(0.02)
    assert formatter(0.0, None) == "0"
    assert formatter(0.02, None) == "2"
    assert formatter(-0.06, None) == "-6"
    # 步长小于 1% 时保留小数，避免刻度全部取整为 0。
    assert charts._percent_tick_formatter(0.005)(0.005, None) == "0.5"
    # 2.5 一族步长需要一位小数。
    assert charts._percent_tick_formatter(0.025)(0.025, None) == "2.5"
    assert charts._percent_tick_formatter(0.025)(0.075, None) == "7.5"
    # 阈值刻度显示为 <-X、>+X，标明尾部极值已归并进边缘箱。
    assert charts._percent_tick_formatter(0.01, overflow_limit=0.032865)(0.032865, None) == ">+3.3"
    assert charts._percent_tick_formatter(0.01, overflow_limit=0.032865)(-0.032865, None) == "<-3.3"
    assert charts._percent_tick_formatter(0.01, overflow_limit=0.032865)(0.02, None) == "2"


def test_percent_axes_put_unit_in_title_and_ticks_stay_plain(monkeypatch, tmp_path: Path):
    captured = {}

    def capture_figure(figure, path):
        figure.canvas.draw()
        axis = figure.axes[0]
        captured[path.stem] = (
            axis.get_ylabel(),
            [label.get_text() for label in axis.get_yticklabels()],
        )

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(24)]
    charts._draw_line_chart(
        tmp_path / "drawdown.png", "最大回撤曲线", dates,
        [("策略", [-index * 0.01 for index in range(24)], charts.ORANGE)], "回撤（%）", percent=True,
    )
    charts._draw_line_chart(
        tmp_path / "excess.png", "超额收益曲线", dates,
        [("累计超额收益", [index * 0.002 for index in range(24)], charts.RED)], "超额收益（%）", percent=True,
    )
    charts._draw_grouped_bar_chart(
        tmp_path / "annual.png", "分年度收益",
        {"years": ["2024", "2025"], "index": [0.1, -0.02], "strategy": [0.15, 0.04]},
    )

    assert set(captured) == {"drawdown", "excess", "annual"}
    for y_label, y_labels in captured.values():
        # 百分号单位只在轴标题上，刻度是纯数值。
        assert y_label.endswith("（%）")
        assert y_labels
        assert all("%" not in label for label in y_labels)


def test_dual_histogram_percent_ticks_are_symmetric_around_zero(monkeypatch, tmp_path: Path):
    captured = {}

    def capture_figure(figure, path):
        captured["ticks"] = [axis.get_xticks() for axis in figure.axes]

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    combined = [-0.02, 0.01, -0.01, 0.05]
    charts._draw_dual_histogram(
        tmp_path / "daily.png",
        "日收益率分布",
        {"index": combined[:2], "strategy": combined[2:]},
    )

    limit = charts._symmetric_histogram_limit(combined)
    assert len(captured["ticks"]) == 2
    for ticks in captured["ticks"]:
        assert ticks[0] == -ticks[-1]
        assert 0 in ticks
        assert all(-limit <= tick <= limit for tick in ticks)


def test_real_returns_dual_histogram_zooms_into_core_region(monkeypatch, tmp_path: Path):
    returns = _load_fixture_returns()
    captured = {}

    def capture_figure(figure, path):
        figure.canvas.draw()
        captured["limits"] = [axis.get_xlim() for axis in figure.axes]
        captured["ticks"] = [axis.get_xticks() for axis in figure.axes]
        captured["labels"] = [[label.get_text() for label in axis.get_xticklabels()] for axis in figure.axes]
        captured["x_label"] = figure.axes[0].get_xlabel()
        captured["titles"] = [axis.get_title() for axis in figure.axes]
        captured["bar_counts"] = [len(axis.patches) for axis in figure.axes]
        captured["height_sums"] = [sum(patch.get_height() for patch in axis.patches) for axis in figure.axes]
        captured["notes"] = [[text.get_text() for text in axis.texts] for axis in figure.axes]

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    charts._draw_dual_histogram(
        tmp_path / "daily.png",
        "日收益率分布",
        {"index": returns["index_daily"], "strategy": returns["strategy_daily"]},
    )

    # 核心区间按两组样本合并分位数确定（约 ±3.3%）并共用，超轴极端收益归并进边缘箱。
    limit = charts._symmetric_histogram_limit(returns["index_daily"] + returns["strategy_daily"])
    assert captured["limits"] == [(-limit, limit), (-limit, limit)]
    # 刻度只显示数值（单位 % 由轴标题说明），两端阈值刻度以 <-X、>+X 标记归并边界。
    assert captured["x_label"] == "日收益率（%）"
    # 面板小标题标明左右各是指数/策略。
    assert captured["titles"] == ["指数日收益分布", "策略日收益分布"]
    assert captured["labels"] == [["<-3.3", "-2", "-1", "0", "1", "2", ">+3.3"]] * 2
    assert captured["bar_counts"] == [33, 33]
    # 尾部极值归并进边缘箱：柱高之和仍等于样本总数，无数据被丢弃。
    assert captured["height_sums"] == [len(returns["index_daily"]), len(returns["strategy_daily"])]
    # 归并数量不在图内重复标注，由 Word 表格指标承载。
    assert captured["notes"] == [[], []]


def test_excess_combo_chart_overlays_daily_bars_on_cumulative_line(monkeypatch, tmp_path: Path):
    captured = {}

    def capture_figure(figure, path):
        figure.canvas.draw()
        captured["axes"] = len(figure.axes)
        captured["line_colors"] = [line.get_color() for axis in figure.axes for line in axis.lines]
        captured["bar_count"] = sum(len(axis.patches) for axis in figure.axes)
        captured["y_labels"] = [axis.get_ylabel() for axis in figure.axes]
        legend = figure.axes[0].get_legend()
        captured["legend_labels"] = [text.get_text() for text in legend.get_texts()]

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(24)]
    charts._draw_excess_line_bar_chart(
        tmp_path / "excess-combo.png", "累计超额收益曲线", dates,
        [index * 0.002 for index in range(24)],
        [(-0.001, 0.002)[index % 2] for index in range(24)],
    )

    # 双轴：左轴累计超额折线（红），右轴日超额柱状（正绿负红）。
    assert captured["axes"] == 2
    assert charts.RED in captured["line_colors"]
    assert captured["bar_count"] == 24
    assert captured["y_labels"] == ["累计超额收益（%）", "日超额收益（%）"]
    assert captured["legend_labels"] == ["日超额收益(正)", "日超额收益(负)", "累计超额收益"]


def test_real_returns_monthly_excess_bars_match_template_style(monkeypatch, tmp_path: Path):
    returns = _load_fixture_returns()
    captured = {}

    def capture_figure(figure, path):
        figure.canvas.draw()
        axis = figure.axes[0]
        captured["x_label"] = axis.get_xlabel()
        captured["y_label"] = axis.get_ylabel()
        captured["y_labels"] = [label.get_text() for label in axis.get_yticklabels()]
        captured["x_ticks"] = list(axis.get_xticks())
        captured["x_limits"] = axis.get_xlim()
        captured["bar_colors"] = [tuple(bar.get_facecolor()) for bar in axis.containers[0].patches]

    monkeypatch.setattr(charts, "_save_figure", capture_figure)
    charts._draw_monthly_excess_bars(tmp_path / "monthly.png", "月度超额分布", returns["monthly_excess"])

    positive_count = sum(1 for value in returns["monthly_excess"] if value >= 0)
    green = to_rgb(charts.GREEN)
    red = to_rgb(charts.LIGHT_RED)
    green_count = sum(1 for color in captured["bar_colors"] if color[:3] == green)
    red_count = sum(1 for color in captured["bar_colors"] if color[:3] == red)
    assert captured["x_label"] == "月份序号"
    assert captured["y_label"] == "月度超额收益（%）"
    # 正超额/负超额月数与绿/红柱一一对应。
    assert green_count == positive_count
    assert red_count == len(returns["monthly_excess"]) - positive_count
    # 月份序号恒为非负整数（定位器会返回视野外的候补刻度，需先过滤）。
    visible_x = [tick for tick in captured["x_ticks"] if captured["x_limits"][0] <= tick <= captured["x_limits"][1]]
    assert visible_x
    assert all(float(tick).is_integer() and tick >= 0 for tick in visible_x)
    assert captured["y_labels"]
    assert all("%" not in label for label in captured["y_labels"])
    assert "0.0" in captured["y_labels"]
    # y 轴按 1-2-2.5-5 序列自适应，本数据范围（约 18% 跨度）即 2.5% 间隔。
    y_values = [float(label) for label in captured["y_labels"]]
    assert all(abs(value / 2.5 - round(value / 2.5)) < 1e-9 for value in y_values)
    assert "2.5" in captured["y_labels"]


def test_histogram_bin_count_adapts_to_sample_size_and_range():
    returns = _load_fixture_returns()
    # 核心区间（指数 ±2.5%、策略 ±3.7%）内自适应细分行：箱宽约 0.2%。
    for series, expected_bins in ((returns["index_daily"], 25), (returns["strategy_daily"], 37)):
        limit = charts._symmetric_histogram_limit(series)
        assert charts._histogram_bin_count(series, limit) == expected_bins
    # 箱数始终被限制在 12~60 之间，小样本与常数序列也有可读的粒度。
    small = [value / 1000 for value in range(-50, 50)]
    assert 12 <= charts._histogram_bin_count(small, charts._symmetric_histogram_limit(small)) <= 60
    assert charts._histogram_bin_count([0.0], 0.0105) >= 12


def test_generate_report_charts_with_real_fixture_returns(tmp_path: Path):
    returns = _load_fixture_returns()
    paths = charts.generate_report_charts({
        "dates": [date(2016, 1, 4) + timedelta(days=offset) for offset in range(len(returns["index_nav"]))],
        "index_nav": returns["index_nav"],
        "strategy_nav": returns["strategy_nav"],
        "excess_nav": [
            strategy / index - 1 for index, strategy in zip(returns["index_nav"], returns["strategy_nav"])
        ],
        "index_daily_returns": returns["index_daily"],
        "strategy_daily_returns": returns["strategy_daily"],
        "monthly_excess_returns": returns["monthly_excess"],
        "annual_returns": {"years": ["2024", "2025"], "index": [0.1, -0.02], "strategy": [0.15, 0.04]},
    }, tmp_path)

    assert set(paths) == {"累计净值曲线", "最大回撤曲线", "超额收益曲线", "分年度收益", "日收益分布", "月度超额分布"}
    for path in paths.values():
        image = mpimg.imread(path)
        assert image.shape[:2] == (760, 1440)
