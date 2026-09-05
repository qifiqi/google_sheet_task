"""策略回测报告图表生成器。"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib

# 报告由后台线程生成，必须使用不依赖桌面会话的渲染后端。
matplotlib.use("Agg")

from matplotlib import dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import PercentFormatter
from numpy import linspace

from app.utils.value_parser import parse_float


# Word 模板按 6 英寸宽插图；240 DPI 对应约 1440 像素，打印和 PDF 缩放都足够清晰。
FIGURE_SIZE = (6, 3.17)
CHART_DPI = 240
NAVY = "#1F4E79"
BLUE = "#4472C4"
ORANGE = "#ED7D31"
RED = "#C00000"
GRID = "#E1E6EC"
TEXT = "#333333"
BACKGROUND = "#FFFFFF"
# 使用项目根目录定位字体，避免依赖部署机器的 Windows 字体目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = PROJECT_ROOT / "static" / "fonts"
FONT_REGULAR_PATH = FONTS_DIR / "NotoSansCJKsc-Regular.otf"
FONT_BOLD_PATH = FONTS_DIR / "NotoSansCJKsc-Bold.otf"


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
    # 先校验字体，尽早失败并避免生成一组字体不一致的半成品图片。
    _ensure_fonts_available()

    # 序列统一补齐到日期长度，保证每条曲线与横轴一一对应。
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
        [("指数", index_drawdown, BLUE), ("策略", strategy_drawdown, ORANGE)], "回撤", percent=True,
    )
    _draw_line_chart(
        charts["超额收益曲线"], "累计超额收益曲线", dates,
        [("累计超额收益", excess_nav, RED)], "超额收益", percent=True,
    )
    _draw_grouped_bar_chart(charts["分年度收益"], "分年度收益", chart_data.get("annual_returns") or {})
    _draw_dual_histogram(
        charts["日收益分布"], "日收益率分布",
        {
            "index": _finite_values(chart_data.get("index_daily_returns")),
            "strategy": _finite_values(chart_data.get("strategy_daily_returns")),
        },
    )
    _draw_histogram(
        charts["月度超额分布"], "月度超额分布",
        _finite_values(chart_data.get("monthly_excess_returns")), "月度超额收益",
    )
    return {title: str(path) for title, path in charts.items()}


def _numeric_series(values: Any, length: int, default: float) -> list[float]:
    """转换数值并补齐长度；非法值使用指定默认值。"""
    result = []
    for value in list(values or [])[:length]:
        number = parse_float(value, default=default)
        result.append(number if number is not None else default)
    return result + [default] * max(0, length - len(result))


def _finite_values(values: Any) -> list[float]:
    """过滤空值、非法值和非有限浮点数，空序列保留一个零值用于绘图。"""
    result = []
    for value in list(values or []):
        number = parse_float(value)
        if number is not None:
            result.append(number)
    return result or [0.0]


def _drawdown_series(values: list[float]) -> list[float]:
    """回撤以历史最高净值为基准，输出小于等于 0 的比例序列。"""
    peak = values[0] if values else 1.0
    result = []
    for value in values:
        peak = max(peak, value)
        result.append(value / peak - 1 if peak else 0.0)
    return result


@lru_cache(maxsize=4)
def _font(size: float, bold: bool = False) -> FontProperties:
    # FontProperties 可安全复用；缓存可减少六张图反复解析字体文件的开销。
    return FontProperties(fname=str(FONT_BOLD_PATH if bold else FONT_REGULAR_PATH), size=size)


def _ensure_fonts_available() -> None:
    missing_paths = [path for path in (FONT_REGULAR_PATH, FONT_BOLD_PATH) if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError(f"报告图表字体文件不存在: {', '.join(map(str, missing_paths))}")


def _new_figure() -> Figure:
    """创建独立 Figure，避免 pyplot 全局状态影响后台并发任务。"""
    figure = Figure(figsize=FIGURE_SIZE, dpi=CHART_DPI, facecolor=BACKGROUND)
    FigureCanvasAgg(figure)
    return figure


def _save_figure(figure: Figure, path: Path) -> None:
    """以 Word 兼容的 PNG 保存，并释放 Figure 占用的绘图对象。"""
    figure.savefig(path, format="png", dpi=CHART_DPI, facecolor=BACKGROUND)
    figure.clear()


def _style_axis(axis: Any) -> None:
    """统一报告图表的网格、边框、刻度和字体风格。"""
    axis.set_facecolor(BACKGROUND)
    axis.grid(axis="y", color=GRID, linewidth=0.7)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_color("#9EADBD")
    axis.tick_params(colors=TEXT, labelsize=8)
    for label in [*axis.get_xticklabels(), *axis.get_yticklabels()]:
        label.set_fontproperties(_font(8))


def _set_axis_labels(axis: Any, x_label: str = "", y_label: str = "") -> None:
    if x_label:
        axis.set_xlabel(x_label, color=TEXT, fontproperties=_font(9))
    if y_label:
        axis.set_ylabel(y_label, color=TEXT, fontproperties=_font(9))


def _set_percent_axis(axis: Any, axis_name: str) -> None:
    # 回测收益数据以 0.01 表示 1%，PercentFormatter 将其显示为百分号刻度。
    formatter = PercentFormatter(xmax=1, decimals=0)
    (axis.xaxis if axis_name == "x" else axis.yaxis).set_major_formatter(formatter)


def _draw_line_chart(
    path: Path,
    title: str,
    dates: list[date],
    series: list[tuple[str, list[float], str]],
    y_label: str,
    *,
    percent: bool = False,
) -> None:
    figure = _new_figure()
    axis = figure.subplots()
    for name, values, color in series:
        axis.plot(dates, values, label=name, color=color, linewidth=1.8)
    _set_axis_labels(axis, y_label=y_label)
    axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    # 短周期显示日，长周期显示月份，避免短周期所有标签都重复为同一个月份。
    date_format = "%Y-%m" if (max(dates) - min(dates)).days > 90 else "%m-%d"
    axis.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    axis.margins(x=0.01, y=0.12)
    if percent:
        _set_percent_axis(axis, "y")
    _style_axis(axis)
    # 图表标题由 Word 模板的 Heading 2 提供，PNG 内不重复绘制标题。
    axis.legend(frameon=False, loc="upper left", ncol=len(series), prop=_font(8))
    figure.subplots_adjust(left=0.12, right=0.98, bottom=0.18, top=0.96)
    figure.autofmt_xdate(rotation=0, ha="center")
    _save_figure(figure, path)


def _draw_grouped_bar_chart(path: Path, title: str, data: dict[str, list[Any]]) -> None:
    years = [str(value) for value in data.get("years") or []]
    if not years:
        _draw_empty_chart(path, title)
        return

    index_returns = _numeric_series(data.get("index"), len(years), 0.0)
    strategy_returns = _numeric_series(data.get("strategy"), len(years), 0.0)
    figure = _new_figure()
    axis = figure.subplots()
    positions = list(range(len(years)))
    bar_width = 0.36
    # 两组柱以同一年度为中心对称排列，便于直接比较指数与策略。
    axis.bar([position - bar_width / 2 for position in positions], index_returns, bar_width, label="指数", color=BLUE)
    axis.bar([position + bar_width / 2 for position in positions], strategy_returns, bar_width, label="策略", color=ORANGE)
    axis.axhline(0, color="#9EADBD", linewidth=0.8)
    axis.set_xticks(positions, years, fontproperties=_font(8))
    _set_axis_labels(axis, y_label="收益率")
    _set_percent_axis(axis, "y")
    _style_axis(axis)
    axis.legend(frameon=False, loc="upper left", ncol=2, prop=_font(8))
    figure.subplots_adjust(left=0.12, right=0.98, bottom=0.18, top=0.96)
    _save_figure(figure, path)


def _histogram_limits(values: list[float]) -> tuple[float, float]:
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        # 常数序列需要人为扩展范围，否则 Matplotlib 无法生成可见的柱形。
        padding = max(abs(minimum) * 0.12, 0.01)
        return minimum - padding, maximum + padding
    return minimum, maximum


def _symmetric_histogram_limit(values: list[float]) -> float:
    """返回覆盖全部数据且以 0 为中心的直方图半轴范围。

    日收益率同时包含正负值时，左右面板必须使用相同的对称范围，
    否则 X 轴偏移会放大或压缩其中一侧的波动。最小半轴保留 1%，
    让全零或近似全零数据仍有可读的绘图区域。
    """
    minimum, maximum = _histogram_limits(values)
    return max(abs(minimum), abs(maximum), 0.01) * 1.05


def _draw_histogram(path: Path, title: str, values: list[float], x_label: str) -> None:
    figure = _new_figure()
    axis = figure.subplots()
    minimum, maximum = _histogram_limits(values)
    axis.hist(values, bins=16, range=(minimum, maximum), color=BLUE, edgecolor=BACKGROUND, linewidth=0.8)
    _set_axis_labels(axis, x_label=x_label, y_label="频数")
    _set_percent_axis(axis, "x")
    _style_axis(axis)
    figure.subplots_adjust(left=0.12, right=0.98, bottom=0.2, top=0.96)
    _save_figure(figure, path)


def _draw_dual_histogram(path: Path, title: str, data: dict[str, list[float]]) -> None:
    values = data["index"] + data["strategy"]
    # 两个子图共用、以 0 为中心的 X 轴和分箱边界，避免正负收益比较产生视觉偏差。
    symmetric_limit = _symmetric_histogram_limit(values)
    bin_edges = linspace(-symmetric_limit, symmetric_limit, 19)
    figure = _new_figure()
    left_axis, right_axis = figure.subplots(1, 2, sharey=True)
    for axis, panel_title, series, color in (
        (left_axis, "指数日收益分布", data["index"], BLUE),
        (right_axis, "策略日收益分布", data["strategy"], ORANGE),
    ):
        axis.hist(series, bins=bin_edges, color=color, edgecolor=BACKGROUND, linewidth=0.8)
        axis.set_xlim(-symmetric_limit, symmetric_limit)
        # 0% 是收益率分布的关键参照点，使用浅色细线避免喧宾夺主。
        axis.axvline(0, color="#9EADBD", linewidth=0.8)
        # 双子图需要保留各自的小标题，否则 Word 中只有“日收益分布”无法区分左右面板。
        axis.set_title(panel_title, color=TEXT, fontproperties=_font(9, bold=True), loc="left", pad=6)
        _set_axis_labels(axis, x_label="日收益率")
        _set_percent_axis(axis, "x")
        _style_axis(axis)
    _set_axis_labels(left_axis, y_label="频数")
    # 左右子图标题由 Word 中的统一图表标题承担，避免同一标题出现三次。
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    _save_figure(figure, path)


def _draw_empty_chart(path: Path, title: str) -> None:
    """没有年度数据时仍输出占位图，保证报告图表数量和顺序稳定。"""
    figure = _new_figure()
    axis = figure.subplots()
    axis.axis("off")
    axis.text(0.5, 0.5, "暂无可用数据", color=TEXT, fontproperties=_font(13), ha="center", va="center")
    _save_figure(figure, path)
