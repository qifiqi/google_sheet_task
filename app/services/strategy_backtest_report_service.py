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
from app.services.strategy_backtest_report_template import generate_strategy_backtest_report
from app.utils.return_series import parse_return_series_fields
from app.utils.value_parser import parse_date, parse_float, parse_int, parse_ratio


class StrategyBacktestReportService:
    """将 V1 指标结果适配为声明式 DOCX 模板所需的数据结构。"""

    def generate_word(self, payload: dict[str, Any] | StrategyBacktestReportRequestDTO) -> tuple[str, BytesIO]:
        # 先完成 DTO 校验，再调用性能分析，保证路由层只负责收发请求。
        """处理generate_word相关逻辑。"""
        request = payload if isinstance(payload, StrategyBacktestReportRequestDTO) else StrategyBacktestReportRequestDTO.from_payload(payload)

        # 三类来源在此统一为累计收益序列，后续指标、图表与 Word 渲染完全复用。
        returns = self._resolve_returns(request)
        runtime = self._runtime_params(request.runtime_params)
        result = xpl_analyzer.get_calculate_metrics_v1_with_dataframes(returns, runtime)
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
        if all(percent_flags) or math.isclose(total, 1.0, abs_tol=1e-8):
            weights = raw_weights
        elif math.isclose(total, 100.0, abs_tol=1e-8):
            weights = [value / 100 for value in raw_weights]
        else:
            raise ValueError("多品比例之和必须为 1 或 100%")
        if not math.isclose(sum(weights), 1.0, abs_tol=1e-8):
            raise ValueError("多品比例之和必须为 1 或 100%")
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
        """处理_build_report_data相关逻辑。"""
        metrics = result.metrics
        report_type = payload.report_type
        if report_type not in {"RPT-S", "RPT-M"}:
            raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")
        dates = self._dates(result.index_df)
        first_date = dates[0].strftime("%Y-%m-%d")
        last_date = dates[-1].strftime("%Y-%m-%d")
        generated_at = datetime.now()
        metadata = {
            **payload.metadata,
            "report_id": f"{report_type}-{generated_at:%Y%m%d}",
            "model_version": str(payload.metadata.get("model_version") or ""),
            "price_type": str(payload.metadata.get("price_type") or ""),
            "generated_at": generated_at.strftime("%Y年%m月%d日 %H:%M"),
            "date_range": f"{first_date} 至 {last_date}",
            "total_trading_days": f"{len(result.index_df)} 天",
            "risk_free_rate": str(payload.metadata.get("risk_free_rate") or "0.00%"),
        }
        return {
            "report_type": report_type,
            "title": payload.title,
            "metadata": metadata,
            "weight_allocation": self._weight_allocation(payload, report_type),
            "sections": self._sections(metrics, result),
            "charts": [],
            "calculation_notes": [("指标计算口径", [
                "净值按每日收益率连续复合计算，月度与年度指标由 performance_analysis 统一计算。",
                "超额收益按策略收益率减指数收益率计算。",
                "市场下跌阶段和上涨阶段阈值通过 runtime_params 传入。",
            ])],
            "conclusion": self._conclusion(metrics, result, first_date, last_date),
        }

    @staticmethod
    def _weight_allocation(payload: StrategyBacktestReportRequestDTO, report_type: str) -> dict[str, Any]:
        """处理_weight_allocation相关逻辑。"""
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
            rows = [["组合", "多产品回测", ""]] if report_type == "RPT-M" else [["组合", "策略", ""]]
        return {"columns": ["股票代码", "股票名", "权重"], "rows": rows}

    def _sections(self, metrics: dict[str, Any], result: Any) -> list[dict[str, Any]]:
        # 累计收益：result_mapper 使用累计收益率，最后一行即为报告区间收益。
        """处理_sections相关逻辑。"""
        index_cumulative_return = self._compound_return(result.index_df, "index_return")
        strategy_cumulative_return = self._compound_return(result.start_df, "start_return")
        excess_cumulative_return = strategy_cumulative_return - index_cumulative_return

        # 年化与年度收益：均由 result_mapper 返回的 V1 指标直接提供。
        index_annualized_return = self._year_all(metrics.get("index_annualized_rates"), "annualized_return")
        strategy_annualized_return = self._year_all(metrics.get("start_annualized_rates"), "annualized_return")
        annualized_excess_return = self._num(strategy_annualized_return) - self._num(index_annualized_return)
        index_annual_volatility = self._all_metric(metrics.get("index_sharpe_ratios"), "annual_std_dev")
        strategy_annual_volatility = self._all_metric(metrics.get("start_sharpe_ratios"), "annual_std_dev")
        index_annual_returns = self._metric_by_year(metrics.get("index_returns_rate"), "annual_return")
        strategy_annual_returns = self._metric_by_year(metrics.get("start_returns_rate"), "annual_return")

        # 月度收益：从净值曲线计算，用于滚动、分布和极端市场表现。
        index_monthly_returns = self._monthly_returns(result.index_df)
        strategy_monthly_returns = self._monthly_returns(result.start_df)
        monthly_pairs = self._matched_pairs(index_monthly_returns, strategy_monthly_returns)

        # 回撤与恢复：最大回撤来自 V1 指标；持续时间从净值曲线逐段计算。
        index_max_drawdown = self._total_metric(metrics.get("index_maximum_drawdown"), "drawdown")
        strategy_max_drawdown = self._total_metric(metrics.get("start_maximum_drawdown"), "drawdown")
        index_drawdown_duration = self._average_drawdown_duration(result.index_df)
        strategy_drawdown_duration = self._average_drawdown_duration(result.start_df)
        index_max_repair_days = metrics.get("index_maximum_number_of_backtest_repair_days")
        strategy_max_repair_days = metrics.get("start_maximum_number_of_backtest_repair_days")
        index_large_loss_days = self._count_below(self._daily_returns(result.index_df), -0.05)
        strategy_large_loss_days = self._count_below(self._daily_returns(result.start_df), -0.05)
        index_year_drawdowns = self._metric_by_year(
            (metrics.get("index_maximum_drawdown") or {}).get("year_maximum_drawdown"),
            "drawdown",
        )
        strategy_year_drawdowns = self._metric_by_year(
            (metrics.get("start_maximum_drawdown") or {}).get("year_maximum_drawdown"),
            "drawdown",
        )

        # 风险调整收益：all 条目表示完整回测区间的比率。
        index_sharpe = self._all_metric(metrics.get("index_sharpe_ratios"), "sharpe_ratio")
        strategy_sharpe = self._all_metric(metrics.get("start_sharpe_ratios"), "sharpe_ratio")
        index_calmar = self._year_all(metrics.get("index_kama_ratio"), "kama_ratio")
        strategy_calmar = self._year_all(metrics.get("start_kama_ratio"), "kama_ratio")
        index_sortino = self._year_all(metrics.get("index_sotino_ratio"), "sortino_ratio")
        strategy_sortino = self._year_all(metrics.get("start_sotino_ratio"), "sortino_ratio")
        excess_sharpe = metrics.get("excess_sharp")
        excess_sortino = metrics.get("excess_of_promissory_note")

        # 月度分布变量：对应报告中的 4.1、4.2 表格。
        index_month_values = [item["value"] for item in index_monthly_returns]
        strategy_month_values = [item["value"] for item in strategy_monthly_returns]
        index_month_distribution = self._distribution(index_month_values, [-1, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1])
        strategy_month_distribution = self._distribution(strategy_month_values, [-1, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1])

        # 日度分布变量：daily_return 是累计净值的相邻日变化，不重复使用累计收益。
        index_daily_values = self._daily_returns(result.index_df)
        strategy_daily_values = self._daily_returns(result.start_df)
        index_day_distribution = self._distribution(index_daily_values, [-1, -0.05, -0.03, -0.01, 0, 0.01, 0.03, 0.05, 1])
        strategy_day_distribution = self._distribution(strategy_daily_values, [-1, -0.05, -0.03, -0.01, 0, 0.01, 0.03, 0.05, 1])

        # 超额收益变量：按相同月份匹配策略与指数，避免不同交易日范围混算。
        monthly_excess_values = [strategy_value - index_value for _month, index_value, strategy_value in monthly_pairs]
        excess_distribution = self._distribution(monthly_excess_values, [-1, -0.02, 0, 0.02, 0.05, 1])

        # 极端行情变量：使用指数月收益定义上涨、下跌阶段。
        downturn_pairs = [item for item in monthly_pairs if item[1] < -0.02]
        upturn_pairs = [item for item in monthly_pairs if item[1] > 0.02]

        # 资金曲线变量：从实际净值曲线提取净值、高点与连续涨跌特征。
        index_net_values = self._net_values(result.index_df, "index_return")
        strategy_net_values = self._net_values(result.start_df, "start_return")

        annual_years = sorted(set(index_annual_returns) | set(strategy_annual_returns))
        drawdown_years = sorted(set(index_year_drawdowns) | set(strategy_year_drawdowns))
        return [
            {"title": "一、收益类指标", "subsections": [
                {"title": "1.1 核心收益", "table": self._table(
                    ["指标", "指数", "策略", "超额(策略-指数)"], [
                        ["累计回报率", self._pct(index_cumulative_return), self._pct(strategy_cumulative_return), self._pct(excess_cumulative_return)],
                        ["年化收益率", self._pct(index_annualized_return), self._pct(strategy_annualized_return), self._pct(annualized_excess_return)],
                        ["年化波动率", self._pct(index_annual_volatility), self._pct(strategy_annual_volatility), self._pct(self._num(strategy_annual_volatility) - self._num(index_annual_volatility))],
                    ]),
                },
                {"title": "1.2 分年度收益率", "table": self._table(
                    ["年份", "指数", "策略", "超额(策略-指数)"], [
                        [year, self._pct(index_annual_returns.get(year)), self._pct(strategy_annual_returns.get(year)), self._pct(self._num(strategy_annual_returns.get(year)) - self._num(index_annual_returns.get(year)))]
                        for year in annual_years
                    ]),
                },
                {"title": "1.3 滚动收益（月度窗口）", "table": self._table(
                    ["滚动周期", "指数平均收益", "策略平均收益", "策略胜率(跑赢指数)"], [
                        self._rolling_row(index_month_values, strategy_month_values, months)
                        for months in (3, 6, 12)
                    ]),
                },
            ]},
            {"title": "二、风险类指标", "subsections": [
                {"title": "2.1 回撤指标", "table": self._table(
                    ["指标", "指数", "策略"], [
                        ["最大回撤(MDD)", self._pct(-self._num(index_max_drawdown)), self._pct(-self._num(strategy_max_drawdown))],
                        ["回撤持续时间(平均/天)", self._decimal(index_drawdown_duration, 1), self._decimal(strategy_drawdown_duration, 1)],
                        ["最大回撤修复天数(年度最大)", self._integer(index_max_repair_days), self._integer(strategy_max_repair_days)],
                        ["回撤发生次数(单日>5%)", self._integer(index_large_loss_days), self._integer(strategy_large_loss_days)],
                    ]),
                },
                {"title": "2.2 分年度最大回撤", "table": self._table(
                    ["年份", "指数回撤", "策略回撤", "超额回撤(策略-指数)"], [
                        [year, self._pct(-self._num(index_year_drawdowns.get(year))), self._pct(-self._num(strategy_year_drawdowns.get(year))), self._pct(self._num(index_year_drawdowns.get(year)) - self._num(strategy_year_drawdowns.get(year)))]
                        for year in drawdown_years
                    ]),
                },
            ]},
            {"title": "三、风险调整收益指标", "subsections": [{"table": self._table(
                ["指标", "指数", "策略", "超额"], [
                    ["夏普比率", self._decimal(index_sharpe), self._decimal(strategy_sharpe), "-"],
                    ["卡玛比率", self._decimal(index_calmar), self._decimal(strategy_calmar), "-"],
                    ["索提诺比率", self._decimal(index_sortino), self._decimal(strategy_sortino), "-"],
                    ["超额夏普比率", "-", "-", self._decimal(excess_sharpe)],
                    ["超额索提诺比率", "-", "-", self._decimal(excess_sortino)],
                    ["信息比率", "-", "-", self._information_ratio(index_daily_values, strategy_daily_values)],
                    ["收益回撤比", self._calmar_from_returns(index_annualized_return, index_max_drawdown), self._calmar_from_returns(strategy_annualized_return, strategy_max_drawdown), "-"],
                ])}]},
            {"title": "四、月度收益分布", "subsections": [
                {"title": "4.1 月度统计总览", "table": self._table(
                    ["指标", "指数", "策略"], self._monthly_summary_rows(index_month_values, strategy_month_values)),
                },
                {"title": "4.2 月度收益区间分布", "table": self._table(
                    ["收益区间", "指数(月数/占比)", "策略(月数/占比)"], self._distribution_rows(
                        ["< -5%", "-5%~-2%", "-2%~0%", "0%~2%", "2%~5%", "5%~10%", ">10%"],
                        index_month_distribution,
                        strategy_month_distribution,
                    )),
                },
            ]},
            {"title": "五、日度收益分布", "subsections": [
                {"title": "5.1 日度统计总览", "table": self._table(
                    ["指标", "指数", "策略"], self._daily_summary_rows(index_daily_values, strategy_daily_values)),
                },
                {"title": "5.2 盈亏比分析", "table": self._table(
                    ["指标", "指数", "策略"], self._profit_loss_rows(index_daily_values, strategy_daily_values)),
                },
                {"title": "5.3 日度收益区间分布", "table": self._table(
                    ["收益区间", "指数(天数/占比)", "策略(天数/占比)"], self._distribution_rows(
                        ["<-5%", "-5%~-3%", "-3%~-1%", "-1%~0%", "0%~1%", "1%~3%", "3%~5%", ">5%"],
                        index_day_distribution,
                        strategy_day_distribution,
                    )),
                },
            ]},
            {"title": "六、超额收益分析", "subsections": [
                {"title": "6.1 超额收益统计", "table": self._table(
                    ["指标", "数值"], self._excess_summary_rows(excess_cumulative_return, annualized_excess_return, monthly_excess_values)),
                },
                {"title": "6.2 超额收益区间分布", "table": self._table(
                    ["超额区间", "月数/占比"], self._single_distribution_rows(
                        ["<-2%", "-2%~0%", "0%~2%", "2%~5%", ">5%"], excess_distribution)),
                },
                {"title": "6.3 滚动超额胜率", "table": self._table(
                    ["滚动窗口", "平均超额", "正超额概率"], [
                        self._excess_rolling_row(monthly_excess_values, months) for months in (1, 3, 6, 12)
                    ]),
                },
            ]},
            {"title": "七、极端行情表现", "subsections": [
                {"title": "7.1 市场下跌阶段（指数月收益 < -2%）", "table": self._table(
                    ["指标", "指数", "策略", "超额"], self._market_phase_rows(downturn_pairs)),
                },
                {"title": "7.2 市场上涨阶段（指数月收益 > +2%）", "table": self._table(
                    ["指标", "指数", "策略", "超额"], self._market_phase_rows(upturn_pairs)),
                },
                {"title": "7.3 极端单日表现", "table": self._table(
                    ["指标", "指数", "策略"], self._extreme_day_rows(index_daily_values, strategy_daily_values)),
                },
            ]},
            {"title": "八、资金曲线特征", "subsections": [{"table": self._table(
                ["指标", "指数", "策略"], self._capital_curve_rows(index_net_values, strategy_net_values),
            )}]},
        ]

    def _all_metric(self,items: Any, field: str) -> Any:
        """处理_all_metric相关逻辑。"""
        return self._year_all(items, field)

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
    def _matched_pairs(index_monthly: list[dict[str, Any]], strategy_monthly: list[dict[str, Any]]) -> list[tuple[str, float, float]]:
        """处理_matched_pairs相关逻辑。"""
        index_by_month = {item["month"]: item["value"] for item in index_monthly}
        strategy_by_month = {item["month"]: item["value"] for item in strategy_monthly}
        return [(month, index_by_month[month], strategy_by_month[month]) for month in sorted(index_by_month.keys() & strategy_by_month.keys())]

    @classmethod
    def _average_drawdown_duration(cls, frame: Any) -> float:
        """处理_average_drawdown_duration相关逻辑。"""
        durations, current = [], 0
        peak = 0.0
        for net_value in cls._net_values(frame, "index_return" if "index_return" in frame else "start_return"):
            peak = max(peak, net_value)
            if net_value < peak:
                current += 1
            elif current:
                durations.append(current)
                current = 0
        if current:
            durations.append(current)
        return mean(durations) if durations else 0.0

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

    @classmethod
    def _rolling_row(cls, index_values: list[float], strategy_values: list[float], months: int) -> list[str]:
        """处理_rolling_row相关逻辑。"""
        pairs = [
            (mean(index_values[index:index + months]), mean(strategy_values[index:index + months]))
            for index in range(max(0, min(len(index_values), len(strategy_values)) - months + 1))
        ]
        if not pairs:
            return [f"{months}个月滚动", "-", "-", "-"]
        return [
            f"{months}个月滚动",
            cls._pct(mean(item[0] for item in pairs)),
            cls._pct(mean(item[1] for item in pairs)),
            cls._pct(sum(strategy > index for index, strategy in pairs) / len(pairs)),
        ]

    @classmethod
    def _monthly_summary_rows(cls, index_values: list[float], strategy_values: list[float]) -> list[list[str]]:
        """处理_monthly_summary_rows相关逻辑。"""
        return [
            ["总月数", cls._integer(len(index_values)), cls._integer(len(strategy_values))],
            ["盈利月数", cls._integer(sum(value > 0 for value in index_values)), cls._integer(sum(value > 0 for value in strategy_values))],
            ["亏损月数", cls._integer(sum(value < 0 for value in index_values)), cls._integer(sum(value < 0 for value in strategy_values))],
            ["月盈利百分比", cls._pct(cls._ratio(index_values, lambda value: value > 0)), cls._pct(cls._ratio(strategy_values, lambda value: value > 0))],
            ["平均月收益率", cls._pct(cls._mean(index_values)), cls._pct(cls._mean(strategy_values))],
            ["月收益率标准差", cls._pct(cls._std(index_values)), cls._pct(cls._std(strategy_values))],
            ["最大单月收益", cls._pct(max(index_values, default=0)), cls._pct(max(strategy_values, default=0))],
            ["最大单月亏损", cls._pct(min(index_values, default=0)), cls._pct(min(strategy_values, default=0))],
            ["月收益率偏度", cls._decimal(cls._skew(index_values)), cls._decimal(cls._skew(strategy_values))],
            ["月收益率峰度", cls._decimal(cls._kurtosis(index_values)), cls._decimal(cls._kurtosis(strategy_values))],
        ]

    @classmethod
    def _daily_summary_rows(cls, index_values: list[float], strategy_values: list[float]) -> list[list[str]]:
        """处理_daily_summary_rows相关逻辑。"""
        return [
            ["总交易日", cls._integer(len(index_values)), cls._integer(len(strategy_values))],
            ["盈利天数", cls._integer(sum(value > 0 for value in index_values)), cls._integer(sum(value > 0 for value in strategy_values))],
            ["亏损天数", cls._integer(sum(value < 0 for value in index_values)), cls._integer(sum(value < 0 for value in strategy_values))],
            ["日盈利百分比", cls._pct(cls._ratio(index_values, lambda value: value > 0)), cls._pct(cls._ratio(strategy_values, lambda value: value > 0))],
            ["日均收益率", cls._pct(cls._mean(index_values)), cls._pct(cls._mean(strategy_values))],
            ["日收益率标准差", cls._pct(cls._std(index_values)), cls._pct(cls._std(strategy_values))],
            ["最大单日收益", cls._pct(max(index_values, default=0)), cls._pct(max(strategy_values, default=0))],
            ["最大单日亏损", cls._pct(min(index_values, default=0)), cls._pct(min(strategy_values, default=0))],
            ["日收益率偏度", cls._decimal(cls._skew(index_values)), cls._decimal(cls._skew(strategy_values))],
            ["日收益率峰度", cls._decimal(cls._kurtosis(index_values)), cls._decimal(cls._kurtosis(strategy_values))],
        ]

    @classmethod
    def _profit_loss_rows(cls, index_values: list[float], strategy_values: list[float]) -> list[list[str]]:
        """处理_profit_loss_rows相关逻辑。"""
        def values_above(values: list[float]) -> list[float]:
            """处理values_above相关逻辑。"""
            return [value for value in values if value > 0]

        def values_below(values: list[float]) -> list[float]:
            """处理values_below相关逻辑。"""
            return [value for value in values if value < 0]

        index_gains, strategy_gains = values_above(index_values), values_above(strategy_values)
        index_losses, strategy_losses = values_below(index_values), values_below(strategy_values)
        return [
            ["平均盈利日收益", cls._pct(cls._mean(index_gains)), cls._pct(cls._mean(strategy_gains))],
            ["平均亏损日收益", cls._pct(cls._mean(index_losses)), cls._pct(cls._mean(strategy_losses))],
            ["盈亏比(平均盈利/平均亏损)", cls._decimal(cls._ratio_by_abs(cls._mean(index_gains), cls._mean(index_losses))), cls._decimal(cls._ratio_by_abs(cls._mean(strategy_gains), cls._mean(strategy_losses)))],
            ["单笔最大盈利/最大亏损", cls._decimal(cls._ratio_by_abs(max(index_gains, default=0), min(index_losses, default=0))), cls._decimal(cls._ratio_by_abs(max(strategy_gains, default=0), min(strategy_losses, default=0)))],
        ]

    @classmethod
    def _distribution_rows(cls, labels: list[str], index_distribution: list[tuple[int, float]], strategy_distribution: list[tuple[int, float]]) -> list[list[str]]:
        """处理_distribution_rows相关逻辑。"""
        return [[label, cls._count_percent(*index_distribution[index]), cls._count_percent(*strategy_distribution[index])] for index, label in enumerate(labels)]

    @classmethod
    def _single_distribution_rows(cls, labels: list[str], distribution: list[tuple[int, float]]) -> list[list[str]]:
        """处理_single_distribution_rows相关逻辑。"""
        return [[label, cls._count_percent(*distribution[index])] for index, label in enumerate(labels)]

    @classmethod
    def _excess_summary_rows(cls, cumulative: float, annualized: float, values: list[float]) -> list[list[str]]:
        """处理_excess_summary_rows相关逻辑。"""
        return [
            ["累计超额(策略-指数)", cls._pct(cumulative)],
            ["年化超额", cls._pct(annualized)],
            ["月超额收益均值", cls._pct(cls._mean(values))],
            ["月超额收益中位数", cls._pct(cls._median(values))],
            ["月超额收益标准差", cls._pct(cls._std(values))],
            ["月超额胜率(>0)", cls._pct(cls._ratio(values, lambda value: value > 0))],
            ["最大单月超额", cls._pct(max(values, default=0))],
        ]

    @classmethod
    def _excess_rolling_row(cls, values: list[float], months: int) -> list[str]:
        """处理_excess_rolling_row相关逻辑。"""
        rolling = [mean(values[index:index + months]) for index in range(max(0, len(values) - months + 1))]
        return [f"{months}个月", cls._pct(cls._mean(rolling)), cls._pct(cls._ratio(rolling, lambda value: value > 0))] if rolling else [f"{months}个月", "-", "-"]

    @classmethod
    def _market_phase_rows(cls, pairs: list[tuple[str, float, float]]) -> list[list[str]]:
        """处理_market_phase_rows相关逻辑。"""
        index_values = [item[1] for item in pairs]
        strategy_values = [item[2] for item in pairs]
        excess_values = [strategy - index for index, strategy in zip(index_values, strategy_values)]
        return [
            ["阶段月数", cls._integer(len(pairs)), cls._integer(len(pairs)), "-"],
            ["平均收益", cls._pct(cls._mean(index_values)), cls._pct(cls._mean(strategy_values)), cls._pct(cls._mean(excess_values))],
            ["中位收益", cls._pct(cls._median(index_values)), cls._pct(cls._median(strategy_values)), cls._pct(cls._median(excess_values))],
            ["策略跑赢次数", "-", cls._integer(sum(strategy > index for index, strategy in zip(index_values, strategy_values))), cls._pct(cls._ratio(excess_values, lambda value: value > 0))],
        ]

    @classmethod
    def _extreme_day_rows(cls, index_values: list[float], strategy_values: list[float]) -> list[list[str]]:
        """处理_extreme_day_rows相关逻辑。"""
        return [
            ["最大单日涨幅", cls._pct(max(index_values, default=0)), cls._pct(max(strategy_values, default=0))],
            ["最大单日跌幅", cls._pct(min(index_values, default=0)), cls._pct(min(strategy_values, default=0))],
            ["涨幅>2%的天数", cls._integer(sum(value > 0.02 for value in index_values)), cls._integer(sum(value > 0.02 for value in strategy_values))],
            ["跌幅>2%的天数", cls._integer(sum(value < -0.02 for value in index_values)), cls._integer(sum(value < -0.02 for value in strategy_values))],
            ["涨跌比(涨>2%/跌>2%)", cls._decimal(cls._ratio_by_abs(sum(value > 0.02 for value in index_values), sum(value < -0.02 for value in index_values))), cls._decimal(cls._ratio_by_abs(sum(value > 0.02 for value in strategy_values), sum(value < -0.02 for value in strategy_values)))],
        ]

    @classmethod
    def _capital_curve_rows(cls, index_values: list[float], strategy_values: list[float]) -> list[list[str]]:
        """处理_capital_curve_rows相关逻辑。"""
        index_highs = cls._new_high_positions(index_values)
        strategy_highs = cls._new_high_positions(strategy_values)
        index_consecutive = cls._consecutive_changes(index_values)
        strategy_consecutive = cls._consecutive_changes(strategy_values)
        return [
            ["初始净值", cls._decimal(index_values[0] if index_values else 1, 4), cls._decimal(strategy_values[0] if strategy_values else 1, 4)],
            ["期末净值", cls._decimal(index_values[-1] if index_values else 1, 4), cls._decimal(strategy_values[-1] if strategy_values else 1, 4)],
            ["净值创新高次数", cls._integer(len(index_highs)), cls._integer(len(strategy_highs))],
            ["净值创新高频率", cls._pct(len(index_highs) / len(index_values) if index_values else 0), cls._pct(len(strategy_highs) / len(strategy_values) if strategy_values else 0)],
            ["最大涨幅区间(连续)", cls._pct(index_consecutive["max_gain"]), cls._pct(strategy_consecutive["max_gain"])],
            ["最大跌幅区间(连续)", cls._pct(index_consecutive["max_loss"]), cls._pct(strategy_consecutive["max_loss"])],
            ["创新高平均间隔(天)", cls._decimal(cls._average_interval(index_highs), 1), cls._decimal(cls._average_interval(strategy_highs), 1)],
        ]

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

    @classmethod
    def _information_ratio(cls, index_values: list[float], strategy_values: list[float]) -> str:
        """处理_information_ratio相关逻辑。"""
        excess = [strategy - index for index, strategy in zip(index_values, strategy_values)]
        return cls._decimal(cls._mean(excess) / cls._std(excess) * math.sqrt(252) if cls._std(excess) else 0.0)

    @classmethod
    def _calmar_from_returns(cls, annualized_return: Any, drawdown: Any) -> str:
        """处理_calmar_from_returns相关逻辑。"""
        return cls._decimal(cls._num(annualized_return) / cls._num(drawdown) if cls._num(drawdown) else 0.0)

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

    @staticmethod
    def _count_percent(count: int, ratio: float) -> str:
        """处理_count_percent相关逻辑。"""
        return f"{count} / {ratio:.1%}"

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

    def _year_all(self, items: Any, field: str) -> Any:
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
        values = [cls._num(item[field]) for item in items or [] if isinstance(item, dict) and item.get(field) is not None]
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
        annual_index = {str(item.get("year")): self._num(item.get("annual_return")) for item in metrics.get("index_returns_rate") or [] if isinstance(item, dict)}
        annual_start = {str(item.get("year")): self._num(item.get("annual_return")) for item in metrics.get("start_returns_rate") or [] if isinstance(item, dict)}
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
            "monthly_excess_returns": [self._num(item.get("monthly_excess_return_diff")) for item in metrics.get("monthly_excess_returns") or [] if isinstance(item, dict)],
            "annual_returns": {"years": years, "index": [annual_index.get(year, 0) for year in years], "strategy": [annual_start.get(year, 0) for year in years]},
        }

    @classmethod
    def _compound_return(cls, frame: Any, column: str) -> float:
        """处理_compound_return相关逻辑。"""
        values = frame[column].tolist() if column in frame else []
        return cls._num(values[-1]) if values else 0.0


strategy_backtest_report_service = StrategyBacktestReportService()
