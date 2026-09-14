"""策略回测报告图表生成器。"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from math import ceil, floor, log10
from pathlib import Path
from typing import Any

import matplotlib

# 报告由后台线程生成，必须使用不依赖桌面会话的渲染后端。
matplotlib.use("Agg")

from matplotlib import dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, MultipleLocator
from numpy import isnan, linspace, ma

from app.utils.value_parser import parse_float


# Word 模板按 6 英寸宽插图；240 DPI 对应约 1440 像素，打印和 PDF 缩放都足够清晰。
FIGURE_SIZE = (6, 3.17)
CHART_DPI = 240
NAVY = "#1F4E79"
BLUE = "#4472C4"
ORANGE = "#ED7D31"
RED = "#C00000"
GREEN = "#4AA564"
LIGHT_RED = "#EF6E6E"
GRID = "#E1E6EC"
TEXT = "#333333"
BACKGROUND = "#FFFFFF"
# 多基准折线依次取调色板取色；策略恒定橙色锚定，单基准落在蓝色与历史一致。
BENCHMARK_PALETTE = [BLUE, "#7030A0", GREEN, "#B45309", RED]


def _benchmark_color(index: int) -> str:
    return BENCHMARK_PALETTE[index % len(BENCHMARK_PALETTE)]


def benchmark_label(benchmark: dict[str, Any], index: int) -> str:
    """基准图例文案；服务端已按单基准"指数"/多基准"指数(代码)"填好 label。"""
    return str(benchmark.get("label") or f"指数{index + 1}")
# 相关系数热力图配色：0 附近为标准蓝，向 +1/-1 两端渐变为白（相关性越强越浅）。
CORRELATION_CMAP = LinearSegmentedColormap.from_list(
    "correlation_blue_white",
    [(0.0, "#FFFFFF"), (0.5, BLUE), (1.0, "#FFFFFF")],
).with_extremes(bad="#F0F0F0")
# 折线主线条宽（pt）：CHART_DPI=240 下 1pt ≈ 3.3 物理像素，视觉粗细按此换算。
LINE_WIDTH = 0.8
# 回撤面积图的描边线宽（pt），细于主折线以突出填充主体。
AREA_EDGE_WIDTH = LINE_WIDTH
# 使用项目根目录定位字体，避免依赖部署机器的 Windows 字体目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = PROJECT_ROOT / "static" / "fonts"
FONT_REGULAR_PATH = FONTS_DIR / "NotoSansCJKsc-Regular.otf"
FONT_BOLD_PATH = FONTS_DIR / "NotoSansCJKsc-Bold.otf"


def generate_report_charts(chart_data: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """根据真实回测数据生成报告图表，返回图表标题到 PNG 路径的映射。

    序列形状由服务端 _build_chart_data 组装，本模块只渲染：benchmarks 为
    基准序列列表（label/nav/drawdown/daily_returns），策略、超额、月度超额
    单独给出；月度超额按基准逐条提供（含图表标题）。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dates = chart_data.get("dates") or []
    if not dates:
        raise ValueError("报告图表至少需要一条日期数据")
    # 先校验字体，尽早失败并避免生成一组字体不一致的半成品图片。
    _ensure_fonts_available()

    # 序列统一补齐到日期长度，保证每条曲线与横轴一一对应；
    # 全部序列（含回撤）由服务端 _build_chart_data 预先算好，这里只负责渲染。
    benchmarks = chart_data.get("benchmarks") or []
    strategy_nav = _numeric_series(chart_data.get("strategy_nav"), len(dates), 1.0)
    strategy_drawdown = _numeric_series(chart_data.get("strategy_drawdown"), len(dates), 0.0)
    nav_series = [
        (benchmark_label(benchmark, index),
         _numeric_series(benchmark.get("nav"), len(dates), 1.0), _benchmark_color(index))
        for index, benchmark in enumerate(benchmarks)
    ]
    drawdown_series = [
        (f"{benchmark_label(benchmark, index)}回撤",
         _numeric_series(benchmark.get("drawdown"), len(dates), 0.0), _benchmark_color(index))
        for index, benchmark in enumerate(benchmarks)
    ]
    excess_series = chart_data.get("excess_series") or []
    excess_line_series = [
        (str(entry.get("label") or "累计超额收益"),
         _numeric_series(entry.get("values"), len(dates), 0.0),
         RED if len(excess_series) <= 1 else _benchmark_color(index))
        for index, entry in enumerate(excess_series)
    ]

    charts = {
        "累计净值曲线": output_dir / "累计净值曲线.png",
        "最大回撤曲线": output_dir / "最大回撤曲线.png",
        "超额收益曲线": output_dir / "超额收益曲线.png",
        "分年度收益": output_dir / "分年度收益.png",
        "日收益分布": output_dir / "日收益分布.png",
    }
    _draw_line_chart(
        charts["累计净值曲线"], "累计净值曲线", dates,
        [*nav_series, ("策略", strategy_nav, ORANGE)], "净值",
    )
    # 最大回撤曲线按面积图渲染；与折线变体保持相同签名，便于一键切换。
    _draw_drawdown_area_chart(
        charts["最大回撤曲线"], "最大回撤曲线", dates,
        [*drawdown_series, ("策略回撤", strategy_drawdown, ORANGE)], "回撤（%）", percent=True,
    )
    # _draw_excess_line_bar_chart(
    #     charts["超额收益曲线"], "累计超额收益曲线", dates,
    #     _numeric_series(chart_data.get("excess_daily_return"), len(dates), 0.0),
    # )
    _draw_line_chart(
        charts["超额收益曲线"], "累计超额收益曲线", dates,
        excess_line_series, "超额收益（%）", percent=True,
    )
    _draw_grouped_bar_chart(charts["分年度收益"], "分年度收益", chart_data.get("annual_returns") or {})
    _draw_daily_distribution(
        charts["日收益分布"], "日收益率分布",
        chart_data.get("daily_distribution") or {},
    )
    for index, entry in enumerate(chart_data.get("monthly_excess_by_benchmark") or []):
        title = str(entry.get("title") or "月度超额分布")
        # 多基准时每基准一张图；文件名加序号避免相互覆盖。
        charts[title] = output_dir / f"月度超额分布{index + 1 if index else ''}.png"
        _draw_monthly_excess_bars(charts[title], title, _finite_values(entry.get("values")))
    return {title: str(path) for title, path in charts.items()}


def generate_correlation_heatmap(
    labels: list[str],
    matrix: list[list[Any]],
    output_path: str | Path,
) -> None:
    """权重日涨跌幅相关系数热力图：N×N 方阵，单元格内直接标注相关系数。

    标的增多时矩阵表格会超出版面宽度，热力图边长可随标的数自适应；
    相关系数缺失（数据不可对齐/零方差）的格子以灰色底与 "-" 展示。
    """
    _ensure_fonts_available()
    count = len(labels)
    # 边长随标的数自适应并限制在 4~9 英寸，Word 按 6 英寸宽缩放后仍可读。
    size = min(9.0, max(4.0, 0.62 * count + 1.8))
    figure = Figure(figsize=(size, size * 0.94), dpi=CHART_DPI, facecolor=BACKGROUND)
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    values = [[float("nan") if cell is None else float(cell) for cell in row] for row in matrix]
    image = axis.imshow(ma.masked_invalid(values), cmap=CORRELATION_CMAP, vmin=-1.0, vmax=1.0)
    axis.set_xticks(range(count), labels, rotation=45, ha="right", fontproperties=_font(8))
    axis.set_yticks(range(count), labels, fontproperties=_font(8))
    axis.tick_params(colors=TEXT, length=0)
    cell_font_size = 8 if count <= 8 else 7
    for row_index, row in enumerate(values):
        for column_index, value in enumerate(row):
            if isnan(value):
                text, color = "-", "#8C8C8C"
            else:
                # 蓝色区域用白字，接近白色的强相关区域用正文灰。
                text = f"{value:.2f}"
                color = "#FFFFFF" if abs(value) <= 0.5 else TEXT
            axis.text(
                column_index, row_index, text, ha="center", va="center",
                color=color, fontproperties=_font(cell_font_size),
            )
    colorbar = figure.colorbar(image, ax=axis, shrink=0.85, pad=0.02)
    colorbar.ax.tick_params(colors=TEXT, labelsize=8)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(_font(8))
    colorbar.outline.set_edgecolor("#9EADBD")
    figure.tight_layout()
    _save_figure(figure, Path(output_path))


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
    # 回测收益数据以 0.01 表示 1%；刻度只显示数值，百分号单位由轴标题（%）说明。
    formatter = FuncFormatter(lambda value, _position: f"{value * 100:g}")
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
        axis.plot(dates, values, label=name, color=color, linewidth=LINE_WIDTH)
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


def _draw_drawdown_area_chart(
    path: Path,
    title: str,
    dates: list[date],
    series: list[tuple[str, list[float], str]],
    y_label: str,
    *,
    percent: bool = False,
) -> None:
    """最大回撤的面积图变体：各序列填充到 0 轴并保留细描边。

    与 _draw_line_chart 保持相同签名和坐标轴风格，仅绘制方式不同，
    便于在 generate_report_charts 入口通过 DRAWDOWN_CHART_STYLE 一键切换。
    图例只保留填充色的一个条目，描边线不再重复注册 label。
    """
    figure = _new_figure()
    axis = figure.subplots()
    for name, values, color in series:
        axis.fill_between(dates, values, 0, label=name, color=color, alpha=0.4, linewidth=0)
        axis.plot(dates, values, color=color, linewidth=AREA_EDGE_WIDTH)
    _set_axis_labels(axis, y_label=y_label)
    axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    # 与折线图一致：短周期显示日，长周期显示月份。
    date_format = "%Y-%m" if (max(dates) - min(dates)).days > 90 else "%m-%d"
    axis.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    axis.margins(x=0.01, y=0.12)
    if percent:
        _set_percent_axis(axis, "y")
    _style_axis(axis)
    axis.legend(frameon=False, loc="upper left", ncol=len(series), prop=_font(8))
    figure.subplots_adjust(left=0.12, right=0.98, bottom=0.18, top=0.96)
    figure.autofmt_xdate(rotation=0, ha="center")
    _save_figure(figure, path)


def _draw_excess_line_bar_chart(
    path: Path,
    title: str,
    dates: list[date],
    excess_nav: list[float],
    excess_daily: list[float],
) -> None:
    """超额收益的线柱组合图：累计超额折线（左轴）+ 日超额收益柱状（右轴）。

    日超额量级远小于累计超额，双轴分别按百分数刻度展示；柱按正负
    染色，沿用月度超额分布的绿/红约定。twinx 默认后建轴在上，手动
    抬高主轴避免柱面遮挡折线。
    """
    figure = _new_figure()
    line_axis = figure.subplots()
    bar_axis = line_axis.twinx()
    bar_colors = [GREEN if value >= 0 else LIGHT_RED for value in excess_daily]
    bar_axis.bar(dates, excess_daily, color=bar_colors, width=1.0, alpha=0.7)
    # 0 轴是正负超额的分界参照线，与月度超额分布保持同一风格。
    bar_axis.axhline(0, color="#9EADBD", linewidth=0.9)
    line_axis.plot(dates, excess_nav, color=RED, linewidth=LINE_WIDTH)
    _set_axis_labels(line_axis, y_label="累计超额收益（%）")
    _set_axis_labels(bar_axis, y_label="日超额收益（%）")
    line_axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    # 与折线图一致：短周期显示日，长周期显示月份。
    date_format = "%Y-%m" if (max(dates) - min(dates)).days > 90 else "%m-%d"
    line_axis.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    line_axis.margins(x=0.01, y=0.12)
    bar_axis.margins(x=0.01, y=0.12)
    _set_percent_axis(line_axis, "y")
    _set_percent_axis(bar_axis, "y")
    _style_axis(line_axis)
    # 双轴只保留主轴的 y 网格，右轴仅同步刻度字体与边框颜色。
    bar_axis.grid(False)
    bar_axis.tick_params(colors=TEXT, labelsize=8)
    for label in bar_axis.get_yticklabels():
        label.set_fontproperties(_font(8))
    for spine in bar_axis.spines.values():
        spine.set_color("#9EADBD")
    line_axis.set_zorder(bar_axis.get_zorder() + 1)
    line_axis.patch.set_visible(False)
    line_axis.legend(
        handles=[
            Patch(facecolor=GREEN, label="日超额收益(正)"),
            Patch(facecolor=LIGHT_RED, label="日超额收益(负)"),
            Line2D([0], [0], color=RED, linewidth=LINE_WIDTH, label="累计超额收益"),
        ],
        frameon=False, loc="upper left", ncol=3, prop=_font(8),
    )
    # 右侧留出副轴标题与刻度的空间。
    figure.subplots_adjust(left=0.12, right=0.87, bottom=0.18, top=0.96)
    figure.autofmt_xdate(rotation=0, ha="center")
    _save_figure(figure, path)


def _draw_grouped_bar_chart(path: Path, title: str, data: dict[str, Any]) -> None:
    """分年度收益分组柱状图：每组柱 = 各基准（调色板）+ 策略（橙）。"""
    years = [str(value) for value in data.get("years") or []]
    if not years:
        _draw_empty_chart(path, title)
        return

    benchmarks = data.get("benchmarks") or []
    entries = [
        (benchmark_label(benchmark, index),
         _numeric_series(benchmark.get("values"), len(years), 0.0), _benchmark_color(index))
        for index, benchmark in enumerate(benchmarks)
    ]
    entries.append(("策略", _numeric_series(data.get("strategy"), len(years), 0.0), ORANGE))
    count = len(entries)
    bar_width = 0.8 / count
    figure = _new_figure()
    axis = figure.subplots()
    positions = list(range(len(years)))
    # 各组柱以同一年度为中心对称排列，便于同年度直接横向比较。
    for offset, (label, values, color) in enumerate(entries):
        shift = (offset - (count - 1) / 2) * bar_width
        axis.bar([position + shift for position in positions], values, bar_width, label=label, color=color)
    axis.axhline(0, color="#9EADBD", linewidth=0.8)
    axis.set_xticks(positions, years, fontproperties=_font(8))
    _set_axis_labels(axis, y_label="收益率（%）")
    _set_percent_axis(axis, "y")
    _style_axis(axis)
    axis.legend(frameon=False, loc="upper left", ncol=count, prop=_font(8))
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
    """返回核心区间、以 0 为中心的直方图半轴范围。

    以 0.5%/99.5% 分位数（而非极值）为基准：极少数极端收益若直接
    决定坐标轴，会把主体分布压扁并留下大片无数据的空白。轴范围随
    数据集中区走，超出的极端样本折叠进两端边缘箱，尾部频数统计不
    丢失（其数值仍体现在报告的最大单日收益等表格指标中）。最小半
    轴保留 1%，让全零或近似全零数据仍有可读的绘图区域。
    """
    ordered = sorted(values)
    count = len(ordered)
    low = ordered[int((count - 1) * 0.005)]
    high = ordered[min(count - 1, ceil((count - 1) * 0.995))]
    return max(abs(low), abs(high), 0.01) * 1.05


def _histogram_bin_count(values: list[float], symmetric_limit: float) -> int:
    """按样本量与范围自适应分箱数，箱宽对齐 1-2-2.5-5 百分网格。

    固定 18 箱会把主体收益挤进三四根柱子里，分布形态与尾部都看不
    清。箱宽取 Freedman–Diaconis 估计（2×四分位距×n^(-1/3)，随样本
    量自适应）与 span/60 的较大者——后者兜底重尾数据，避免箱数爆炸
    ——再向上取整到规整的百分数网格，箱数被自然限制在 12~60 之间。
    """
    ordered = sorted(values)
    count = len(ordered)
    span = symmetric_limit * 2
    if count > 1:
        iqr = ordered[int((count - 1) * 0.75)] - ordered[int((count - 1) * 0.25)]
        width = max(2 * iqr / count ** (1 / 3), span / 60)
    else:
        width = span / 60
    magnitude = 10.0 ** floor(log10(width))
    for mantissa in (1, 2, 2.5, 5, 10):
        nice_width = mantissa * magnitude
        if nice_width >= width:
            break
    return max(12, ceil(span / nice_width))


def _percent_tick_step(span: float, max_intervals: int = 4) -> float:
    """按刻度跨度从 1-2-2.5-5 序列自适应选取步长，span 内不超过 max_intervals 个刻度区间。

    常规日收益半轴（±7% 附近）落到约 2% 一个刻度；月度超额 y 轴把
    预算放宽到 8，约 20% 的跨度落到模板样式的 2.5% 一个刻度。范围
    放大或缩小时步长随之增减，避免刻度过密或全部消失；步长限定
    1-2-2.5-5 序列，保证刻度值规整且正负两侧能按同一步长成对对齐。
    """
    magnitude = 10.0 ** floor(log10(span / max_intervals))
    for mantissa in (1, 2, 2.5, 5, 10):
        step = mantissa * magnitude
        if floor(span / step) <= max_intervals:
            return step
    return 10.0 * magnitude


def _percent_tick_formatter(step: float, overflow_limit: float | None = None) -> FuncFormatter:
    """刻度只显示数值不显示百分号，单位由轴标题（%）说明。

    overflow_limit 非空时，两端阈值刻度显示为 <-X、>+X，标明尾部
    极端收益已归并进边缘箱。小数位取能精确表示步长百分数的最少位数
    （如 2.5% 保留 1 位），避免刻度全部取整为 0 或出现拖尾小数。
    """
    step_percent = step * 100
    decimals = 0
    while decimals < 6 and abs(round(step_percent, decimals) - step_percent) > 1e-9:
        decimals += 1

    def format_tick(value: float, _position: Any) -> str:
        if overflow_limit is not None:
            if value == overflow_limit:
                return f">+{overflow_limit * 100:.1f}"
            if value == -overflow_limit:
                return f"<-{overflow_limit * 100:.1f}"
        return f"{value * 100:.{decimals}f}"

    return FuncFormatter(format_tick)


def _apply_symmetric_percent_ticks(axis: Any, symmetric_limit: float, mark_overflow: bool = False) -> None:
    """X 轴使用关于 0 对称的数值刻度（单位 % 由轴标题说明），正负两侧刻度完全对齐。

    mark_overflow 时在两端阈值位置追加 <-X、>+X 边缘刻度，标明
    极端收益已归并进边缘箱；阈值与最外侧刻度过近时后者让位，避免
    标签互相重叠。
    """
    step = _percent_tick_step(symmetric_limit)
    intervals = floor(symmetric_limit / step)
    ticks = [multiplier * step for multiplier in range(-intervals, intervals + 1)]
    if mark_overflow:
        if len(ticks) > 1 and symmetric_limit - intervals * step < step / 2:
            ticks = ticks[1:-1]
        ticks = [-symmetric_limit] + ticks + [symmetric_limit]
    axis.xaxis.set_major_locator(FixedLocator(ticks))
    axis.xaxis.set_major_formatter(
        _percent_tick_formatter(step, overflow_limit=symmetric_limit if mark_overflow else None)
    )
    if mark_overflow:
        # 阈值刻度位于轴端，标签向面板内侧对齐，避免越出图面。
        labels = axis.get_xticklabels()
        labels[0].set_ha("left")
        labels[-1].set_ha("right")


def _draw_monthly_excess_bars(path: Path, title: str, monthly_excess: list[float]) -> None:
    """按模板把月度超额画成逐月柱状序列：正超额绿色、负超额红色。"""
    figure = _new_figure()
    axis = figure.subplots()
    colors = [GREEN if value >= 0 else LIGHT_RED for value in monthly_excess]
    axis.bar(range(len(monthly_excess)), monthly_excess, color=colors, width=0.8)
    # 0 轴是正负超额的分界参照线，与分年度收益图保持同一风格。
    axis.axhline(0, color="#9EADBD", linewidth=0.9)
    _set_axis_labels(axis, x_label="月份序号", y_label="月度超额收益（%）")
    lowest, highest = min(monthly_excess), max(monthly_excess)
    # 常数序列（如缺数据兜底的 [0.0]）需要人为保留可读的 y 轴范围。
    span = (highest - lowest) or max(abs(highest) * 0.2, 0.02)
    # y 轴预算放宽到 8 个刻度区间：约 20% 的跨度自适应出模板样式的 2.5% 间隔。
    step = _percent_tick_step(span, max_intervals=8)
    axis.yaxis.set_major_locator(MultipleLocator(step))
    axis.yaxis.set_major_formatter(_percent_tick_formatter(step))
    # 月份序号恒为整数，刻度密度交给 MaxNLocator 按序列长度自适应。
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_axis(axis)
    # Word 标题只有“月度超额分布”，颜色含义需要图内图例说明。
    axis.legend(
        handles=[Patch(facecolor=GREEN, label="正超额"), Patch(facecolor=LIGHT_RED, label="负超额")],
        frameon=False, loc="upper left", ncol=2, prop=_font(8),
    )
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    _save_figure(figure, path)


def _draw_daily_distribution(path: Path, title: str, data: dict[str, Any]) -> None:
    """日收益分布：面板 = 各基准 + 策略，共享以 0 为中心的核心区间与分箱。

    核心区间按分位数确定，超出区间的极端收益归并进两端边缘箱（overflow
    bins），既提升主体分辨率又不丢失尾部统计。面板数 ≤3 单行排布，更多
    时折叠为两行网格；配色沿用基准=调色板、策略=橙的约定。
    """
    benchmarks = data.get("benchmarks") or []
    panels = [
        (benchmark_label(benchmark, index), _finite_values(benchmark.get("values")), _benchmark_color(index))
        for index, benchmark in enumerate(benchmarks)
    ]
    panels.append(("策略", _finite_values(data.get("strategy")), ORANGE))
    values = [value for _, series, _ in panels for value in series]
    # 全部面板共用、以 0 为中心的核心区间和分箱边界，便于左右对比。
    symmetric_limit = _symmetric_histogram_limit(values)
    bin_count = _histogram_bin_count(values, symmetric_limit)
    bin_edges = linspace(-symmetric_limit, symmetric_limit, bin_count + 1)
    overflow_count = sum(1 for value in values if not -symmetric_limit <= value <= symmetric_limit)
    figure = _new_figure()
    if len(panels) <= 3:
        axes = list(figure.subplots(1, len(panels), sharey=True, squeeze=False)[0])
    else:
        axes = list(figure.subplots(2, ceil(len(panels) / 2), sharey=True, squeeze=False).ravel())
        for spare_axis in axes[len(panels):]:
            spare_axis.axis("off")
    for axis, (panel_label, series, color) in zip(axes, panels):
        clipped = [min(max(value, -symmetric_limit), symmetric_limit) for value in series]
        # 顶部多留 12% 余量，避免归并标注与最高柱重叠。
        axis.margins(y=0.12)
        axis.hist(clipped, bins=bin_edges, color=color, edgecolor=BACKGROUND, linewidth=0.8)
        axis.set_xlim(-symmetric_limit, symmetric_limit)
        # 0% 是收益率分布的关键参照点，使用浅色细线避免喧宾夺主。
        axis.axvline(0, color="#9EADBD", linewidth=0.8)
        # 面板小标题自明：指数 / 指数(代码) / 策略 日收益分布。
        axis.set_title(f"{panel_label}日收益分布", color=TEXT, fontproperties=_font(9), pad=8)
        _set_axis_labels(axis, x_label="日收益率（%）")
        _apply_symmetric_percent_ticks(axis, symmetric_limit, mark_overflow=overflow_count > 0)
        _style_axis(axis)
    if overflow_count:
        # 归并需在图内说明，否则读者会把边缘柱当成普通分箱。
        # axes[-1].text(
        #     0.98, 0.96, f"{overflow_count} 笔超出 ±{symmetric_limit * 100:.1f}% 已并入两端",
        #     transform=axes[-1].transAxes, color="#8C8C8C", fontproperties=_font(7),
        #     ha="right", va="top",
        # )
        pass
    _set_axis_labels(axes[0], y_label="频数")
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    _save_figure(figure, path)


def _draw_empty_chart(path: Path, title: str) -> None:
    """没有年度数据时仍输出占位图，保证报告图表数量和顺序稳定。"""
    figure = _new_figure()
    axis = figure.subplots()
    axis.axis("off")
    axis.text(0.5, 0.5, "暂无可用数据", color=TEXT, fontproperties=_font(13), ha="center", va="center")
    _save_figure(figure, path)
