"""Diagnose why ``return * ratio`` can reduce annual maximum drawdown.

示例:

    python scripts/debug_scaled_return_drawdown.py --ratio 50 --returns "0.10,-0.30,0.05"

也可以指定日期:

    python scripts/debug_scaled_return_drawdown.py --ratio 0.5 ^
      --dates "2024-01-01,2024-01-02,2024-01-03" ^
      --returns "0.10,-0.30,0.05"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.xpl_service import XPLAnalyzer  # noqa: E402


DEFAULT_DATES = ["2024-01-01", "2024-01-02", "2024-01-03"]
DEFAULT_RETURNS = [0.10, -0.30, 0.05]


def normalize_ratio(value: str | float | int) -> float:
    """Convert 50, "50%", 0.5, and "0.5" to the ratio used by the algorithm."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("ratio 不能为空")

    has_percent = raw.endswith("%")
    if has_percent:
        raw = raw[:-1].strip()

    ratio = float(raw)
    if has_percent or abs(ratio) > 1:
        ratio = ratio / 100
    return ratio


def parse_csv_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_csv_strings(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_metric_rows(
    *,
    dates: list[str],
    returns: list[float],
    ratio: float,
    field: str = "start_return",
) -> list[dict[str, Any]]:
    if len(dates) != len(returns):
        raise ValueError(f"dates 数量({len(dates)})必须等于 returns 数量({len(returns)})")
    if field not in {"start_return", "index_return"}:
        raise ValueError("field 只能是 start_return 或 index_return")

    other_field = "index_return" if field == "start_return" else "start_return"
    return [
        {
            "date": date,
            field: ret * ratio,
            other_field: ret * ratio,
        }
        for date, ret in zip(dates, returns)
    ]


def get_year_drawdowns(metrics: dict[str, Any], field: str) -> list[dict[str, Any]]:
    metric_key = "start_maximum_drawdown" if field == "start_return" else "index_maximum_drawdown"
    return list((metrics.get(metric_key) or {}).get("year_maximum_drawdown") or [])


def pick_year_drawdown(rows: list[dict[str, Any]], field: str, year: int) -> float:
    metrics = XPLAnalyzer().get_calculate_metrics_v1(rows)
    for item in get_year_drawdowns(metrics, field):
        if int(item.get("year")) == year:
            return float(item.get("drawdown") or 0)
    raise ValueError(f"没有找到 {year} 年的最大回撤")


def calculate_running_drawdown(net_values: Iterable[float]) -> list[float]:
    peak = -math.inf
    result: list[float] = []
    for net_value in net_values:
        peak = max(peak, net_value)
        result.append((peak - net_value) / peak if peak > 0 else 0)
    return result


def compute_drawdown_rows(*, dates: list[str], returns: list[float], ratio: float) -> list[dict[str, Any]]:
    scaled_returns = [ret * ratio for ret in returns]
    raw_net_values = [1 + ret for ret in returns]
    scaled_net_values = [1 + ret for ret in scaled_returns]
    raw_drawdowns = calculate_running_drawdown(raw_net_values)
    scaled_drawdowns = calculate_running_drawdown(scaled_net_values)

    return [
        {
            "date": date,
            "raw_return": raw_return,
            "scaled_return": scaled_return,
            "raw_net_value": raw_net_value,
            "scaled_net_value": scaled_net_value,
            "raw_drawdown": raw_drawdown,
            "scaled_drawdown": scaled_drawdown,
        }
        for date, raw_return, scaled_return, raw_net_value, scaled_net_value, raw_drawdown, scaled_drawdown in zip(
            dates,
            returns,
            scaled_returns,
            raw_net_values,
            scaled_net_values,
            raw_drawdowns,
            scaled_drawdowns,
        )
    ]


def format_percent(value: float) -> str:
    return f"{value * 100:.6f}%"


def print_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "date",
        "raw_return",
        "scaled_return",
        "raw_net_value",
        "scaled_net_value",
        "raw_drawdown",
        "scaled_drawdown",
    ]
    print("\n逐日诊断:")
    print(" | ".join(headers))
    print("-" * 116)
    for row in rows:
        print(
            " | ".join(
                [
                    str(row["date"]),
                    format_percent(row["raw_return"]),
                    format_percent(row["scaled_return"]),
                    f"{row['raw_net_value']:.10f}",
                    f"{row['scaled_net_value']:.10f}",
                    format_percent(row["raw_drawdown"]),
                    format_percent(row["scaled_drawdown"]),
                ]
            )
        )


def print_metrics_summary(*, dates: list[str], returns: list[float], ratio: float, field: str) -> None:
    raw_rows = build_metric_rows(dates=dates, returns=returns, ratio=1, field=field)
    scaled_rows = build_metric_rows(dates=dates, returns=returns, ratio=ratio, field=field)
    raw_metrics = XPLAnalyzer().get_calculate_metrics_v1(raw_rows)
    scaled_metrics = XPLAnalyzer().get_calculate_metrics_v1(scaled_rows)

    metric_label = "模型结果" if field == "start_return" else "指数"
    metric_key = "start_maximum_drawdown" if field == "start_return" else "index_maximum_drawdown"

    print(f"\n真实 XPLAnalyzer 指标口径: {metric_label} {metric_key}")
    for title, metrics in [("原始 return", raw_metrics), (f"return * {ratio:g}", scaled_metrics)]:
        max_drawdown = metrics[metric_key]
        total = max_drawdown["total_maximum_drawdown"]
        years = max_drawdown["year_maximum_drawdown"]
        print(f"\n{title}:")
        print(f"  total_maximum_drawdown.drawdown = {format_percent(float(total['drawdown']))}")
        print("  year_maximum_drawdown:")
        for item in years:
            print(
                "    "
                f"{int(item['year'])}: {format_percent(float(item['drawdown']))} "
                f"(date={item['date']}, net_value={float(item['net_value']):.10f})"
            )

    print("\n关键公式:")
    print("  net_value = 1 + return")
    print("  scaled_net_value = 1 + return * ratio")
    print("  drawdown = (历史最高 net_value - 当前 net_value) / 历史最高 net_value")
    print("所以当 ratio 小于 1 时，收益序列整体更靠近 1，峰值和低点的距离通常会被压缩，最大回撤就会变小。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="诊断指定 return * 比例 后，XPL 年最大回撤为什么会变小。",
    )
    parser.add_argument(
        "--ratio",
        default="50",
        help="比例。支持 50、50%%、0.5，默认 50。",
    )
    parser.add_argument(
        "--returns",
        default=",".join(str(value) for value in DEFAULT_RETURNS),
        help="逗号分隔的收益序列，默认 0.10,-0.30,0.05。",
    )
    parser.add_argument(
        "--dates",
        default=",".join(DEFAULT_DATES),
        help="逗号分隔的日期序列，数量必须和 returns 一致。",
    )
    parser.add_argument(
        "--field",
        choices=["start_return", "index_return"],
        default="start_return",
        help="诊断模型结果还是指数，默认 start_return。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出逐日诊断行。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ratio = normalize_ratio(args.ratio)
    returns = parse_csv_floats(args.returns)
    dates = parse_csv_strings(args.dates)

    rows = compute_drawdown_rows(dates=dates, returns=returns, ratio=ratio)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"ratio = {ratio:g}")
        print_table(rows)
        print_metrics_summary(dates=dates, returns=returns, ratio=ratio, field=args.field)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
