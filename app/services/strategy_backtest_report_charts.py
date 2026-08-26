"""策略回测报告图表模板。

本模块仅用假数据绘制报告示例图。真实接入时，xpl 只需将已计算好的
序列替换 ``build_demo_chart_data`` 的字段，并调用对应的绘图函数即可。
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1440
HEIGHT = 760
MARGIN = (110, 70, 70, 105)
NAVY = "#1F4E79"
BLUE = "#4472C4"
ORANGE = "#ED7D31"
RED = "#C00000"
GRID = "#D9E2F3"
TEXT = "#333333"
BACKGROUND = "#FFFFFF"


def build_demo_chart_data() -> dict[str, Any]:
    """返回独立于报告的假数据结构，供 xpl 后续替换为真实计算结果。"""
    # 固定随机种子，保证示例图每次生成一致，便于模板视觉回归检查。
    random_generator = random.Random(20260821)
    start_date = date(2020, 8, 21)
    dates = [start_date + timedelta(days=index * 7) for index in range(312)]

    index_nav, strategy_nav = [1.0], [1.0]
    for index in range(1, len(dates)):
        index_return = 0.0022 + 0.016 * math.sin(index / 13) + random_generator.uniform(-0.025, 0.025)
        strategy_return = 0.0041 + 0.014 * math.sin(index / 11 + 0.5) + random_generator.uniform(-0.023, 0.023)
        index_nav.append(max(index_nav[-1] * (1 + index_return), 0.3))
        strategy_nav.append(max(strategy_nav[-1] * (1 + strategy_return), 0.3))

    def drawdown(values: list[float]) -> list[float]:
        peak = values[0]
        result = []
        for value in values:
            peak = max(peak, value)
            result.append(value / peak - 1)
        return result

    index_drawdown = drawdown(index_nav)
    strategy_drawdown = drawdown(strategy_nav)
    excess_nav = [strategy / benchmark - 1 for benchmark, strategy in zip(index_nav, strategy_nav)]
    annual_returns = {
        "years": ["2020", "2021", "2022", "2023", "2024", "2025", "2026"],
        "index": [0.1603, 0.3174, -0.0323, 0.0468, 0.1085, 0.0457, 0.2768],
        "strategy": [0.1242, 0.6734, 0.0509, 0.2036, 0.1097, 0.2712, 0.4044],
    }
    # 两个收益率序列分别用于“日收益分布”的左右子图。
    index_daily_returns = [index_nav[index] / index_nav[index - 1] - 1 for index in range(1, len(index_nav))]
    strategy_daily_returns = [strategy_nav[index] / strategy_nav[index - 1] - 1 for index in range(1, len(strategy_nav))]
    monthly_excess = [0.0106 + 0.035 * math.sin(index / 3) + random_generator.uniform(-0.035, 0.035) for index in range(72)]

    return {
        "nav_curve": {"dates": dates, "index": index_nav, "strategy": strategy_nav},
        "drawdown_curve": {"dates": dates, "index": index_drawdown, "strategy": strategy_drawdown},
        "excess_curve": {"dates": dates, "excess": excess_nav},
        "annual_returns": annual_returns,
        "daily_return_distribution": {
            "index": index_daily_returns,
            "strategy": strategy_daily_returns,
        },
        "monthly_excess_distribution": monthly_excess,
    }


def generate_demo_charts(output_dir: str | Path) -> dict[str, str]:
    """生成六张假数据示例图，返回可直接写入 ``report_data['charts']`` 的路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = build_demo_chart_data()
    charts = {
        "累计净值曲线": output_dir / "累计净值曲线.png",
        "最大回撤曲线": output_dir / "最大回撤曲线.png",
        "超额收益曲线": output_dir / "超额收益曲线.png",
        "分年度收益": output_dir / "分年度收益.png",
        "日收益分布": output_dir / "日收益分布.png",
        "月度超额分布": output_dir / "月度超额分布.png",
    }
    _draw_line_chart(
        charts["累计净值曲线"], "累计净值曲线", data["nav_curve"]["dates"],
        [("指数", data["nav_curve"]["index"], BLUE), ("策略", data["nav_curve"]["strategy"], ORANGE)], "净值")
    _draw_line_chart(
        charts["最大回撤曲线"], "最大回撤曲线", data["drawdown_curve"]["dates"],
        [("指数", data["drawdown_curve"]["index"], BLUE), ("策略", data["drawdown_curve"]["strategy"], ORANGE)], "回撤")
    _draw_line_chart(
        charts["超额收益曲线"], "累计超额收益曲线", data["excess_curve"]["dates"],
        [("累计超额收益", data["excess_curve"]["excess"], RED)], "超额收益")
    _draw_grouped_bar_chart(charts["分年度收益"], "分年度收益", data["annual_returns"])
    # 日收益图使用双子图，方便在同一量纲下比较指数与策略的分布形态。
    _draw_dual_histogram(charts["日收益分布"], "日收益率分布", data["daily_return_distribution"])
    _draw_histogram(charts["月度超额分布"], "月度超额分布", data["monthly_excess_distribution"], "月度超额收益")
    return {title: str(path) for title, path in charts.items()}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_paths = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf" if bold else r"C:\Windows\Fonts\simsun.ttc",
    ]
    for font_path in font_paths:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def _canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN[0], 22), title, fill=NAVY, font=_font(32, bold=True))
    return image, draw


def _plot_area() -> tuple[int, int, int, int]:
    left, top, right, bottom = MARGIN
    return left, top + 40, WIDTH - right, HEIGHT - bottom


def _draw_line_chart(path: Path, title: str, dates: list[date], series: list[tuple[str, list[float], str]], y_label: str) -> None:
    image, draw = _canvas(title)
    left, top, right, bottom = _plot_area()
    values = [value for _, value_list, _ in series for value in value_list]
    minimum, maximum = min(values), max(values)
    padding = max((maximum - minimum) * 0.12, 0.01)
    minimum, maximum = minimum - padding, maximum + padding
    _draw_grid(draw, left, top, right, bottom, minimum, maximum, y_label, percent="回撤" in y_label or "超额" in y_label)

    for name, values, color in series:
        points = [
            (left + index * (right - left) / max(1, len(values) - 1), bottom - (value - minimum) / (maximum - minimum) * (bottom - top))
            for index, value in enumerate(values)
        ]
        draw.line(points, fill=color, width=4)
        _draw_legend_item(draw, 950 + series.index((name, values, color)) * 170, 37, name, color)

    for index in range(0, len(dates), max(1, len(dates) // 6)):
        x = left + index * (right - left) / max(1, len(dates) - 1)
        draw.text((x - 38, bottom + 14), dates[index].strftime("%Y-%m"), fill=TEXT, font=_font(16))
    draw.text((left - 72, top - 6), y_label, fill=TEXT, font=_font(18))
    image.save(path)


def _draw_grouped_bar_chart(path: Path, title: str, data: dict[str, list[Any]]) -> None:
    image, draw = _canvas(title)
    left, top, right, bottom = _plot_area()
    # 两个子图共用分箱边界和纵轴上限，避免视觉比较被各自缩放误导。
    values = data["index"] + data["strategy"]
    minimum, maximum = min(min(values), 0), max(values)
    padding = (maximum - minimum) * 0.12
    minimum, maximum = minimum - padding, maximum + padding
    _draw_grid(draw, left, top, right, bottom, minimum, maximum, "收益率", percent=True)
    zero_y = bottom - (0 - minimum) / (maximum - minimum) * (bottom - top)
    group_width = (right - left) / len(data["years"])
    bar_width = group_width * 0.28
    for index, year in enumerate(data["years"]):
        center = left + group_width * (index + 0.5)
        for offset, value, color in ((-bar_width * 0.6, data["index"][index], BLUE), (bar_width * 0.6, data["strategy"][index], ORANGE)):
            y = bottom - (value - minimum) / (maximum - minimum) * (bottom - top)
            draw.rectangle((center + offset - bar_width / 2, min(y, zero_y), center + offset + bar_width / 2, max(y, zero_y)), fill=color)
        draw.text((center - 24, bottom + 14), year, fill=TEXT, font=_font(16))
    _draw_legend_item(draw, 1010, 37, "指数", BLUE)
    _draw_legend_item(draw, 1150, 37, "策略", ORANGE)
    image.save(path)


def _draw_histogram(path: Path, title: str, values: list[float], x_label: str) -> None:
    image, draw = _canvas(title)
    left, top, right, bottom = _plot_area()
    bin_count = 16
    minimum, maximum = min(values), max(values)
    bin_width = (maximum - minimum) / bin_count
    counts = [0] * bin_count
    for value in values:
        index = min(int((value - minimum) / bin_width), bin_count - 1)
        counts[index] += 1
    max_count = max(counts)
    _draw_grid(draw, left, top, right, bottom, 0, max_count * 1.12, "频数", percent=False)
    bar_width = (right - left) / bin_count * 0.78
    for index, count in enumerate(counts):
        x = left + (right - left) * (index + 0.5) / bin_count
        y = bottom - count / (max_count * 1.12) * (bottom - top)
        draw.rectangle((x - bar_width / 2, y, x + bar_width / 2, bottom), fill=BLUE)
    for index in range(0, bin_count + 1, 4):
        value = minimum + min(index, bin_count) * bin_width
        x = left + (right - left) * min(index, bin_count) / bin_count
        draw.text((x - 35, bottom + 14), f"{value:.1%}", fill=TEXT, font=_font(16))
    draw.text((left - 72, top - 6), "频数", fill=TEXT, font=_font(18))
    draw.text((right - 92, bottom + 52), x_label, fill=TEXT, font=_font(18))
    image.save(path)


def _draw_dual_histogram(path: Path, title: str, data: dict[str, list[float]]) -> None:
    """并列绘制指数与策略的日收益率直方图。"""
    image, draw = _canvas(title)
    left, top, right, bottom = _plot_area()
    gap = 70
    midpoint = (left + right) / 2
    panels = [
        (left, int(midpoint - gap / 2), "指数日收益分布", data["index"], BLUE),
        (int(midpoint + gap / 2), right, "策略日收益分布", data["strategy"], ORANGE),
    ]
    values = data["index"] + data["strategy"]
    bin_count = 18
    minimum, maximum = min(values), max(values)
    bin_width = (maximum - minimum) / bin_count
    histogram_counts = []
    for _, _, _, series, _ in panels:
        counts = [0] * bin_count
        for value in series:
            index = min(int((value - minimum) / bin_width), bin_count - 1)
            counts[index] += 1
        histogram_counts.append(counts)
    max_count = max(max(counts) for counts in histogram_counts)

    for (panel_left, panel_right, panel_title, _, color), counts in zip(panels, histogram_counts):
        draw.text((panel_left, top - 42), panel_title, fill=TEXT, font=_font(20, bold=True))
        _draw_grid(draw, panel_left, top, panel_right, bottom, 0, max_count * 1.12, "频数", percent=False)
        bar_width = (panel_right - panel_left) / bin_count * 0.78
        for index, count in enumerate(counts):
            x = panel_left + (panel_right - panel_left) * (index + 0.5) / bin_count
            y = bottom - count / (max_count * 1.12) * (bottom - top)
            draw.rectangle((x - bar_width / 2, y, x + bar_width / 2, bottom), fill=color)
        for index in range(0, bin_count + 1, 6):
            value = minimum + min(index, bin_count) * bin_width
            x = panel_left + (panel_right - panel_left) * min(index, bin_count) / bin_count
            draw.text((x - 30, bottom + 14), f"{value:.1%}", fill=TEXT, font=_font(14))
        draw.text((panel_right - 88, bottom + 52), "日收益率", fill=TEXT, font=_font(16))

    image.save(path)


def _draw_grid(draw: ImageDraw.ImageDraw, left: int, top: int, right: int, bottom: int, minimum: float, maximum: float, y_label: str, percent: bool) -> None:
    draw.rectangle((left, top, right, bottom), outline="#9EADBD", width=2)
    for index in range(6):
        y = top + index * (bottom - top) / 5
        value = maximum - index * (maximum - minimum) / 5
        draw.line((left, y, right, y), fill=GRID, width=1)
        label = f"{value:.0%}" if percent else f"{value:.0f}"
        draw.text((left - 70, y - 10), label, fill=TEXT, font=_font(16))


def _draw_legend_item(draw: ImageDraw.ImageDraw, x: int, y: int, name: str, color: str) -> None:
    draw.line((x, y + 12, x + 28, y + 12), fill=color, width=4)
    draw.text((x + 36, y), name, fill=TEXT, font=_font(17))


def _main() -> None:
    parser = argparse.ArgumentParser(description="生成策略回测报告图表示例")
    parser.add_argument("--output-dir", default="downloads/策略回测报告图表")
    args = parser.parse_args()
    for title, path in generate_demo_charts(args.output_dir).items():
        print(f"{title}: {path}")


if __name__ == "__main__":
    _main()
