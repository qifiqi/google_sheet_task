"""策略回测 Word 报告适配服务。"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.repositories import task_repository, task_result_repository
from app.models import TaskResult, TaskResultReturn
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis_service import xpl_analyzer
from app.services.strategy_backtest_report_charts import generate_report_charts
from app.dto.strategy_backtest_report import StrategyBacktestReportRequestDTO
from app.services.word_export_template import generate_word_document
from app.utils.backtest_report_metadata import get_backtest_model_version
from app.utils.return_series import parse_return_series_fields
from app.utils.value_parser import parse_date, parse_float, parse_int, parse_ratio
from app.services.performance_analysis.portfolio_combiner import (
    combine_product_returns,
    cumulative_to_daily,
    daily_to_cumulative,
    normalize_weight,
)


class StrategyBacktestReportService:
    """将 V1 指标结果适配为通用 Word JSON。"""

    def generate_word(self, payload: dict[str, Any] | StrategyBacktestReportRequestDTO) -> tuple[str, BytesIO]:
        # 先完成 DTO 校验，再调用性能分析，保证路由层只负责收发请求。
        """处理generate_word相关逻辑。"""
        request = payload if isinstance(payload,
                                        StrategyBacktestReportRequestDTO) else StrategyBacktestReportRequestDTO.from_payload(
            payload)

        # 三类来源在此统一为累计收益序列，后续指标、图表与 Word 渲染完全复用。
        returns = self._resolve_returns(request)
        runtime = self._runtime_params(request.runtime_params)
        result = xpl_analyzer.get_calculate_metrics_v1_with_dataframes(returns, runtime)
        if not result.metrics or result.index_df.empty:
            raise ValueError("收益数据无法生成回测报告")

        # 把 DataFrame 和指标字典转换成通用 Word JSON。
        report_data = self._build_report_data(request, result)
        chart_data = self._build_chart_data(result)
        dates = self._dates(result.index_df)
        first_date = dates[0].strftime("%Y-%m-%d")
        last_date = dates[-1].strftime("%Y-%m-%d")
        with TemporaryDirectory(prefix="strategy_backtest_report_") as temp_dir:
            # 图片只在临时目录中存在，DOCX 保存时会将图片内容嵌入文件。
            chart_paths = generate_report_charts(chart_data, temp_dir)
            report_data["blocks"].extend([
                {"type": "heading", "text": "九、分析图表", "level": 1},
                *[
                    {"type": "image", "title": title, "path": path, "caption": f"{title}（基于传入回测数据生成）"}
                    for title, path in chart_paths.items()
                ],
                # {"type": "heading", "text": "十、指标计算说明", "level": 1},
                # {"type": "bullet_list", "items": [
                #     "净值按每日收益率连续复合计算，月度与年度指标由 performance_analysis 统一计算。",
                #     "超额收益按策略收益率减指数收益率计算。",
                #     "市场下跌阶段和上涨阶段阈值通过 runtime_params 传入。",
                # ]},
                {"type": "heading", "text": "十、结论", "level": 1},
                *[{"type": "paragraph", "text": text} for text in self._conclusion(result.metrics, result, first_date, last_date)],
            ])
            output_path = Path(temp_dir) / "report.docx"
            generate_word_document(report_data, output_path)
            raw = output_path.read_bytes()

        filename = request.filename or self._default_filename(request)
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        return filename, BytesIO(raw)

    def _default_filename(self, request: StrategyBacktestReportRequestDTO) -> str:
        """按报告类型、产品代码和生成时间构造默认下载文件名。"""
        stock_codes = [
            str(product.get("stock_code") or "").strip().upper()
            for product in request.products
            if isinstance(product, dict) and str(product.get("stock_code") or "").strip()
        ]
        suffix = "-".join([*stock_codes, datetime.now().strftime("%Y%m%d%H%M%S")])
        return f"{request.report_type}-{suffix}" if suffix else f"{request.report_type}-{datetime.now():%Y%m%d%H%M%S}"

    def _resolve_returns(self, request: StrategyBacktestReportRequestDTO) -> list[dict[str, Any]]:
        """将单品、V2 或多品输入统一为 result_mapper 所需的累计收益序列。"""
        if request.report_type == "RPT-M":
            return self._combine_product_returns(request.products, request.weighting_mode)
        return self._resolve_source_returns({
            "returns": request.returns,
            "task_id": request.task_id,
            "return_series_id": request.return_series_id,
            "google_sheet_url": request.google_sheet_url,
            "spreadsheet_id": request.spreadsheet_id,
            "google_sheet_name": request.google_sheet_name,
        })

    def _resolve_source_returns(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """读取一种收益来源，并规范为按日期升序的累计收益率。"""
        if source.get("returns"):
            return self._normalize_returns(source["returns"])
        if source.get("task_id"):
            return self._returns_from_task(
                str(source["task_id"]),
                source.get("return_series_id"),
            )
        spreadsheet_id = self._spreadsheet_id(source)
        rows, _sheet_result, _sheet_df = xpl_analyzer.get_google_sheet_data(
            spreadsheet_id,
            str(source["google_sheet_name"]),
        )
        return self._normalize_returns(rows)

    @staticmethod
    def _spreadsheet_id(source: dict[str, Any]) -> str:
        """处理_spreadsheet_id相关逻辑。"""
        spreadsheet_id = str(source.get("spreadsheet_id") or "").strip()
        if spreadsheet_id:
            return spreadsheet_id
        url = str(source.get("google_sheet_url") or "").strip()
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        raise ValueError("google_sheet_url 无法解析 spreadsheet_id")

    @staticmethod
    def _returns_from_task(task_id: str, return_series_id: Any) -> list[dict[str, Any]]:
        """处理_returns_from_task相关逻辑。"""
        if return_series_id is not None:
            series_id = parse_int(return_series_id)
            if series_id is None:
                raise ValueError("return_series_id 必须是整数")
            series = task_result_repository.get_return_entity(series_id)
            if not series or series.task_id != task_id:
                raise ValueError("return_series_id 不属于指定 task_id")
            return StrategyBacktestReportService._normalize_returns(parse_return_series_fields(series))

        series_ids = task_result_repository.list_return_series_ids_by_task(task_id)
        if not series_ids:
            raise ValueError("任务没有可用的收益序列")
        if len(series_ids) > 1:
            raise ValueError("任务包含多条收益序列，请传入 return_series_id")
        series = task_result_repository.get_return_entity(series_ids[0])
        if not series:
            raise ValueError("任务收益序列不存在")
        return StrategyBacktestReportService._normalize_returns(parse_return_series_fields(series))

    def _combine_product_returns(
        self,
        products: list[dict[str, Any]],
        weighting_mode: str = "daily_compound",
    ) -> list[dict[str, Any]]:
        """将多产品组合委托给统一组合器。"""
        inputs = [
            {
                "returns": self._resolve_source_returns(product),
                "ratio": product.get("ratio", product.get("weight")),
            }
            for product in products
        ]
        return combine_product_returns(inputs, weighting_mode=weighting_mode)

    @staticmethod
    def _normalized_weights(products: list[dict[str, Any]]) -> list[float]:
        """统一比例解析器的兼容包装。"""
        return [
            float(normalize_weight(product.get("weight", product.get("ratio"))))
            for product in products
        ]

    @staticmethod
    def _normalize_returns(rows: Any) -> list[dict[str, Any]]:
        """处理_normalize_returns相关逻辑。"""
        if not isinstance(rows, list):
            raise ValueError("收益序列必须是数组")
        normalized: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"收益序列第 {index} 项必须是对象")
            raw_date = row.get("date") or row.get("stock_date")
            try:
                parsed_date = parse_date(raw_date)
                if parsed_date is None:
                    raise ValueError("日期无效")
                normalized_date = parsed_date.isoformat()
                index_return = float(row.get("index_return"))
                start_return = float(row.get("start_return"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"收益序列第 {index} 项的日期或收益率无效") from exc
            if not math.isfinite(index_return) or not math.isfinite(start_return):
                raise ValueError(f"收益序列第 {index} 项的收益率必须是有限数")
            if index_return <= -1 or start_return <= -1:
                raise ValueError(f"收益序列第 {index} 项的累计收益率不能小于等于 -100%")
            if normalized_date in normalized:
                raise ValueError(f"收益序列日期重复: {normalized_date}")
            normalized[normalized_date] = {
                "date": normalized_date,
                "index_return": index_return,
                "start_return": start_return,
            }
        if len(normalized) < 2:
            raise ValueError("收益序列至少需要 2 个交易日")
        return [normalized[current_date] for current_date in sorted(normalized)]

    @staticmethod
    def _cumulative_to_daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """统一收益转换器的兼容包装。"""
        return cumulative_to_daily(rows)

    @staticmethod
    def _daily_to_cumulative(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """统一复利转换器的兼容包装。"""
        return daily_to_cumulative(rows)

    @staticmethod
    def _runtime_params(raw: Any) -> MetricsRuntimeParamsDTO:
        """处理_runtime_params相关逻辑。"""
        return MetricsRuntimeParamsDTO.from_raw(raw)

    def _build_report_data(self, payload: StrategyBacktestReportRequestDTO, result: Any) -> dict[str, Any]:
        """将回测指标转换为通用 Word JSON 协议。"""
        metrics = result.metrics
        report_type = payload.report_type
        if report_type not in {"RPT-S", "RPT-M"}:
            raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")
        dates = self._dates(result.index_df)
        first_date = dates[0].strftime("%Y-%m-%d")
        last_date = dates[-1].strftime("%Y-%m-%d")
        generated_at = datetime.now()
        model_version = str(payload.metadata.get("model_version") or "")
        if not model_version:
            model_version = get_backtest_model_version(payload.metadata.get("sheet_title"))
        metadata = [
            {"label": "报告编号", "value": f"{report_type}-{generated_at:%Y%m%d}"},
            {"label": "模型版本", "value": model_version},
            {"label": "价格类型", "value": str(payload.metadata.get("price_type") or "")},
            {"label": "生成日期", "value": generated_at.strftime("%Y年%m月%d日 %H:%M")},
            {"label": "数据区间", "value": f"{first_date} 至 {last_date}"},
            {"label": "总交易日", "value": f"{len(result.index_df)} 天"},
            {"label": "无风险利率", "value": str(payload.metadata.get("risk_free_rate") or "0.00%")},
        ]
        weight_allocation = self._weight_allocation(payload, report_type)
        sections = self._sections(metrics, result)
        blocks: list[dict[str, Any]] = [
            {"type": "metadata", "items": metadata},
            {"type": "table", "title": "权重分配", **weight_allocation},
        ]
        for section in sections:
            blocks.append({"type": "heading", "text": section["title"], "level": 1})
            for subsection in section["subsections"]:
                if subsection.get("title"):
                    blocks.append({"type": "heading", "text": subsection["title"], "level": 2})
                blocks.append({"type": "table", **subsection["table"]})
        return {
            "title": payload.title,
            "footer": payload.title,
            "blocks": blocks,
        }

    @staticmethod
    def _weight_allocation(payload: StrategyBacktestReportRequestDTO, report_type: str) -> dict[str, Any]:
        """构造报告中的股票权重表格。"""
        raw = payload.weight_allocation
        if isinstance(raw, dict) and raw.get("columns") and isinstance(raw.get("rows"), list):
            return raw
        products = payload.products
        rows = []
        if isinstance(products, list):
            for product in products:
                if isinstance(product, dict):
                    weight = str(product.get("ratio") or product.get("weight") or "").strip()
                    if report_type == "RPT-S" and not weight:
                        weight = "100.00%"
                    rows.append([
                        str(product.get("stock_code") or product.get("product_name") or "未命名"),
                        str(product.get("product_name") or ""),
                        weight if not weight or weight.endswith("%") else f"{weight}%",
                    ])
        if not rows and report_type == "RPT-S":
            rows = [["单品", "", "100.00%"]]
        return {"columns": ["股票代码", "股票名", "权重"], "rows": rows or [["", "", ""]]}

    def _sections(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """按模板顺序合并各表格 JSON。"""
        return [
            {"title": "一、收益类指标", "subsections": self._return_section(metrics, result)},
            {"title": "二、风险类指标", "subsections": self._risk_section(metrics, result)},
            {"title": "三、风险调整收益指标", "subsections": self._risk_adjusted_section(metrics, result)},
            {"title": "四、月度收益分布", "subsections": self._monthly_section(metrics, result)},
            {"title": "五、日度收益分布", "subsections": self._daily_section(metrics, result)},
            {"title": "六、超额收益分析", "subsections": self._excess_section(metrics, result)},
            {"title": "七、极端行情表现", "subsections": self._extreme_section(metrics, result)},
            {"title": "八、资金曲线特征", "subsections": self._capital_curve_section(metrics, result)},
        ]

    def _return_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造一、收益类指标章节的全部表格；数值统一取自 V1 指标结果。

        超额列为两个 V1 数值的展示减法（策略-指数），不含业务口径计算。
        """
        _ = result
        index_cumulative = self._num(metrics.get("index_cumulative_return"))
        strategy_cumulative = self._num(metrics.get("start_cumulative_return"))
        excess_cumulative = self._num(metrics.get("excess_cumulative_return"))
        index_annualized = self._year_all(metrics.get("index_annualized_rates"), "annualized_return")
        strategy_annualized = self._year_all(metrics.get("start_annualized_rates"), "annualized_return")
        index_volatility = self._year_all(metrics.get("index_sharpe_ratios"), "annual_std_dev")
        strategy_volatility = self._year_all(metrics.get("start_sharpe_ratios"), "annual_std_dev")
        index_returns = self._metric_by_year(metrics.get("index_returns_rate"), "annual_return")
        strategy_returns = self._metric_by_year(metrics.get("start_returns_rate"), "annual_return")
        years = sorted(set(index_returns) | set(strategy_returns))
        rolling_rows = [
            self._rolling_row(metrics, months)
            for months in (3, 6, 12)
        ]
        return [
            {"title": "1.1 核心收益", "table": self._table(
                ["指标", "指数", "策略", "超额(策略-指数)"], [
                    ["累计回报率", self._pct(index_cumulative), self._pct(strategy_cumulative),
                     self._pct(excess_cumulative)],
                    ["年化收益率", self._pct(index_annualized), self._pct(strategy_annualized),
                     self._pct(self._num(strategy_annualized) - self._num(index_annualized))],
                    ["年化波动率", self._pct(index_volatility), self._pct(strategy_volatility),
                     self._pct(self._num(strategy_volatility) - self._num(index_volatility))],
                ])},
            {"title": "1.2 分年度收益率", "table": self._table(
                ["年份", "指数", "策略", "超额(策略-指数)"], [
                    [year, self._pct(index_returns.get(year)), self._pct(strategy_returns.get(year)),
                     self._pct(self._num(strategy_returns.get(year)) - self._num(index_returns.get(year)))]
                    for year in years
                ])},
            {"title": "1.3 滚动收益（月度窗口）", "table": self._table(
                ["滚动周期", "指数平均收益", "策略平均收益", "策略胜率(跑赢指数)"], rolling_rows)},
        ]

    @classmethod
    def _rolling_row(cls, metrics: dict[str, Any], months: int) -> list[str]:
        """直接消费 V1 滚动聚合导出；数据不足 5 年时展示 V1 返回的 reason。"""
        label = f"{months}个月滚动"
        reason = metrics.get(f"rolling_return_{months}_reason")
        if reason:
            return [f"{label}（{reason}）", "-", "-", "-"]
        index_avg = metrics.get(f"index_rolling_return_{months}_avg_return")
        start_avg = metrics.get(f"start_rolling_return_{months}_avg_return")
        win_rate = metrics.get(f"rolling_return_{months}_win_rate")
        if index_avg is None or start_avg is None or win_rate is None:
            return [label, "-", "-", "-"]
        return [label, cls._pct(index_avg), cls._pct(start_avg), cls._pct(win_rate)]

    def _risk_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造二、风险类指标章节的全部表格；数值统一取自 V1 指标结果。

        2.2 超额回撤列为两个 V1 回撤值的展示减法（指数-策略，口径见 metrics TODO）。
        """
        _ = result
        index_drawdown = self._total_metric(metrics.get("index_maximum_drawdown"), "drawdown")
        strategy_drawdown = self._total_metric(metrics.get("start_maximum_drawdown"), "drawdown")
        index_years = self._metric_by_year((metrics.get("index_maximum_drawdown") or {}).get("year_maximum_drawdown"),
                                           "drawdown")
        strategy_years = self._metric_by_year(
            (metrics.get("start_maximum_drawdown") or {}).get("year_maximum_drawdown"), "drawdown")
        years = sorted(set(index_years) | set(strategy_years))
        drawdown_rows = [
            [year, self._pct(-self._num(index_years.get(year))), self._pct(-self._num(strategy_years.get(year))),
             self._pct(self._num(index_years.get(year)) - self._num(strategy_years.get(year)))]
            for year in years
        ]
        daily_drawdown_threshold = metrics.get("daily_drawdown_threshold")
        if daily_drawdown_threshold is None:
            daily_drawdown_threshold = MetricsRuntimeParamsDTO().daily_drawdown_threshold
        return [
            {"title": "2.1 回撤指标", "table": self._table(
                ["指标", "指数", "策略"], [
                    ["最大回撤(MDD)", self._pct(-self._num(index_drawdown)), self._pct(-self._num(strategy_drawdown))],
                    ["最大回撤修复天数(年度最大)",
                     self._integer(metrics.get("index_maximum_number_of_backtest_repair_days")),
                     self._integer(metrics.get("start_maximum_number_of_backtest_repair_days"))],
                    [f"回撤发生次数(单日>{self._percent_label(daily_drawdown_threshold)})",
                     self._integer(metrics.get("index_dd_count")),
                     self._integer(metrics.get("start_dd_count"))],
                ])},
            {"title": "2.2 分年度最大回撤", "table": self._table(
                ["年份", "指数回撤", "策略回撤", "超额回撤(策略-指数)"], drawdown_rows)},
        ]

    def _risk_adjusted_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造三、风险调整收益指标章节的表格。"""
        return [{"table": self._table(
            ["指标", "指数", "策略"], [
                ["夏普比率", self._decimal(self._year_all(metrics.get("index_sharpe_ratios"), "sharpe_ratio")),
                 self._decimal(self._year_all(metrics.get("start_sharpe_ratios"), "sharpe_ratio"))],
                ["卡玛比率", self._decimal(self._year_all(metrics.get("index_kama_ratio"), "kama_ratio")),
                 self._decimal(self._year_all(metrics.get("start_kama_ratio"), "kama_ratio"))],
                ["索提诺比率", self._decimal(self._year_all(metrics.get("index_sortino_ratio"), "sortino_ratio")),
                 self._decimal(self._year_all(metrics.get("start_sortino_ratio"), "sortino_ratio"))],
                ["超额夏普比率", "-", self._decimal(metrics.get("excess_sharpe"))],
                ["超额索提诺比率", "-", self._decimal(metrics.get("excess_sortino"))],
            ])}]

    def _monthly_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造四、月度收益分布章节的全部表格；数值统一取自 V1 指标结果。"""
        _ = result
        distribution_labels = ["< -5%", "-5%~-2%", "-2%~0%", "0%~2%", "2%~5%", "5%~10%", ">10%"]
        index_distribution = self._num_list(metrics.get("index_monthly_distribution"))
        index_distribution_pct = self._num_list(metrics.get("index_monthly_distribution_pct"))
        strategy_distribution = self._num_list(metrics.get("start_monthly_distribution"))
        strategy_distribution_pct = self._num_list(metrics.get("start_monthly_distribution_pct"))
        distribution_rows = [
            [label,
             self._integer(self._pick(index_distribution, index)),
             self._pct(self._pick(index_distribution_pct, index) / 100),
             self._integer(self._pick(strategy_distribution, index)),
             self._pct(self._pick(strategy_distribution_pct, index) / 100)]
            for index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总月数", self._integer(metrics.get("total_months")), self._integer(metrics.get("total_months"))],
            ["盈利月数", self._integer(metrics.get("index_profit_months")),
             self._integer(metrics.get("start_profit_months"))],
            ["亏损月数", self._integer(metrics.get("index_loss_months")),
             self._integer(metrics.get("start_loss_months"))],
            ["月盈利百分比", self._pct(metrics.get("index_profit_percentage")),
             self._pct(metrics.get("start_profit_percentage"))],
            ["平均月收益率", self._pct(self._year_all(metrics.get("index_sharpe_ratios"), "avg_monthly_return")),
             self._pct(self._year_all(metrics.get("start_sharpe_ratios"), "avg_monthly_return"))],
            ["月收益率标准差", self._pct(self._year_all(metrics.get("index_sharpe_ratios"), "monthly_std_dev")),
             self._pct(self._year_all(metrics.get("start_sharpe_ratios"), "monthly_std_dev"))],
            ["最大单月收益", self._pct(metrics.get("index_max_monthly_return")),
             self._pct(metrics.get("start_max_monthly_return"))],
            ["最大单月亏损", self._pct(metrics.get("index_max_monthly_loss")),
             self._pct(metrics.get("start_max_monthly_loss"))],
            ["月收益率偏度", self._decimal(metrics.get("index_monthly_return_skewness")),
             self._decimal(metrics.get("start_monthly_return_skewness"))],
            ["月收益率峰度", self._decimal(metrics.get("index_monthly_return_kurtosis")),
             self._decimal(metrics.get("start_monthly_return_kurtosis"))],
        ]
        return [
            {"title": "4.1 月度统计总览", "table": self._table(
                ["指标", "指数", "策略"], summary_rows)},
            {"title": "4.2 月度收益区间分布", "table": self._table(
                ["收益区间", "指数月数", "指数占比", "策略月数", "策略占比"], distribution_rows)},
        ]

    def _daily_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造五、日度收益分布章节的全部表格；数值统一取自 V1 指标结果。"""
        distribution_labels = ["<-5%", "-5%~-3%", "-3%~-1%", "-1%~0%", "0%~1%", "1%~3%", "3%~5%", ">5%"]
        index_distribution = self._num_list(metrics.get("index_days_distribution"))
        index_distribution_pct = self._num_list(metrics.get("index_days_distribution_pct"))
        strategy_distribution = self._num_list(metrics.get("start_days_distribution"))
        strategy_distribution_pct = self._num_list(metrics.get("start_days_distribution_pct"))
        distribution_rows = [
            [label,
             self._integer(self._pick(index_distribution, index)),
             self._pct(self._pick(index_distribution_pct, index) / 100),
             self._integer(self._pick(strategy_distribution, index)),
             self._pct(self._pick(strategy_distribution_pct, index) / 100)]
            for index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总交易日", self._integer(metrics.get("total_trading_days")),
             self._integer(metrics.get("total_trading_days"))],
            ["盈利天数", self._integer(metrics.get("index_profit_days")),
             self._integer(metrics.get("start_profit_days"))],
            ["亏损天数", self._integer(metrics.get("index_loss_days")),
             self._integer(metrics.get("start_loss_days"))],
            ["日盈利百分比", self._pct(metrics.get("index_days_profit_percentage")),
             self._pct(metrics.get("start_days_profit_percentage"))],
            ["日均收益率", self._pct(metrics.get("index_mean_daily_return")),
             self._pct(metrics.get("start_mean_daily_return"))],
            ["日收益率标准差", self._pct(metrics.get("index_daily_return_std")),
             self._pct(metrics.get("start_daily_return_std"))],
            ["最大单日收益", self._pct(metrics.get("index_max_daily_gain")),
             self._pct(metrics.get("start_max_daily_gain"))],
            ["最大单日亏损", self._pct(metrics.get("index_max_daily_loss")),
             self._pct(metrics.get("start_max_daily_loss"))],
            ["日收益率偏度", self._decimal(metrics.get("index_mean_daily_skewness")),
             self._decimal(metrics.get("start_mean_daily_skewness"))],
            ["日收益率峰度", self._decimal(metrics.get("index_mean_daily_kurtosis")),
             self._decimal(metrics.get("start_mean_daily_kurtosis"))],
        ]
        profit_loss_rows = [
            ["平均盈利日收益", self._pct(metrics.get("index_avg_profit_day_return")),
             self._pct(metrics.get("start_avg_profit_day_return"))],
            ["平均亏损日收益", self._pct(metrics.get("index_avg_loss_day_return")),
             self._pct(metrics.get("start_avg_loss_day_return"))],
            ["盈亏比(平均盈利/平均亏损)", self._decimal(metrics.get("index_profit_loss_ratio")),
             self._decimal(metrics.get("start_profit_loss_ratio"))],
            ["单笔最大盈利/最大亏损", self._decimal(metrics.get("index_max_profit_loss_ratio")),
             self._decimal(metrics.get("start_max_profit_loss_ratio"))],
        ]
        return [
            {"title": "5.1 日度统计总览", "table": self._table(
                ["指标", "指数", "策略"], summary_rows)},
            {"title": "5.2 盈亏比分析", "table": self._table(
                ["指标", "指数", "策略"], profit_loss_rows)},
            {"title": "5.3 日度收益区间分布", "table": self._table(
                ["收益区间", "指数天数", "指数占比", "策略天数", "策略占比"], distribution_rows)},
        ]

    def _excess_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造六、超额收益分析章节的全部表格；数值统一取自 V1 指标结果。"""
        _ = result
        annualized = self._year_all(metrics.get("excess_returns"), "annualized_return_diff")
        distribution_labels = ["<-2%", "-2%~0%", "0%~2%", "2%~5%", ">5%"]
        distribution_counts = self._num_list(metrics.get("excess_distribution"))
        distribution_pct = self._num_list(metrics.get("excess_distribution_pct"))
        distribution_rows = [
            [label, self._integer(self._pick(distribution_counts, index)),
             self._pct(self._pick(distribution_pct, index) / 100)]
            for index, label in enumerate(distribution_labels)]
        excess_rows = [
            ["累计超额(策略-指数)", self._pct(metrics.get("excess_cumulative_return"))],
            ["年化超额", self._pct(annualized)],
            ["月超额收益均值", self._pct(metrics.get("average_monthly_excess_return"))],
            ["月超额收益波动率", self._pct(metrics.get("monthly_excess_return_standard_deviation"))],
            ["月超额胜率(>0)", self._pct(metrics.get("monthly_excess_win_rate"))],
            ["最大单月超额", self._pct(metrics.get("max_monthly_excess"))],
        ]
        excess_rolling_rows = [self._excess_rolling_row(metrics, months) for months in (1, 3, 6, 12)]
        return [
            {"title": "6.1 超额收益统计", "table": self._table(
                ["指标", "数值"], excess_rows)},
            {"title": "6.2 超额收益区间分布", "table": self._table(
                ["超额区间", "月数", "占比"], distribution_rows)},
            {"title": "6.3 滚动超额胜率", "table": self._table(
                ["滚动窗口", "平均超额", "正超额概率"], excess_rolling_rows)},
        ]

    @classmethod
    def _excess_rolling_row(cls, metrics: dict[str, Any], months: int) -> list[str]:
        """1 个月窗口取 V1 月度超额统计；其余窗口消费 V1 滚动超额聚合导出。"""
        label = f"{months}个月"
        if months == 1:
            average = metrics.get("average_monthly_excess_return")
            win_rate = metrics.get("monthly_excess_win_rate")
            if average is None and win_rate is None:
                return [label, "-", "-"]
            return [label, cls._pct(average), cls._pct(win_rate)]
        reason = metrics.get(f"excess_rolling_return_{months}_reason")
        if reason:
            return [f"{label}（{reason}）", "-", "-"]
        average = metrics.get(f"excess_rolling_return_{months}_avg_return")
        win_rate = metrics.get(f"excess_rolling_return_{months}_win_rate")
        if average is None or win_rate is None:
            return [label, "-", "-"]
        return [label, cls._pct(average), cls._pct(win_rate)]

    def _extreme_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造七、极端行情表现章节的全部表格；数值统一取自 V1 指标结果。

        跑赢次数为 V1 胜率的分子口径（下跌阶段：跑赢且策略仍低于阈值；
        上涨阶段：跑赢且策略超上涨阈值），见 metrics.py 内的口径 TODO。
        """
        _ = result
        downturn_threshold = metrics.get("market_downturn_threshold")
        if downturn_threshold is None:
            downturn_threshold = MetricsRuntimeParamsDTO().market_downturn_threshold
        upturn_threshold = metrics.get("market_upturn_threshold")
        if upturn_threshold is None:
            upturn_threshold = MetricsRuntimeParamsDTO().market_upturn_threshold
        daily_extreme_threshold = metrics.get("daily_extreme_threshold")
        if daily_extreme_threshold is None:
            daily_extreme_threshold = MetricsRuntimeParamsDTO().daily_extreme_threshold
        daily_extreme_label = self._percent_label(daily_extreme_threshold)
        downturn_rows = [
            ["阶段月数", self._integer(metrics.get("index_downfall_months_len")),
             self._integer(metrics.get("start_downfall_months_len")), "-"],
            ["平均收益", self._pct(metrics.get("index_downfall_avg_return")),
             self._pct(metrics.get("start_downfall_avg_return")),
             self._pct(metrics.get("downfall_excess_avg_return"))],
            ["策略跑赢次数", "-", self._integer(metrics.get("downfall_outperform_count")),
             self._pct(metrics.get("downfall_win_rate"))]]
        upturn_rows = [
            ["阶段月数", self._integer(metrics.get("index_upward_months_len")),
             self._integer(metrics.get("start_upward_months_len")), "-"],
            ["平均收益", self._pct(metrics.get("index_upward_avg_return")),
             self._pct(metrics.get("start_upward_avg_return")),
             self._pct(metrics.get("upward_excess_avg_return"))],
            ["策略跑赢次数", "-", self._integer(metrics.get("upward_outperform_count")),
             self._pct(metrics.get("upward_win_rate"))]]
        extreme_rows = [
            ["最大单日涨幅", self._pct(metrics.get("index_max_daily_gain")),
             self._pct(metrics.get("start_max_daily_gain"))],
            ["最大单日跌幅", self._pct(metrics.get("index_max_daily_loss")),
             self._pct(metrics.get("start_max_daily_loss"))],
            [f"涨幅>{daily_extreme_label}的天数", self._integer(metrics.get("index_daily_gain_days")),
             self._integer(metrics.get("start_daily_gain_days"))],
            [f"跌幅>{daily_extreme_label}的天数", self._integer(metrics.get("index_daily_loss_days")),
             self._integer(metrics.get("start_daily_loss_days"))],
            [f"涨跌比(涨>{daily_extreme_label}/跌>{daily_extreme_label})",
             self._decimal(metrics.get("index_daily_gain_loss_ratio")),
             self._decimal(metrics.get("start_daily_gain_loss_ratio"))]]
        return [
            {"title": f"7.1 市场下跌阶段（指数月收益 < {self._threshold_label(downturn_threshold)}）",
             "table": self._table(["指标", "指数", "策略", "超额"], downturn_rows)},
            {"title": f"7.2 市场上涨阶段（指数月收益 > {self._threshold_label(upturn_threshold)}）",
             "table": self._table(["指标", "指数", "策略", "超额"], upturn_rows)},
            {"title": "7.3 极端单日表现", "table": self._table(
                ["指标", "指数", "策略"], extreme_rows)},
        ]

    @staticmethod
    def _threshold_label(value: float) -> str:
        """把阈值格式化为报告标题用的百分比标签（保留有效数字，正数带 + 号）。"""
        text = f"{value * 100:g}%"
        return text if text.startswith("-") else f"+{text}"

    @staticmethod
    def _percent_label(value: float) -> str:
        """把非负阈值格式化为百分比标签（不带符号，用于行内标签）。"""
        return f"{value * 100:g}%"

    def _capital_curve_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造八、资金曲线特征章节的表格；净值/连涨连跌/创新高统计统一取自 V1 指标结果。"""
        _ = result
        index_consecutive = metrics.get("index_consecutive") or {}
        start_consecutive = metrics.get("start_consecutive") or {}
        rows = [
            ["初始净值", self._decimal(metrics.get("index_net_value_left"), 4),
             self._decimal(metrics.get("start_net_value_left"), 4)],
            ["期末净值", self._decimal(metrics.get("index_net_value_right"), 4),
             self._decimal(metrics.get("start_net_value_right"), 4)],
            ["净值创新高次数", self._integer(metrics.get("index_new_high_count")),
             self._integer(metrics.get("start_new_high_count"))],
            ["净值创新高频率", self._pct(metrics.get("index_new_high_frequency")),
             self._pct(metrics.get("start_new_high_frequency"))],
            ["最大涨幅区间(连续)", self._pct(index_consecutive.get("max_gain")),
             self._pct(start_consecutive.get("max_gain"))],
            ["最大跌幅区间(连续)", self._pct(index_consecutive.get("max_loss")),
             self._pct(start_consecutive.get("max_loss"))],
            ["创新高平均间隔(天)", self._decimal(metrics.get("index_new_high_avg_interval_days"), 1),
             self._decimal(metrics.get("start_new_high_avg_interval_days"), 1)]]
        return [{"table": self._table(["指标", "指数", "策略"], rows)}]

    @classmethod
    def _metric_by_year(cls, items: Any, field: str) -> dict[str, Any]:
        """处理_metric_by_year相关逻辑。"""
        return {
            str(item.get("year")): item.get(field)
            for item in items or []
            if isinstance(item, dict) and item.get("year") not in (None, "all")
        }

    @classmethod
    def _net_values(cls, frame: Any, return_column: str) -> list[float]:
        """处理_net_values相关逻辑。"""
        values = frame["net_value"].tolist() if "net_value" in frame else []
        if values:
            return [cls._num(value) for value in values]
        return [1 + cls._num(value) for value in frame[return_column].tolist()]

    @staticmethod
    def _num_list(values: Any) -> list[float]:
        """读取 V1 分布结果（Pandas Series 已转换为数值列表，顺序与区间标签一致）。"""
        if not isinstance(values, list):
            return []
        return [StrategyBacktestReportService._num(value) for value in values]

    @staticmethod
    def _pick(values: list[float], index: int) -> float:
        """按下标取 V1 分布值，越界时返回 0。"""
        return values[index] if 0 <= index < len(values) else 0.0

    @classmethod
    def _decimal(cls, value: Any, digits: int = 4) -> str:
        """处理_decimal相关逻辑。"""
        return f"{cls._num(value):.{digits}f}"

    @classmethod
    def _integer(cls, value: Any) -> str:
        """处理_integer相关逻辑。"""
        return str(int(cls._num(value)))

    @staticmethod
    def _table(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
        """处理_table相关逻辑。"""
        return {"columns": columns, "rows": rows}

    @classmethod
    def _year_all(cls, items: Any, field: str) -> Any:
        """处理_year_all相关逻辑。"""
        if isinstance(items, dict):
            item = items.get("all") or {}
            return item.get(field) if isinstance(item, dict) else None
        for item in items or []:
            if isinstance(item, dict) and str(item.get("year")) == "all":
                return item.get(field)
        return None

    @staticmethod
    def _total_metric(metrics: Any, field: str) -> Any:
        """处理_total_metric相关逻辑。"""
        if not isinstance(metrics, dict):
            return None
        total = metrics.get("total_maximum_drawdown") or {}
        return total.get(field) if isinstance(total, dict) else None

    @staticmethod
    def _num(value: Any) -> float:
        """处理_num相关逻辑。"""
        number = parse_float(value, default=0.0)
        return number if number is not None else 0.0

    @classmethod
    def _pct(cls, value: Any) -> str:
        """处理_pct相关逻辑。"""
        return f"{cls._num(value):.2%}"

    def _conclusion(self, metrics: dict[str, Any], result: Any, first_date: str, last_date: str) -> list[str]:
        """处理_conclusion相关逻辑；累计回报与累计超额直接取自 V1 指标结果。"""
        _ = result
        index_return = self._num(metrics.get("index_cumulative_return"))
        start_return = self._num(metrics.get("start_cumulative_return"))
        excess_return = self._num(metrics.get("excess_cumulative_return"))
        return [
            f"本报告覆盖 {first_date} 至 {last_date}，指数累计回报率为 {index_return:.2%}，策略累计回报率为 {start_return:.2%}。",
            f"策略相对指数的累计超额回报为 {excess_return:.2%}。",
        ]

    @staticmethod
    def _dates(frame: Any) -> list[date]:
        """处理_dates相关逻辑。"""
        values = frame["date"].tolist()
        result = []
        for value in values:
            parsed = parse_date(value)
            if parsed is None:
                raise ValueError(f"无法解析日期: {value}")
            result.append(parsed)
        return result

    def _build_chart_data(self, result: Any) -> dict[str, Any]:
        # result_mapper 已提供累计收益对应的净值，不再对累计收益重复复利。
        """处理_build_chart_data相关逻辑。"""
        dates = self._dates(result.index_df)
        index_df = result.index_df
        start_df = result.start_df
        excess_df = result.excess_df
        metrics = result.metrics
        annual_index = {str(item.get("year")): self._num(item.get("annual_return")) for item in
                        metrics.get("index_returns_rate") or [] if isinstance(item, dict)}
        annual_start = {str(item.get("year")): self._num(item.get("annual_return")) for item in
                        metrics.get("start_returns_rate") or [] if isinstance(item, dict)}
        years = sorted(set(annual_index) | set(annual_start))
        if not years:
            years = sorted({str(value.year) for value in dates})
        return {
            "dates": dates,
            "index_nav": self._net_values(index_df, "index_return"),
            "strategy_nav": self._net_values(start_df, "start_return"),
            "excess_nav": self._net_values(excess_df, "excess_return"),
            "index_daily_returns": index_df["daily_return"].tolist() if "daily_return" in index_df else [],
            "strategy_daily_returns": start_df["daily_return"].tolist() if "daily_return" in start_df else [],
            "monthly_excess_returns": [self._num(item.get("monthly_excess_return_diff")) for item in
                                       metrics.get("monthly_excess_returns") or [] if isinstance(item, dict)],
            "annual_returns": {"years": years, "index": [annual_index.get(year, 0) for year in years],
                               "strategy": [annual_start.get(year, 0) for year in years]},
        }

strategy_backtest_report_service = StrategyBacktestReportService()
