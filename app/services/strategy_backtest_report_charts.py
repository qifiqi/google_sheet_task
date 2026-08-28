"""策略回测报告图表生成器。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.utils.value_parser import parse_float


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


def generate_report_charts(chart_data: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """根据真实回测数据生成报告图表，返回图表标题到 PNG 路径的映射。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dates = chart_data.get("dates") or []
    if not dates:
        raise ValueError("报告图表至少需要一条日期数据")

    charts = {
        "累计净值曲线": output_dir / "累计净值曲线.png",
        "最大回撤曲线": output_dir / "最大回撤曲线.png",
        "超额收益曲线": output_dir / "超额收益曲线.png",
        "分年度收益": output_dir / "分年度收益.png",
        "日收益分布": output_dir / "日收益分布.png",
        "月度超额分布": output_dir / "月度超额分布.png",
    }
    # 所有序列统一补齐到日期长度，保证绘图坐标不会错位。
    index_nav = _numeric_series(chart_data.get("index_nav"), len(dates), 1.0)
    strategy_nav = _numeric_series(chart_data.get("strategy_nav"), len(dates), 1.0)
    index_drawdown = _drawdown_series(index_nav)
    strategy_drawdown = _drawdown_series(strategy_nav)
    excess_nav = _numeric_series(chart_data.get("excess_nav"), len(dates), 0.0)
    _draw_line_chart(
        charts["累计净值曲线"], "累计净值曲线", dates,
        [("指数", index_nav, BLUE), ("策略", strategy_nav, ORANGE)], "净值",
    )
    _draw_line_chart(
        charts["最大回撤曲线"], "最大回撤曲线", dates,
        [("指数", index_drawdown, BLUE), ("策略", strategy_drawdown, ORANGE)], "回撤",
    )
    _draw_line_chart(
        charts["超额收益曲线"], "累计超额收益曲线", dates,
        [("累计超额收益", excess_nav, RED)], "超额收益",
    )
    annual_returns = chart_data.get("annual_returns") or {"years": [], "index": [], "strategy": []}
    _draw_grouped_bar_chart(charts["分年度收益"], "分年度收益", annual_returns)
    _draw_dual_histogram(
        charts["日收益分布"], "日收益率分布",
        {"index": _finite_values(chart_data.get("index_daily_returns")),
         "strategy": _finite_values(chart_data.get("strategy_daily_returns"))},
    )
    _draw_histogram(
        charts["月度超额分布"], "月度超额分布",
        _finite_values(chart_data.get("monthly_excess_returns")), "月度超额收益",
    )
    return {title: str(path) for title, path in charts.items()}


def _numeric_series(values: Any, length: int, default: float) -> list[float]:
    """处理_numeric_series相关逻辑。"""
    result = []
    for value in list(values or [])[:length]:
        number = parse_float(value, default=default)
        result.append(number if number is not None else default)
    return result + [default] * max(0, length - len(result))


def _finite_values(values: Any) -> list[float]:
    """处理_finite_values相关逻辑。"""
    result = []
    for value in list(values or []):
        number = parse_float(value)
        if number is not None:
            result.append(number)
    return result or [0.0]


def _drawdown_series(values: list[float]) -> list[float]:
    # 回撤以历史最高净值为基准，输出小于等于 0 的比例序列。
    """处理_drawdown_series相关逻辑。"""
    peak = values[0] if values else 1.0
    result = []
    for value in values:
        peak = max(peak, value)
        result.append(value / peak - 1 if peak else 0.0)
    return result


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """处理_font相关逻辑。"""
    font_paths = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf" if bold else r"C:\Windows\Fonts\simsun.ttc",
    ]
    for font_path in font_paths:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def _canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """处理_canvas相关逻辑。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN[0], 22), title, fill=NAVY, font=_font(32, bold=True))
    return image, draw


def _plot_area() -> tuple[int, int, int, int]:
    """处理_plot_area相关逻辑。"""
    left, top, right, bottom = MARGIN
    return left, top + 40, WIDTH - right, HEIGHT - bottom


def _draw_line_chart(path: Path, title: str, dates: list[date], series: list[tuple[str, list[float], str]], y_label: str) -> None:
    """处理_draw_line_chart相关逻辑。"""
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
    """处理_draw_grouped_bar_chart相关逻辑。"""
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
    """处理_draw_histogram相关逻辑。"""
    image, draw = _canvas(title)
    left, top, right, bottom = _plot_area()
    bin_count = 16
    minimum, maximum = min(values), max(values)
    bin_width = (maximum - minimum) / bin_count or 1.0
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
    bin_width = (maximum - minimum) / bin_count or 1.0
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
    """绘制图表网格和纵轴标签。"""
    draw.rectangle((left, top, right, bottom), outline="#9EADBD", width=2)
    for index in range(6):
        y = top + index * (bottom - top) / 5
        value = maximum - index * (maximum - minimum) / 5
        draw.line((left, y, right, y), fill=GRID, width=1)
        label = f"{value:.0%}" if percent else f"{value:.0f}"
        draw.text((left - 70, y - 10), label, fill=TEXT, font=_font(16))


def _draw_legend_item(draw: ImageDraw.ImageDraw, x: int, y: int, name: str, color: str) -> None:
    """处理_draw_legend_item相关逻辑。"""
    draw.line((x, y + 12, x + 28, y + 12), fill=color, width=4)
    draw.text((x + 36, y), name, fill=TEXT, font=_font(17))
