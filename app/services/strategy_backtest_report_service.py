"""多产品回测 Word 报告适配服务。"""

from __future__ import annotations

import math
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis_service import xpl_analyzer
from app.services.strategy_backtest_report_charts import generate_report_charts
from app.dto.strategy_backtest_report import StrategyBacktestReportRequestDTO
from app.services.strategy_backtest_report_template import (
    build_demo_report_data,
    generate_strategy_backtest_report,
)


class StrategyBacktestReportService:
    """将 V1 指标结果适配为声明式 DOCX 模板所需的数据结构。"""

    def generate_word(self, payload: dict[str, Any] | StrategyBacktestReportRequestDTO) -> tuple[str, BytesIO]:
        # 先完成 DTO 校验，再调用性能分析，保证路由层只负责收发请求。
        request = payload if isinstance(payload, StrategyBacktestReportRequestDTO) else StrategyBacktestReportRequestDTO.from_payload(payload)

        # 运行参数暂时只作为分析接口的配置入口，后续可扩展市场阶段指标。
        runtime = self._runtime_params(request.runtime_params)
        result = xpl_analyzer.get_calculate_metrics_v1_with_dataframes(request.returns, runtime)
        if not result.metrics or result.index_df.empty:
            raise ValueError("收益数据无法生成回测报告")

        # 把 DataFrame 和指标字典转换成 Word JSON 模板约定的数据结构。
        report_data = self._build_report_data(request, result)
        chart_data = self._build_chart_data(result)
        with TemporaryDirectory(prefix="strategy_backtest_report_") as temp_dir:
            # 图片只在临时目录中存在，DOCX 保存时会将图片内容嵌入文件。
            chart_paths = generate_report_charts(chart_data, temp_dir)
            report_data["charts"] = [
                {"title": title, "image_path": path, "caption": f"{title}（基于传入回测数据生成）"}
                for title, path in chart_paths.items()
            ]
            output_path = Path(temp_dir) / "report.docx"
            generate_strategy_backtest_report(report_data, output_path)
            raw = output_path.read_bytes()

        filename = request.filename.strip()
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        return filename, BytesIO(raw)

    @staticmethod
    def _runtime_params(raw: Any) -> MetricsRuntimeParamsDTO:
        if raw is None:
            return MetricsRuntimeParamsDTO()
        if not isinstance(raw, dict):
            raise ValueError("runtime_params 必须是对象")
        try:
            downturn = float(raw.get("market_downturn_threshold", -0.02))
            upturn = float(raw.get("market_upturn_threshold", 0.02))
        except (TypeError, ValueError) as exc:
            raise ValueError("市场阶段阈值必须是数字") from exc
        if not math.isfinite(downturn) or not math.isfinite(upturn):
            raise ValueError("市场阶段阈值必须是有限数字")
        return MetricsRuntimeParamsDTO(
            market_downturn_threshold=downturn,
            market_upturn_threshold=upturn,
        )

    def _build_report_data(self, payload: StrategyBacktestReportRequestDTO, result: Any) -> dict[str, Any]:
        metrics = result.metrics
        report_type = payload.report_type
        if report_type not in {"RPT", "ZRPT"}:
            raise ValueError("report_type 仅支持 RPT 或 ZRPT")
        demo = build_demo_report_data(report_type)
        dates = self._dates(result.index_df)
        first_date = dates[0].strftime("%Y-%m-%d")
        last_date = dates[-1].strftime("%Y-%m-%d")
        title = payload.title
        metadata = {
            **demo["metadata"],
            **payload.metadata,
            "report_id": str(payload.report_id or payload.metadata.get("report_id") or f"REPORT-{datetime.now():%Y%m%d%H%M%S}"),
            "generated_at": datetime.now().strftime("%Y年%m月%d日 %H:%M"),
            "date_range": f"{first_date} 至 {last_date}",
            "total_trading_days": f"{len(result.index_df)} 天",
        }
        demo.update({"title": title, "metadata": metadata})
        demo["weight_allocation"] = self._weight_allocation(payload, report_type)
        demo["sections"] = self._sections(metrics, result)
        demo["calculation_notes"] = [
            ("指标计算口径", [
                "净值按每日收益率连续复合计算，月度与年度指标由 performance_analysis 统一计算。",
                "超额收益按策略收益率减指数收益率计算。",
                "市场下跌阶段和上涨阶段阈值通过 runtime_params 传入。",
            ])
        ]
        demo["conclusion"] = self._conclusion(metrics, result, first_date, last_date)
        return demo

    @staticmethod
    def _weight_allocation(payload: StrategyBacktestReportRequestDTO, report_type: str) -> dict[str, Any]:
        raw = payload.weight_allocation
        if isinstance(raw, dict) and raw.get("columns") and isinstance(raw.get("rows"), list):
            return raw
        products = payload.products
        rows = []
        if isinstance(products, list):
            for product in products:
                if isinstance(product, dict):
                    rows.append([
                        str(product.get("stock_code") or product.get("product_name") or "未命名"),
                        str(product.get("product_name") or ""),
                        str(product.get("ratio") or product.get("weight") or ""),
                    ])
        if not rows:
            rows = [["组合", "多产品回测", ""]] if report_type == "ZRPT" else [["组合", "策略", ""]]
        return {"columns": ["股票代码", "股票名", "权重"], "rows": rows}

    def _sections(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        index_all = self._year_all(metrics.get("index_annualized_rates"), "annualized_return")
        start_all = self._year_all(metrics.get("start_annualized_rates"), "annualized_return")
        index_mdd = self._total_metric(metrics.get("index_maximum_drawdown"), "drawdown")
        start_mdd = self._total_metric(metrics.get("start_maximum_drawdown"), "drawdown")
        index_sharpe = self._year_all(metrics.get("index_sharpe_ratios"), "sharpe_ratio")
        start_sharpe = self._year_all(metrics.get("start_sharpe_ratios"), "sharpe_ratio")
        return [
            {"title": "一、收益类指标", "subsections": [{"title": "1.1 核心收益", "table": self._table(
                ["指标", "指数", "策略", "超额"], [
                    ["累计回报率", self._pct(self._compound_return(result.index_df, "index_return")), self._pct(self._compound_return(result.start_df, "start_return")), self._pct(self._compound_return(result.start_df, "start_return") - self._compound_return(result.index_df, "index_return"))],
                    ["年化收益率", self._pct(index_all), self._pct(start_all), self._pct(self._num(start_all) - self._num(index_all))],
                ])}]},
            {"title": "二、风险类指标", "subsections": [{"title": "2.1 最大回撤", "table": self._table(
                ["指标", "指数", "策略"], [["最大回撤", self._pct(-self._num(index_mdd)), self._pct(-self._num(start_mdd))]])}]},
            {"title": "三、风险调整收益指标", "subsections": [{"table": self._table(
                ["指标", "指数", "策略"], [["夏普比率", self._num_text(index_sharpe), self._num_text(start_sharpe)], ["超额夏普比率", "-", self._num_text(metrics.get("excess_sharp"))]])}]},
            {"title": "四、月度收益分布", "subsections": [{"title": "4.1 月度统计", "table": self._table(
                ["指标", "指数", "策略"], [["盈利月比例", self._pct(self._average_metric(metrics.get("index_profit_monthly"), "profit_monthly_percentage")), self._pct(self._average_metric(metrics.get("start_profit_monthly"), "profit_monthly_percentage"))], ["月收益波动率", self._pct(metrics.get("index_monthly_return_volatility")), self._pct(metrics.get("start_monthly_return_volatility"))]])}]},
            {"title": "五、日度收益分布", "subsections": [{"title": "5.1 日度统计", "table": self._table(
                ["指标", "指数", "策略"], [["交易日数", str(len(result.index_df)), str(len(result.start_df))], ["日均收益率", self._pct(metrics.get("index_mean_daily_return")), self._pct(metrics.get("start_mean_daily_return"))]])}]},
            {"title": "六、超额收益分析", "subsections": [{"title": "6.1 超额收益", "table": self._table(
                ["指标", "数值"], [["年化超额收益", self._pct(self._num(start_all) - self._num(index_all))], ["超额夏普比率", self._num_text(metrics.get("excess_sharp"))], ["超额回撤胜率", self._pct(metrics.get("excess_drawdown_winning_rate"))]])}]},
        ]

    @staticmethod
    def _table(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
        return {"columns": columns, "rows": rows}

    @staticmethod
    def _year_all(items: Any, field: str) -> Any:
        if isinstance(items, dict):
            item = items.get("all") or {}
            return item.get(field) if isinstance(item, dict) else None
        for item in items or []:
            if isinstance(item, dict) and str(item.get("year")) == "all":
                return item.get(field)
        return None

    @staticmethod
    def _total_metric(metrics: Any, field: str) -> Any:
        if not isinstance(metrics, dict):
            return None
        total = metrics.get("total_maximum_drawdown") or {}
        return total.get(field) if isinstance(total, dict) else None

    @classmethod
    def _average_metric(cls, items: Any, field: str) -> float:
        values = [cls._num(item[field]) for item in items or [] if isinstance(item, dict) and item.get(field) is not None]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _num(value: Any) -> float:
        try:
            number = float(value)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _pct(cls, value: Any) -> str:
        return f"{cls._num(value):.2%}"

    @classmethod
    def _num_text(cls, value: Any) -> str:
        return f"{cls._num(value):.4f}"

    def _conclusion(self, metrics: dict[str, Any], result: Any, first_date: str, last_date: str) -> list[str]:
        index_return = self._compound_return(result.index_df, "index_return")
        start_return = self._compound_return(result.start_df, "start_return")
        return [
            f"本报告覆盖 {first_date} 至 {last_date}，指数累计回报率为 {index_return:.2%}，策略累计回报率为 {start_return:.2%}。",
            f"策略相对指数的累计超额回报为 {start_return - index_return:.2%}。",
        ]

    @staticmethod
    def _dates(frame: Any) -> list[date]:
        values = frame["date"].tolist()
        result = []
        for value in values:
            if hasattr(value, "date"):
                result.append(value.date())
            elif isinstance(value, date):
                result.append(value)
            else:
                result.append(datetime.fromisoformat(str(value)).date())
        return result

    def _build_chart_data(self, result: Any) -> dict[str, Any]:
        # 图表使用累计复合净值，避免直接绘制单日净值导致曲线失真。
        dates = self._dates(result.index_df)
        index_df = result.index_df
        start_df = result.start_df
        excess_df = result.excess_df
        metrics = result.metrics
        annual_index = {str(item.get("year")): self._num(item.get("annual_return")) for item in metrics.get("index_returns_rate") or [] if isinstance(item, dict)}
        annual_start = {str(item.get("year")): self._num(item.get("annual_return")) for item in metrics.get("start_returns_rate") or [] if isinstance(item, dict)}
        years = sorted(set(annual_index) | set(annual_start))
        if not years:
            years = sorted({str(value.year) for value in dates})
        return {
            "dates": dates,
            "index_nav": self._compound(index_df["index_return"].tolist()),
            "strategy_nav": self._compound(start_df["start_return"].tolist()),
            "excess_nav": self._compound(excess_df["excess_return"].tolist()),
            "index_daily_returns": index_df["daily_return"].tolist() if "daily_return" in index_df else [],
            "strategy_daily_returns": start_df["daily_return"].tolist() if "daily_return" in start_df else [],
            "monthly_excess_returns": [self._num(item.get("monthly_excess_return_diff")) for item in metrics.get("monthly_excess_returns") or [] if isinstance(item, dict)],
            "annual_returns": {"years": years, "index": [annual_index.get(year, 0) for year in years], "strategy": [annual_start.get(year, 0) for year in years]},
        }

    @classmethod
    def _compound(cls, values: list[Any]) -> list[float]:
        nav = 1.0
        result = []
        for value in values:
            nav *= 1 + cls._num(value)
            result.append(nav)
        return result or [1.0]

    @classmethod
    def _compound_return(cls, frame: Any, column: str) -> float:
        values = frame[column].tolist() if column in frame else []
        return cls._compound(values)[-1] - 1


strategy_backtest_report_service = StrategyBacktestReportService()
