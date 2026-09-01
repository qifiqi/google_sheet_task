"""策略回测 Word 报告适配服务。"""

from __future__ import annotations

import math
import re
from statistics import mean, median, pstdev
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.extensions import db
from app.models import TaskResult, TaskResultReturn
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis_service import xpl_analyzer
from app.services.strategy_backtest_report_charts import generate_report_charts
from app.dto.strategy_backtest_report import StrategyBacktestReportRequestDTO
from app.services.word_export_template import generate_word_document
from app.utils.backtest_report_metadata import get_backtest_model_version
from app.utils.return_series import parse_return_series_fields
from app.utils.value_parser import parse_date, parse_float, parse_int, parse_ratio


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
            return self._combine_product_returns(request.products)
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
            series = db.session.get(TaskResultReturn, series_id)
            if not series or series.task_id != task_id:
                raise ValueError("return_series_id 不属于指定 task_id")
            return StrategyBacktestReportService._normalize_returns(parse_return_series_fields(series))

        series_ids = [
            row[0]
            for row in (
                db.session.query(TaskResult.return_series_id)
                .filter(
                    TaskResult.task_id == task_id,
                    TaskResult.return_series_id.isnot(None),
                )
                .order_by(TaskResult.id.asc())
                .all()
            )
        ]
        if not series_ids:
            raise ValueError("任务没有可用的收益序列")
        if len(series_ids) > 1:
            raise ValueError("任务包含多条收益序列，请传入 return_series_id")
        series = db.session.get(TaskResultReturn, series_ids[0])
        if not series:
            raise ValueError("任务收益序列不存在")
        return StrategyBacktestReportService._normalize_returns(parse_return_series_fields(series))

    def _combine_product_returns(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按比例合成多品指数与策略的每日收益，再还原为累计收益。"""
        weights = self._normalized_weights(products)
        daily_maps = []
        common_dates: set[str] | None = None
        for product in products:
            cumulative_returns = self._resolve_source_returns(product)
            daily_returns = self._cumulative_to_daily(cumulative_returns)
            daily_map = {item["date"]: item for item in daily_returns}
            common_dates = set(daily_map) if common_dates is None else common_dates & set(daily_map)
            daily_maps.append(daily_map)
        if not common_dates:
            raise ValueError("多品收益序列没有共同交易日")

        portfolio_daily_returns = []
        for current_date in sorted(common_dates):
            index_return = sum(
                daily_map[current_date]["index_return"] * weight
                for daily_map, weight in zip(daily_maps, weights)
            )
            start_return = sum(
                daily_map[current_date]["start_return"] * weight
                for daily_map, weight in zip(daily_maps, weights)
            )
            portfolio_daily_returns.append({
                "date": current_date,
                "index_return": index_return,
                "start_return": start_return,
            })
        return self._daily_to_cumulative(portfolio_daily_returns)

    @staticmethod
    def _normalized_weights(products: list[dict[str, Any]]) -> list[float]:
        """处理_normalized_weights相关逻辑。"""
        raw_weights = []
        percent_flags = []
        for index, product in enumerate(products, start=1):
            raw = product.get("weight", product.get("ratio"))
            text = str(raw or "").strip()
            if not text:
                raise ValueError(f"products[{index}] 缺少 weight 或 ratio")
            percent_flags.append(text.endswith("%"))
            value = parse_ratio(text)
            if value is None:
                raise ValueError(f"products[{index}] 的比例不是有效数字")
            if value < 0:
                raise ValueError(f"products[{index}] 的比例必须是非负有限数")
            raw_weights.append(value)

        total = sum(raw_weights)
        if all(percent_flags) or total <= 1:
            weights = raw_weights
        else:
            weights = [value / 100 for value in raw_weights]
        return weights

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
        """处理_cumulative_to_daily相关逻辑。"""
        previous_index_net = 1.0
        previous_start_net = 1.0
        daily_returns = []
        for row in rows:
            index_net = 1 + row["index_return"]
            start_net = 1 + row["start_return"]
            daily_returns.append({
                "date": row["date"],
                "index_return": index_net / previous_index_net - 1,
                "start_return": start_net / previous_start_net - 1,
            })
            previous_index_net = index_net
            previous_start_net = start_net
        return daily_returns

    @staticmethod
    def _daily_to_cumulative(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """处理_daily_to_cumulative相关逻辑。"""
        index_net = 1.0
        start_net = 1.0
        cumulative_returns = []
        for row in rows:
            index_net *= 1 + row["index_return"]
            start_net *= 1 + row["start_return"]
            cumulative_returns.append({
                "date": row["date"],
                "index_return": index_net - 1,
                "start_return": start_net - 1,
            })
        return cumulative_returns

    @staticmethod
    def _runtime_params(raw: Any) -> MetricsRuntimeParamsDTO:
        """处理_runtime_params相关逻辑。"""
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
            {"title": "七、极端行情表现", "subsections": self._extreme_section(result)},
            {"title": "八、资金曲线特征", "subsections": self._capital_curve_section(result)},
        ]

    def _return_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造一、收益类指标章节的全部表格。"""
        index_cumulative = self._compound_return(result.index_df, "index_return")
        strategy_cumulative = self._compound_return(result.start_df, "start_return")
        index_annualized = self._year_all(metrics.get("index_annualized_rates"), "annualized_return")
        strategy_annualized = self._year_all(metrics.get("start_annualized_rates"), "annualized_return")
        index_volatility = self._year_all(metrics.get("index_sharpe_ratios"), "annual_std_dev")
        strategy_volatility = self._year_all(metrics.get("start_sharpe_ratios"), "annual_std_dev")
        index_returns = self._metric_by_year(metrics.get("index_returns_rate"), "annual_return")
        strategy_returns = self._metric_by_year(metrics.get("start_returns_rate"), "annual_return")
        index_months = [item["value"] for item in self._monthly_returns(result.index_df)]
        strategy_months = [item["value"] for item in self._monthly_returns(result.start_df)]
        years = sorted(set(index_returns) | set(strategy_returns))
        rolling_rows = []
        rolling_status = metrics.get("index_rolling_return_3")
        rolling_unavailable_reason = rolling_status.get("reason") if isinstance(rolling_status, dict) else None
        for months in (3, 6, 12):
            if rolling_unavailable_reason:
                rolling_rows.append([f"{months}个月滚动（{rolling_unavailable_reason}）", "-", "-", "-"])
                continue
            pairs = [
                (mean(index_months[index:index + months]), mean(strategy_months[index:index + months]))
                for index in range(max(0, min(len(index_months), len(strategy_months)) - months + 1))
            ]
            rolling_rows.append(
                [f"{months}个月滚动", self._pct(mean(item[0] for item in pairs)),
                 self._pct(mean(item[1] for item in pairs)),
                 self._pct(sum(strategy > index for index, strategy in pairs) / len(pairs))]
                if pairs else [f"{months}个月滚动", "-", "-", "-"]
            )
        return [
            {"title": "1.1 核心收益", "table": self._table(
                ["指标", "指数", "策略", "超额(策略-指数)"], [
                    ["累计回报率", self._pct(index_cumulative), self._pct(strategy_cumulative),
                     self._pct(strategy_cumulative - index_cumulative)],
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

    def _risk_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造二、风险类指标章节的全部表格。"""
        index_drawdown = self._total_metric(metrics.get("index_maximum_drawdown"), "drawdown")
        strategy_drawdown = self._total_metric(metrics.get("start_maximum_drawdown"), "drawdown")
        index_daily = self._daily_returns(result.index_df)
        strategy_daily = self._daily_returns(result.start_df)
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
        return [
            {"title": "2.1 回撤指标", "table": self._table(
                ["指标", "指数", "策略"], [
                    ["最大回撤(MDD)", self._pct(-self._num(index_drawdown)), self._pct(-self._num(strategy_drawdown))],
                    ["最大回撤修复天数(年度最大)",
                     self._integer(metrics.get("index_maximum_number_of_backtest_repair_days")),
                     self._integer(metrics.get("start_maximum_number_of_backtest_repair_days"))],
                    ["回撤发生次数(单日>5%)", self._integer(self._count_below(index_daily, -0.05)),
                     self._integer(self._count_below(strategy_daily, -0.05))],
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
                ["索提诺比率", self._decimal(self._year_all(metrics.get("index_sotino_ratio"), "sortino_ratio")),
                 self._decimal(self._year_all(metrics.get("start_sotino_ratio"), "sortino_ratio"))],
                ["超额夏普比率", "-", self._decimal(metrics.get("excess_sharp"))],
                ["超额索提诺比率", "-", self._decimal(metrics.get("excess_of_promissory_note"))],
            ])}]

    def _monthly_section(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        """构造四、月度收益分布章节的全部表格。"""
        index_values = [item["value"] for item in self._monthly_returns(result.index_df)]
        strategy_values = [item["value"] for item in self._monthly_returns(result.start_df)]
        bins = [-1, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1]
        index_distribution = self._distribution(index_values, bins)
        strategy_distribution = self._distribution(strategy_values, bins)
        distribution_labels = ["< -5%", "-5%~-2%", "-2%~0%", "0%~2%", "2%~5%", "5%~10%", ">10%"]
        distribution_rows = [
            [label, self._integer(index_distribution[index][0]), self._pct(index_distribution[index][1]),
             self._integer(strategy_distribution[index][0]), self._pct(strategy_distribution[index][1])] for
            index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总月数", self._integer(len(index_values)), self._integer(len(strategy_values))],
            ["盈利月数", self._integer(sum(value > 0 for value in index_values)),
             self._integer(sum(value > 0 for value in strategy_values))],
            ["亏损月数", self._integer(sum(value < 0 for value in index_values)),
             self._integer(sum(value < 0 for value in strategy_values))],
            ["月盈利百分比", self._pct(self._ratio(index_values, lambda value: value > 0)),
             self._pct(self._ratio(strategy_values, lambda value: value > 0))],
            ["平均月收益率", self._pct(self._mean(index_values)), self._pct(self._mean(strategy_values))],
            ["月收益率标准差", self._pct(self._std(index_values)), self._pct(self._std(strategy_values))],
            ["最大单月收益", self._pct(max(index_values, default=0)), self._pct(max(strategy_values, default=0))],
            ["最大单月亏损", self._pct(min(index_values, default=0)), self._pct(min(strategy_values, default=0))],
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
        """构造五、日度收益分布章节的全部表格。"""
        index_values = self._daily_returns(result.index_df)
        strategy_values = self._daily_returns(result.start_df)
        bins = [-1, -0.05, -0.03, -0.01, 0, 0.01, 0.03, 0.05, 1]
        index_distribution = self._distribution(index_values, bins)
        strategy_distribution = self._distribution(strategy_values, bins)
        distribution_labels = ["<-5%", "-5%~-3%", "-3%~-1%", "-1%~0%", "0%~1%", "1%~3%", "3%~5%", ">5%"]
        distribution_rows = [
            [label, self._integer(index_distribution[index][0]), self._pct(index_distribution[index][1]),
             self._integer(strategy_distribution[index][0]), self._pct(strategy_distribution[index][1])] for
            index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总交易日", self._integer(len(index_values)), self._integer(len(strategy_values))],
            ["盈利天数", self._integer(sum(value > 0 for value in index_values)),
             self._integer(sum(value > 0 for value in strategy_values))],
            ["亏损天数", self._integer(sum(value < 0 for value in index_values)),
             self._integer(sum(value < 0 for value in strategy_values))],
            ["日盈利百分比", self._pct(self._ratio(index_values, lambda value: value > 0)),
             self._pct(self._ratio(strategy_values, lambda value: value > 0))],
            ["日均收益率", self._pct(self._mean(index_values)), self._pct(self._mean(strategy_values))],
            ["日收益率标准差", self._pct(self._std(index_values)), self._pct(self._std(strategy_values))],
            ["最大单日收益", self._pct(max(index_values, default=0)), self._pct(max(strategy_values, default=0))],
            ["最大单日亏损", self._pct(min(index_values, default=0)), self._pct(min(strategy_values, default=0))],
            ["日收益率偏度", self._decimal(metrics.get("index_mean_daily_skewness")),
             self._decimal(metrics.get("start_mean_daily_skewness"))],
            ["日收益率峰度", self._decimal(metrics.get("index_mean_daily_kurtosis")),
             self._decimal(metrics.get("start_mean_daily_kurtosis"))],
        ]
        gain_rows = [["平均盈利日收益", self._pct(self._mean([value for value in index_values if value > 0])),
                      self._pct(self._mean([value for value in strategy_values if value > 0]))],
                     ["平均亏损日收益", self._pct(self._mean([value for value in index_values if value < 0])),
                      self._pct(self._mean([value for value in strategy_values if value < 0]))]]
        index_gains, strategy_gains = [value for value in index_values if value > 0], [value for value in
                                                                                       strategy_values if value > 0]
        index_losses, strategy_losses = [value for value in index_values if value < 0], [value for value in
                                                                                         strategy_values if value < 0]
        profit_loss_rows = gain_rows + [
            ["盈亏比(平均盈利/平均亏损)",
             self._decimal(self._ratio_by_abs(self._mean(index_gains), self._mean(index_losses))),
             self._decimal(self._ratio_by_abs(self._mean(strategy_gains), self._mean(strategy_losses)))],
            ["单笔最大盈利/最大亏损",
             self._decimal(self._ratio_by_abs(max(index_gains, default=0), min(index_losses, default=0))),
             self._decimal(self._ratio_by_abs(max(strategy_gains, default=0), min(strategy_losses, default=0)))],
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
        """构造六、超额收益分析章节的全部表格。"""
        pairs = self._matched_pairs(self._monthly_returns(result.index_df), self._monthly_returns(result.start_df))
        values = [strategy - index for _month, index, strategy in pairs]
        index_cumulative = self._compound_return(result.index_df, "index_return")
        strategy_cumulative = self._compound_return(result.start_df, "start_return")
        annualized = self._num(self._year_all(metrics.get("start_annualized_rates"), "annualized_return")) - self._num(
            self._year_all(metrics.get("index_annualized_rates"), "annualized_return"))
        distribution = self._distribution(values, [-1, -0.02, 0, 0.02, 0.05, 1])
        distribution_rows = [[label, self._integer(count), self._pct(ratio)] for label, (count, ratio) in
                             zip(["<-2%", "-2%~0%", "0%~2%", "2%~5%", ">5%"], distribution)]
        excess_rows = [
            ["累计超额(策略-指数)", self._pct(strategy_cumulative - index_cumulative)],
            ["年化超额", self._pct(annualized)],
            ["月超额收益均值", self._pct(self._mean(values))],
            ["月超额收益中位数", self._pct(self._median(values))],
            ["月超额收益标准差", self._pct(self._std(values))],
            ["月超额胜率(>0)", self._pct(self._ratio(values, lambda value: value > 0))],
            ["最大单月超额", self._pct(max(values, default=0))],
        ]
        excess_rolling_rows = []
        excess_rolling_status = metrics.get("excess_rolling_return_3")
        excess_rolling_unavailable_reason = excess_rolling_status.get("reason") if isinstance(
            excess_rolling_status, dict) else None
        for months in (1, 3, 6, 12):
            if excess_rolling_unavailable_reason:
                excess_rolling_rows.append([f"{months}个月（{excess_rolling_unavailable_reason}）", "-", "-"])
                continue
            rolling = [mean(values[index:index + months]) for index in range(max(0, len(values) - months + 1))]
            excess_rolling_rows.append([f"{months}个月", self._pct(self._mean(rolling)),
                                        self._pct(self._ratio(rolling, lambda value: value > 0))] if rolling else [
                f"{months}个月", "-", "-"])
        return [
            {"title": "6.1 超额收益统计", "table": self._table(
                ["指标", "数值"], excess_rows)},
            {"title": "6.2 超额收益区间分布", "table": self._table(
                ["超额区间", "月数", "占比"], distribution_rows)},
            {"title": "6.3 滚动超额胜率", "table": self._table(
                ["滚动窗口", "平均超额", "正超额概率"], excess_rolling_rows)},
        ]

    def _extreme_section(self, result: Any) -> list[dict[str, Any]]:
        """构造七、极端行情表现章节的全部表格。"""
        pairs = self._matched_pairs(self._monthly_returns(result.index_df), self._monthly_returns(result.start_df))
        index_daily = self._daily_returns(result.index_df)
        strategy_daily = self._daily_returns(result.start_df)
        downturn_pairs = [item for item in pairs if item[1] < -0.02]
        upturn_pairs = [item for item in pairs if item[1] > 0.02]
        downturn_index = [item[1] for item in downturn_pairs]
        downturn_strategy = [item[2] for item in downturn_pairs]
        downturn_excess = [strategy - index for index, strategy in zip(downturn_index, downturn_strategy)]
        upturn_index = [item[1] for item in upturn_pairs]
        upturn_strategy = [item[2] for item in upturn_pairs]
        upturn_excess = [strategy - index for index, strategy in zip(upturn_index, upturn_strategy)]
        downturn_rows = [["阶段月数", self._integer(len(downturn_pairs)), self._integer(len(downturn_pairs)), "-"],
                         ["平均收益", self._pct(self._mean(downturn_index)), self._pct(self._mean(downturn_strategy)),
                          self._pct(self._mean(downturn_excess))], ["中位收益", self._pct(self._median(downturn_index)),
                                                                    self._pct(self._median(downturn_strategy)),
                                                                    self._pct(self._median(downturn_excess))],
                         ["策略跑赢次数", "-", self._integer(
                             sum(strategy > index for index, strategy in zip(downturn_index, downturn_strategy))),
                          self._pct(self._ratio(downturn_excess, lambda value: value > 0))]]
        upturn_rows = [["阶段月数", self._integer(len(upturn_pairs)), self._integer(len(upturn_pairs)), "-"],
                       ["平均收益", self._pct(self._mean(upturn_index)), self._pct(self._mean(upturn_strategy)),
                        self._pct(self._mean(upturn_excess))],
                       ["中位收益", self._pct(self._median(upturn_index)), self._pct(self._median(upturn_strategy)),
                        self._pct(self._median(upturn_excess))], ["策略跑赢次数", "-", self._integer(
                sum(strategy > index for index, strategy in zip(upturn_index, upturn_strategy))), self._pct(
                self._ratio(upturn_excess, lambda value: value > 0))]]
        extreme_rows = [
            ["最大单日涨幅", self._pct(max(index_daily, default=0)), self._pct(max(strategy_daily, default=0))],
            ["最大单日跌幅", self._pct(min(index_daily, default=0)), self._pct(min(strategy_daily, default=0))],
            ["涨幅>2%的天数", self._integer(sum(value > 0.02 for value in index_daily)),
             self._integer(sum(value > 0.02 for value in strategy_daily))],
            ["跌幅>2%的天数", self._integer(sum(value < -0.02 for value in index_daily)),
             self._integer(sum(value < -0.02 for value in strategy_daily))], ["涨跌比(涨>2%/跌>2%)", self._decimal(
                self._ratio_by_abs(sum(value > 0.02 for value in index_daily),
                                   sum(value < -0.02 for value in index_daily))), self._decimal(
                self._ratio_by_abs(sum(value > 0.02 for value in strategy_daily),
                                   sum(value < -0.02 for value in strategy_daily)))]]
        return [
            {"title": "7.1 市场下跌阶段（指数月收益 < -2%）", "table": self._table(
                ["指标", "指数", "策略", "超额"], downturn_rows)},
            {"title": "7.2 市场上涨阶段（指数月收益 > +2%）", "table": self._table(
                ["指标", "指数", "策略", "超额"], upturn_rows)},
            {"title": "7.3 极端单日表现", "table": self._table(
                ["指标", "指数", "策略"], extreme_rows)},
        ]

    def _capital_curve_section(self, result: Any) -> list[dict[str, Any]]:
        """构造八、资金曲线特征章节的表格。"""
        index_values = self._net_values(result.index_df, "index_return")
        strategy_values = self._net_values(result.start_df, "start_return")
        index_highs = self._new_high_positions(index_values)
        strategy_highs = self._new_high_positions(strategy_values)
        index_consecutive = self._consecutive_changes(index_values)
        strategy_consecutive = self._consecutive_changes(strategy_values)
        rows = [
            ["初始净值", self._decimal(index_values[0] if index_values else 1, 4),
             self._decimal(strategy_values[0] if strategy_values else 1, 4)],
            ["期末净值", self._decimal(index_values[-1] if index_values else 1, 4),
             self._decimal(strategy_values[-1] if strategy_values else 1, 4)],
            ["净值创新高次数", self._integer(len(index_highs)), self._integer(len(strategy_highs))],
            ["净值创新高频率", self._pct(len(index_highs) / len(index_values) if index_values else 0),
             self._pct(len(strategy_highs) / len(strategy_values) if strategy_values else 0)],
            ["最大涨幅区间(连续)", self._pct(index_consecutive["max_gain"]),
             self._pct(strategy_consecutive["max_gain"])],
            ["最大跌幅区间(连续)", self._pct(index_consecutive["max_loss"]),
             self._pct(strategy_consecutive["max_loss"])],
            ["创新高平均间隔(天)", self._decimal(self._average_interval(index_highs), 1),
             self._decimal(self._average_interval(strategy_highs), 1)]]
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

    @classmethod
    def _daily_returns(cls, frame: Any) -> list[float]:
        """处理_daily_returns相关逻辑。"""
        net_values = cls._net_values(frame, "index_return" if "index_return" in frame else "start_return")
        return [
            current / previous - 1
            for previous, current in zip(net_values, net_values[1:])
            if previous > 0
        ]

    @classmethod
    def _monthly_returns(cls, frame: Any) -> list[dict[str, Any]]:
        """处理_monthly_returns相关逻辑。"""
        dates = cls._dates(frame)
        net_values = cls._net_values(frame, "index_return" if "index_return" in frame else "start_return")
        monthly: list[dict[str, Any]] = []
        previous_net = 1.0
        for current_date, net_value in zip(dates, net_values):
            month_key = current_date.strftime("%Y-%m")
            if monthly and monthly[-1]["month"] == month_key:
                monthly[-1].update({"date": current_date, "net_value": net_value})
                continue
            monthly.append({"month": month_key, "date": current_date, "net_value": net_value})
        for item in monthly:
            item["value"] = item["net_value"] / previous_net - 1 if previous_net else 0.0
            previous_net = item["net_value"]
        return monthly

    @staticmethod
    def _matched_pairs(index_monthly: list[dict[str, Any]], strategy_monthly: list[dict[str, Any]]) -> list[
        tuple[str, float, float]]:
        """处理_matched_pairs相关逻辑。"""
        index_by_month = {item["month"]: item["value"] for item in index_monthly}
        strategy_by_month = {item["month"]: item["value"] for item in strategy_monthly}
        return [(month, index_by_month[month], strategy_by_month[month]) for month in
                sorted(index_by_month.keys() & strategy_by_month.keys())]

    @staticmethod
    def _count_below(values: list[float], threshold: float) -> int:
        """处理_count_below相关逻辑。"""
        return sum(value < threshold for value in values)

    @staticmethod
    def _distribution(values: list[float], bins: list[float]) -> list[tuple[int, float]]:
        """处理_distribution相关逻辑。"""
        counts = [0] * (len(bins) - 1)
        for value in values:
            for index, (left, right) in enumerate(zip(bins, bins[1:])):
                if left <= value < right or (index == len(counts) - 1 and value == right):
                    counts[index] += 1
                    break
        total = len(values)
        return [(count, count / total if total else 0.0) for count in counts]

    @staticmethod
    def _mean(values: list[float]) -> float:
        """处理_mean相关逻辑。"""
        return mean(values) if values else 0.0

    @staticmethod
    def _median(values: list[float]) -> float:
        """处理_median相关逻辑。"""
        return median(values) if values else 0.0

    @staticmethod
    def _std(values: list[float]) -> float:
        """处理_std相关逻辑。"""
        return pstdev(values) if len(values) > 1 else 0.0

    @classmethod
    def _ratio(cls, values: list[float], predicate: Any) -> float:
        """处理_ratio相关逻辑。"""
        return sum(predicate(value) for value in values) / len(values) if values else 0.0

    @staticmethod
    def _ratio_by_abs(numerator: float, denominator: float) -> float:
        """处理_ratio_by_abs相关逻辑。"""
        return numerator / abs(denominator) if denominator else 0.0

    @staticmethod
    def _skew(values: list[float]) -> float:
        """处理_skew相关逻辑。"""
        if len(values) < 3 or not (std := pstdev(values)):
            return 0.0
        average = mean(values)
        return mean(((value - average) / std) ** 3 for value in values)

    @staticmethod
    def _kurtosis(values: list[float]) -> float:
        """处理_kurtosis相关逻辑。"""
        if len(values) < 4 or not (std := pstdev(values)):
            return 0.0
        average = mean(values)
        return mean(((value - average) / std) ** 4 for value in values) - 3

    @staticmethod
    def _new_high_positions(values: list[float]) -> list[int]:
        """处理_new_high_positions相关逻辑。"""
        highest = float("-inf")
        positions = []
        for index, value in enumerate(values):
            if value > highest:
                highest = value
                positions.append(index)
        return positions

    @staticmethod
    def _average_interval(positions: list[int]) -> float:
        """处理_average_interval相关逻辑。"""
        return mean(right - left for left, right in zip(positions, positions[1:])) if len(positions) > 1 else 0.0

    @staticmethod
    def _consecutive_changes(values: list[float]) -> dict[str, float]:
        """处理_consecutive_changes相关逻辑。"""
        max_gain = max_loss = current_gain = current_loss = 0.0
        for previous, current in zip(values, values[1:]):
            change = current / previous - 1 if previous else 0.0
            current_gain = (1 + current_gain) * (1 + change) - 1 if change > 0 else 0.0
            current_loss = (1 + current_loss) * (1 + change) - 1 if change < 0 else 0.0
            max_gain = max(max_gain, current_gain)
            max_loss = min(max_loss, current_loss)
        return {"max_gain": max_gain, "max_loss": max_loss}

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

    @classmethod
    def _average_metric(cls, items: Any, field: str) -> float:
        """处理_average_metric相关逻辑。"""
        values = [cls._num(item[field]) for item in items or [] if
                  isinstance(item, dict) and item.get(field) is not None]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _num(value: Any) -> float:
        """处理_num相关逻辑。"""
        number = parse_float(value, default=0.0)
        return number if number is not None else 0.0

    @classmethod
    def _pct(cls, value: Any) -> str:
        """处理_pct相关逻辑。"""
        return f"{cls._num(value):.2%}"

    @classmethod
    def _num_text(cls, value: Any) -> str:
        """处理_num_text相关逻辑。"""
        return f"{cls._num(value):.4f}"

    def _conclusion(self, metrics: dict[str, Any], result: Any, first_date: str, last_date: str) -> list[str]:
        """处理_conclusion相关逻辑。"""
        index_return = self._compound_return(result.index_df, "index_return")
        start_return = self._compound_return(result.start_df, "start_return")
        return [
            f"本报告覆盖 {first_date} 至 {last_date}，指数累计回报率为 {index_return:.2%}，策略累计回报率为 {start_return:.2%}。",
            f"策略相对指数的累计超额回报为 {start_return - index_return:.2%}。",
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

    @classmethod
    def _compound_return(cls, frame: Any, column: str) -> float:
        """处理_compound_return相关逻辑。"""
        values = frame[column].tolist() if column in frame else []
        return cls._num(values[-1]) if values else 0.0


strategy_backtest_report_service = StrategyBacktestReportService()
