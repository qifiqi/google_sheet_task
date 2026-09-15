"""策略回测 Word 报告适配服务。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.repositories import task_result_repository
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.strategy_backtest_report_charts import generate_correlation_heatmap, generate_report_charts
from app.schemas.backtest import StrategyBacktestReportSchema
from app.services.word_export_template import generate_word_document
from app.utils.backtest_report_metadata import get_backtest_model_version
from app.utils.return_series import parse_return_series_fields
from app.utils.value_parser import parse_date, parse_float, parse_int
from app.services.performance_analysis.portfolio_combiner import (
    combine_product_returns,
    cumulative_to_daily,
    daily_to_cumulative,
    normalize_weight,
)
from app.services.performance_analysis.return_correlation import aligned_daily_returns, pairwise_correlation_matrix
from app.services.kline_service import KlineService
from app.utils.logger import get_logger
from app.utils.etf_total_assets import get_etf_total_assets_detail
from app.utils.market import normalize_market_type
from app.utils.number_format import abbreviate_number

logger = get_logger(__name__)

# 报告用 K 线服务懒加载：构造轻量，外部数据源 API 在首次取数时才创建。
_kline_service: KlineService | None = None


def _report_kline_service() -> KlineService:
    global _kline_service
    if _kline_service is None:
        _kline_service = KlineService()
    return _kline_service


@dataclass
class _BenchmarkRun:
    """一次 V1 引擎运行：code=None 表示默认组合基准；label 为报告指数列头文案。"""

    code: str | None
    weight: Decimal
    label: str
    result: Any  # MetricsV1Result


class StrategyBacktestReportService:
    """将 V1 指标结果适配为通用 Word JSON。"""

    def generate_word(self, request: StrategyBacktestReportSchema) -> tuple[str, BytesIO]:
        """渲染 Word 报告；请求校验由 StrategyBacktestReportSchema 在请求边界完成。"""

        # 每个基准各运行一次 V1 引擎（未选指数时为默认组合基准）：
        # 策略列与基准选择无关，各次运行完全一致；指数/超额列按各自运行结果取值。
        runs = self._build_benchmark_runs(request)
        result = runs[0].result
        if not result.metrics or result.index_df.empty:
            raise ValueError("收益数据无法生成回测报告")

        # 把 DataFrame 和指标字典转换成通用 Word JSON；图表按基准序列循环渲染。
        chart_data = self._build_chart_data(runs)
        dates = self._dates(result.index_df)
        first_date = dates[0].strftime("%Y-%m-%d")
        last_date = dates[-1].strftime("%Y-%m-%d")
        correlation = self._correlation_matrix(request, result)
        with TemporaryDirectory(prefix="strategy_backtest_report_") as temp_dir:
            # 图片只在临时目录中存在，DOCX 保存时会将图片内容嵌入文件。
            chart_paths = generate_report_charts(chart_data, temp_dir)
            correlation_image = None
            if correlation:
                heatmap_path = Path(temp_dir) / "权重相关系数热力图.png"
                generate_correlation_heatmap(correlation["labels"], correlation["matrix"], heatmap_path)
                correlation_image = {
                    "type": "image",
                    "title": "权重日涨跌幅相关系数",
                    "path": str(heatmap_path),
                    "caption": f"各权重日涨跌幅的 Pearson 相关系数（数据区间 {first_date} 至 {last_date}）",
                }
            report_data = self._build_report_data(request, runs, correlation_image)
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
                *[{"type": "paragraph", "text": text} for text in self._conclusion(runs, first_date, last_date)],
            ])
            output_path = Path(temp_dir) / "report.docx"
            generate_word_document(report_data, output_path)
            raw = output_path.read_bytes()

        filename = request.filename or self._default_filename(request)
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        return filename, BytesIO(raw)

    @staticmethod
    def _is_zero_weight_product(product: dict[str, Any]) -> bool:
        """比例明确为 0 的产品不参与命名、组合与权重分配；缺失/非法比例视为参与。"""
        raw = product.get("ratio", product.get("weight"))
        text = str(raw if raw is not None else "").strip()
        if not text:
            return False
        try:
            return normalize_weight(text) == 0
        except ValueError:
            return False

    @classmethod
    def _active_report_products(cls, products: Any) -> list[dict[str, Any]]:
        """过滤掉比例为 0 的产品；全部为 0 时返回原列表，避免报告内容为空。"""
        if not isinstance(products, list):
            return []
        active = [
            product for product in products
            if isinstance(product, dict) and not cls._is_zero_weight_product(product)
        ]
        return active or [
            product for product in products if isinstance(product, dict)
        ]

    def _default_filename(self, request: StrategyBacktestReportSchema) -> str:
        """按报告类型、产品代码和生成时间构造默认下载文件名。

        比例为 0 的产品不参与代码拼接；有效产品只剩 1 个时前缀按 RPT-S 输出。
        """
        products = self._active_report_products(request.products)
        report_type = (
            "RPT-S" if request.report_type == "RPT-M" and len(products) == 1
            else request.report_type
        )
        stock_codes = [
            str(product.get("stock_code") or "").strip().upper()
            for product in products
            if str(product.get("stock_code") or "").strip()
        ]
        suffix = "-".join([*stock_codes, datetime.now().strftime("%Y%m%d%H%M%S")])
        return f"{report_type}-{suffix}" if suffix else f"{report_type}-{datetime.now():%Y%m%d%H%M%S}"

    @staticmethod
    def _benchmark_entries(payload: StrategyBacktestReportSchema) -> list[tuple[str, Decimal]]:
        """报告采用的基准条目（代码, 权重小数）；空列表表示默认组合基准。"""
        return [
            (str(item.stock_code or "").strip(), Decimal(str(item.ratio)) / Decimal("100"))
            for item in (payload.index_benchmarks or [])
        ]

    @staticmethod
    def _benchmark_codes(payload: StrategyBacktestReportSchema) -> set[str]:
        """基准代码集合（权重表/标签的 "(指数)" 后缀标记用）。"""
        return {code for code, _weight in StrategyBacktestReportService._benchmark_entries(payload)}

    def _build_benchmark_runs(self, request: StrategyBacktestReportSchema) -> list[_BenchmarkRun]:
        """组合收益 + 各基准注入后逐次运行 V1 引擎；未选指数时为单个默认组合基准。

        统一日期轴 = 组合共同交易日 ∩ 全部基准序列交易日，整份报告（表格/图表/
        元数据）共用同一条轴；轴不足 2 个交易日由引擎侧统一报错。
        指数注入仅用于 RPT-M；单品/V2 来源保持顶层三选一解析。
        include_composite_benchmark 开关决定组合指数是否与自定义指数并列成列
        （默认包含，组合列头固定为"指数"）；关闭且未选自定义指数时仍回落组合，
        保证报告恒有基准。
        """
        runtime = self._runtime_params(request.runtime_params)
        if request.report_type == "RPT-M":
            data = self._combine_product_returns(request)
        else:
            data = self._resolve_source_returns({
                "returns": request.returns,
                "task_id": request.task_id,
                "return_series_id": request.return_series_id,
                "google_sheet_url": request.google_sheet_url,
                "spreadsheet_id": request.spreadsheet_id,
                "google_sheet_name": request.google_sheet_name,
            })
        rows_by_date = {row["date"]: row for row in data}
        entries = self._benchmark_entries(request) if request.report_type == "RPT-M" else []
        benchmark_series = [
            (code, weight, self._index_series_by_date(self._find_product(request, code), weight))
            for code, weight in entries
        ]
        include_composite = (
            bool(getattr(request, "include_composite_benchmark", True)) or not entries
        )
        if benchmark_series:
            # 统一日期轴：剔除任一基准缺失的交易日，保证各次运行的策略指标严格一致。
            axis = [
                row["date"] for row in data
                if all(row["date"] in index_map for _, _, index_map in benchmark_series)
            ]
        else:
            axis = [row["date"] for row in data]

        runs: list[_BenchmarkRun] = []
        if include_composite:
            runs.append(_BenchmarkRun(
                code=None,
                weight=Decimal("1"),
                label="指数",
                result=performance_analyzer.get_calculate_metrics_v1_with_dataframes(
                    [rows_by_date[date] for date in axis], runtime),
            ))
        labels = self._benchmark_labels(entries)
        if include_composite and benchmark_series:
            # 组合指数列头固定为"指数"；自定义基准与之撞名时改用 指数(代码) 消歧。
            labels = [
                f"指数({code})" if label == "指数" else label
                for (code, _weight), label in zip(entries, labels)
            ]
        for (code, weight, index_map), label in zip(benchmark_series, labels):
            rows = [
                {"date": date, "index_return": index_map[date],
                 "start_return": rows_by_date[date]["start_return"]}
                for date in axis
            ]
            runs.append(_BenchmarkRun(
                code=code,
                weight=weight,
                label=label,
                result=performance_analyzer.get_calculate_metrics_v1_with_dataframes(rows, runtime),
            ))
        return runs

    @staticmethod
    def _weight_percent_text(weight: Decimal) -> str:
        """权重百分比展示文本；normalize 去尾零后转定点，避免 50.0 / 5E+1。"""
        return format((Decimal(str(weight)) * 100).normalize(), "f")

    @classmethod
    def _benchmark_labels(cls, entries: list[tuple[str, Decimal]]) -> list[str]:
        """基准列头：满配单条保持"指数"；同股只展示比例；异股展示 代码 比例%。"""
        same_code = len({code for code, _weight in entries}) <= 1
        labels = []
        for code, weight in entries:
            if len(entries) == 1 and weight == 1:
                labels.append("指数")
            elif same_code:
                labels.append(f"指数({cls._weight_percent_text(weight)}%)")
            else:
                labels.append(f"指数({code} {cls._weight_percent_text(weight)}%)")
        return labels

    @staticmethod
    def _find_product(request: StrategyBacktestReportSchema, code: str) -> dict[str, Any]:
        """按代码定位基准产品；Schema 已校验唯一命中，此处兜底防御。"""
        product = next(
            (item for item in request.products
             if str(item.get("stock_code") or "").strip() == code),
            None,
        )
        if product is None:
            raise ValueError(f"指数代码 {code} 不在产品列表中")
        return product

    @staticmethod
    def _cumulative_index_by_date(product: dict[str, Any]) -> dict[str, Any]:
        """产品收益序列的 date → index_return（标的自身基准列）映射。"""
        index_by_date: dict[str, Any] = {}
        for row in product.get("returns") or []:
            parsed = parse_date(row.get("date") or row.get("stock_date"))
            if parsed is not None:
                index_by_date[parsed.isoformat()] = row.get("index_return", 0)
        return index_by_date

    @staticmethod
    def _index_series_by_date(product: dict[str, Any], weight: Decimal) -> dict[str, Any]:
        """基准序列映射：权重 1 直接取产品指数列，否则按"比例×日收益+现金"缩放。

        缩放口径与组合器一致（累计→日→乘权重→再复利）。
        """
        if weight == 1:
            return StrategyBacktestReportService._cumulative_index_by_date(product)
        scaled = daily_to_cumulative([
            {"date": row["date"], "index_return": float(weight) * row["index_return"], "start_return": 0.0}
            for row in cumulative_to_daily(product.get("returns") or [])
        ])
        return {row["date"]: row["index_return"] for row in scaled}

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
        rows, _sheet_result, _sheet_df = performance_analyzer.get_google_sheet_data(
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
        request: StrategyBacktestReportSchema,

    ) -> list[dict[str, Any]]:
        """将多产品组合委托给统一组合器；比例为 0 的产品不参与组合。"""
        products = request.products
        weighting_mode = request.weighting_mode or "daily_compound"
        inputs = [
            {
                "returns": self._resolve_source_returns(product),
                "ratio": product.get("ratio", product.get("weight")),
            }
            for product in self._active_report_products(products)
        ]
        return combine_product_returns(inputs, weighting_mode=weighting_mode)

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
    def _runtime_params(raw: Any) -> MetricsRuntimeParamsDTO:
        """处理_runtime_params相关逻辑。"""
        return MetricsRuntimeParamsDTO.from_raw(raw)

    def _build_report_data(
        self,
        payload: StrategyBacktestReportSchema,
        runs: list[_BenchmarkRun],
        correlation_image: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将回测指标转换为通用 Word JSON 协议。"""
        report_type = payload.report_type
        if report_type not in {"RPT-S", "RPT-M"}:
            raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")
        result = runs[0].result
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
        amount_texts = self._weight_metric_texts(payload, first_date, last_date)
        asset_texts, etf_flags = self._etf_total_assets_texts(payload)
        # 全部为个股（资产值均来自总市值回退或缺失、无任何 ETF 资产值）时，列头按净资产表述。
        assets_header = "净资产" if asset_texts and not any(etf_flags.values()) else "ETF资产总数"
        blocks: list[dict[str, Any]] = [
            {"type": "metadata", "items": metadata},
            *self._weight_allocation_blocks(payload, report_type, amount_texts, asset_texts, assets_header),
        ]
        # 相关系数热力图紧跟权重表之后、分析图表区之前。
        if correlation_image is not None:
            blocks.append(correlation_image)
        sections = self._sections(runs)
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
    def _weight_allocation_blocks(
        payload: StrategyBacktestReportSchema,
        report_type: str,
        amounts: dict[str, str] | None = None,
        assets: dict[str, str] | None = None,
        assets_header: str = "ETF资产总数",
    ) -> list[dict[str, Any]]:
        """构造权重表格块：策略权重与指数权重各一张表。

        策略表 = 有效产品按配置比例；指数表 = 指数基准自身的比例权重
        （如 QQQ 100%、SOXX 30%），两表并列展示便于区分策略持仓与指数
        构成，未选指数基准时省略指数表。平均成交额/资产总数按代码标签
        回填；指数表代码列不再重复 "(指数)" 后缀。
        """
        amount_texts = amounts or {}
        asset_texts = assets or {}
        columns = ["股票代码", "股票名", "权重", "平均成交额", assets_header]
        active = StrategyBacktestReportService._active_report_products(payload.products)
        strategy_rows = []
        if isinstance(active, list):
            for product in active:
                if not isinstance(product, dict):
                    continue
                code = str(product.get("stock_code") or product.get("product_name") or "未命名")
                strategy_rows.append([
                    code,
                    str(product.get("product_name") or ""),
                    StrategyBacktestReportService._weight_text(product, report_type),
                    amount_texts.get(code, "-"),
                    asset_texts.get(code, "-"),
                ])
        if not strategy_rows and report_type == "RPT-S":
            strategy_rows = [["单品", "", "100.00%", "-", "-"]]
        blocks: list[dict[str, Any]] = [{
            "type": "table", "title": "策略权重", "columns": columns,
            "rows": strategy_rows or [["", "", "", "-", "-"]],
        }]

        name_by_code: dict[str, str] = {}
        for product in payload.products if isinstance(payload.products, list) else []:
            if isinstance(product, dict):
                name_by_code.setdefault(str(product.get("stock_code") or "").strip(),
                                        str(product.get("product_name") or ""))
        index_rows = []
        for code, weight in StrategyBacktestReportService._benchmark_entries(payload):
            label = f"{code} (指数)"
            index_rows.append([
                code,
                name_by_code.get(code, ""),
                f"{StrategyBacktestReportService._weight_percent_text(weight)}%",
                amount_texts.get(label, "-"),
                asset_texts.get(label, "-"),
            ])
        if index_rows:
            blocks.append({
                "type": "table", "title": "指数权重", "columns": columns, "rows": index_rows,
            })
        return blocks

    @staticmethod
    def _weight_text(product: dict[str, Any], report_type: str) -> str:
        """权重列展示文本；单品报告缺省 100.00%，纯数值自动补百分号。"""
        weight = str(product.get("ratio") or product.get("weight") or "").strip()
        if report_type == "RPT-S" and not weight:
            weight = "100.00%"
        return weight if not weight or weight.endswith("%") else f"{weight}%"

    def _correlation_matrix(self, payload: StrategyBacktestReportSchema, result: Any) -> dict[str, Any] | None:
        """构造相关系数热力图数据；有效对齐产品不足 2 个时不输出。

        日涨跌幅还原与 Pearson 计算统一走 performance_analysis
        （口径与组合收益一致），本方法只负责产品筛选与标签组装。
        """
        products = self._active_report_products(payload.products)
        if not products:
            return None
        dates = [value.strftime("%Y-%m-%d") for value in self._dates(result.index_df)]
        aligned = {}
        for index, product in enumerate(products):
            series = aligned_daily_returns(product.get("returns"), dates)
            if series is not None:
                aligned[index] = series
        indexes = sorted(aligned)
        if len(indexes) < 2:
            return None
        return {
            "labels": [self._product_code_label(payload, products[index]) for index in indexes],
            "matrix": pairwise_correlation_matrix([aligned[index] for index in indexes]),
        }

    def _weight_metric_texts(
        self,
        payload: StrategyBacktestReportSchema,
        first_date: str,
        last_date: str,
    ) -> dict[str, str]:
        """单次 K 线取数产出权重表的平均成交额文本映射。

        同一标的只取数一次（同码的策略行/指数行/多比例行共享结果），
        指数行标签为 "代码 (指数)"。
        """
        amount_texts: dict[str, str] = {}
        kline_texts: dict[str, str] = {}

        def amount_text_for(code: str, product: dict[str, Any]) -> str:
            if code not in kline_texts:
                kline_texts[code] = self._kline_average_amount_text(product, first_date, last_date)
            return kline_texts[code]

        for product in self._active_report_products(payload.products):
            if not isinstance(product, dict):
                continue
            code = str(product.get("stock_code") or product.get("product_name") or "").strip()
            if not code or code in kline_texts:
                continue
            amount_texts[code] = kline_texts[code] = self._kline_average_amount_text(
                product, first_date, last_date,
            )
        for code, _weight in self._benchmark_entries(payload):
            label = f"{code} (指数)"
            if label in amount_texts:
                continue
            if code in kline_texts:
                amount_texts[label] = kline_texts[code]
                continue
            try:
                product = self._find_product(payload, code)
                amount_texts[label] = amount_text_for(code, product)
            except ValueError:
                amount_texts[label] = "-"
        return amount_texts

    def _kline_average_amount_text(
        self,
        product: dict[str, Any],
        first_date: str,
        last_date: str,
    ) -> str:
        """单次 K 线取数计算权重表平均成交额展示文本；失败降级 "-"。

        K 线行缺成交额（如 Yahoo 源未返回）时按 成交量×收盘价 逐行估算。
        market_type 取任务配置透传值并作为 get_kline_data 的推断缺省：
        标准代码后缀推断优先，存储值兜底，避免港股等纯数字代码被误判为 A 股。
        """
        stock_code = str(product.get("stock_code") or "").strip()
        if not stock_code:
            return "-"
        try:
            market_type = str(product.get("market_type") or "").strip() or "cn"
            calendar_days = max(1, (parse_date(last_date) - parse_date(first_date)).days)
            trading_days_per_year = 250 if normalize_market_type(market_type) == "cn" else 252
            limit = max(300, math.ceil(calendar_days * trading_days_per_year / 365.25) + 120)
            klines = _report_kline_service().get_kline_data(
                stock_code,
                market_type,
                limit,
                start_date=first_date,
                end_date=last_date,
                exchange_market=product.get("exchange_market"),
            )
            rows = klines or []
            amount_average = self._average_field(rows, "amount")
            if not amount_average:
                amount_average = self._average_volume_times_close(rows)
            return abbreviate_number(amount_average) or "-"
        except Exception:
            logger.warning("报告平均成交额获取失败: %s", stock_code, exc_info=True)
            return "-"

    @staticmethod
    def _average_field(rows: list[dict[str, Any]], field: str) -> float | None:
        """K 线行指定列的算术平均；全部缺失返回 None。"""
        values = [
            StrategyBacktestReportService._num(row.get(field))
            for row in rows or []
            if row.get(field) is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _average_volume_times_close(rows: list[dict[str, Any]]) -> float | None:
        """成交额缺失时的行级估算均值：Σ(成交量×收盘价)/N。"""
        values = [
            StrategyBacktestReportService._num(row.get("volume"))
            * StrategyBacktestReportService._num(row.get("close"))
            for row in rows or []
            if row.get("volume") is not None and row.get("close") is not None
        ]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _etf_total_assets_detail(product: dict[str, Any]) -> tuple[str, bool | None]:
        """ETF 资产总数展示文本与是否 ETF 标记；取不到显示 "-"（按个股对待）。

        数值按中文习惯缩写（亿/万），避免长数字撑爆表格列宽；
        是否 ETF 取自数据来源（totalAssets=ETF、总市值回退=个股）。
        """
        value, is_etf = get_etf_total_assets_detail(
            product.get("stock_code"),
            product.get("market_type"),
            product.get("exchange_market"),
        )
        return abbreviate_number(value) or "-", is_etf

    def _etf_total_assets_texts(
        self, payload: StrategyBacktestReportSchema,
    ) -> tuple[dict[str, str], dict[str, bool | None]]:
        """按权重表行标签取各标的资产展示文本与是否 ETF 标记（策略行 + 指数基准行）。"""
        texts: dict[str, str] = {}
        flags: dict[str, bool | None] = {}
        for product in self._active_report_products(payload.products):
            if not isinstance(product, dict):
                continue
            code = str(product.get("stock_code") or product.get("product_name") or "").strip()
            if not code or code in texts:
                continue
            texts[code], flags[code] = self._etf_total_assets_detail(product)
        for code, _weight in self._benchmark_entries(payload):
            label = f"{code} (指数)"
            if label in texts:
                continue
            if code in texts:
                texts[label], flags[label] = texts[code], flags[code]
                continue
            try:
                product = self._find_product(payload, code)
                texts[label], flags[label] = self._etf_total_assets_detail(product)
            except ValueError:
                texts[label], flags[label] = "-", None
        return texts, flags

    @staticmethod
    def _product_code_label(payload: StrategyBacktestReportSchema, product: dict[str, Any]) -> str:
        """代码列展示，与策略权重表一致；选中基准代码追加 "(指数)" 后缀。"""
        code = str(product.get("stock_code") or product.get("product_name") or "未命名")
        if code in StrategyBacktestReportService._benchmark_codes(payload):
            return f"{code} (指数)"
        return code

    def _sections(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """按模板顺序合并各表格 JSON。"""
        return [
            {"title": "一、收益类指标", "subsections": self._return_section(runs)},
            {"title": "二、风险类指标", "subsections": self._risk_section(runs)},
            {"title": "三、风险调整收益指标", "subsections": self._risk_adjusted_section(runs)},
            {"title": "四、月度收益分布", "subsections": self._monthly_section(runs)},
            {"title": "五、日度收益分布", "subsections": self._daily_section(runs)},
            {"title": "六、超额收益分析", "subsections": self._excess_section(runs)},
            {"title": "七、极端行情表现", "subsections": self._extreme_section(runs)},
            {"title": "八、资金曲线特征", "subsections": self._capital_curve_section(runs)},
        ]

    @staticmethod
    def _run_metrics_list(runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """各次引擎运行的指标字典；约定首元素为策略列取值来源。"""
        return [run.result.metrics for run in runs]

    def _benchmark_headers(self, runs: list[_BenchmarkRun]) -> list[str]:
        """指数列头：单基准保持现状文案"指数"，多基准用 指数(代码) 自描述。"""
        return [run.label for run in runs]

    def _benchmark_tag(self, runs: list[_BenchmarkRun], run: _BenchmarkRun) -> str:
        """多基准场景的区分标记：取指数列头"指数(...)"括号内的内容。

        与指数列头规则严格对称（同股只展示比例，异股展示 代码 比例%），
        供超额/胜率/月度超额等派生列头统一消费；组合指数列头为无标记的
        "指数"，此处返回空串，派生列头随之省略括号标记。
        """
        if not run.label.startswith("指数"):
            return f"{run.code} {self._weight_percent_text(run.weight)}%"
        tag = run.label[len("指数"):].strip()
        return tag[1:-1] if tag.startswith("(") and tag.endswith(")") else ""

    def _tagged_header(self, prefix: str, runs: list[_BenchmarkRun], run: _BenchmarkRun) -> str:
        """前缀 + 区分标记的派生列头；标记为空（组合指数）时仅返回前缀。"""
        tag = self._benchmark_tag(runs, run)
        return f"{prefix}({tag})" if tag else prefix

    def _excess_headers(self, runs: list[_BenchmarkRun]) -> list[str]:
        """超额列头：单基准保持现状文案"超额(策略-指数)"；多基准同股只展示比例。"""
        if len(runs) <= 1:
            return ["超额(策略-指数)"]
        return [self._tagged_header("超额", runs, run) for run in runs]

    def _return_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造一、收益类指标章节的全部表格；数值统一取自 V1 指标结果。

        指数/超额列按基准循环展开；超额列为两个 V1 数值的展示减法（策略-指数），
        不含业务口径计算。
        """
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        benchmark_headers = self._benchmark_headers(runs)
        excess_headers = self._excess_headers(runs)
        index_cumulatives = [self._num(m.get("index_cumulative_return")) for m in metrics_list]
        excess_cumulatives = [self._num(m.get("excess_cumulative_return")) for m in metrics_list]
        strategy_cumulative = self._num(strategy.get("start_cumulative_return"))
        index_annualized = [self._year_all(m.get("index_annualized_rates"), "annualized_return") for m in metrics_list]
        strategy_annualized = self._year_all(strategy.get("start_annualized_rates"), "annualized_return")
        index_volatilities = [self._year_all(m.get("index_sharpe_ratios"), "annual_std_dev") for m in metrics_list]
        strategy_volatility = self._year_all(strategy.get("start_sharpe_ratios"), "annual_std_dev")
        index_returns_list = [self._metric_by_year(m.get("index_returns_rate"), "annual_return") for m in metrics_list]
        strategy_returns = self._metric_by_year(strategy.get("start_returns_rate"), "annual_return")
        years = sorted(set().union(*(set(item) for item in index_returns_list)) | set(strategy_returns))
        rolling_rows = [
            self._rolling_row(runs, months)
            for months in (3, 6, 12)
        ]
        rolling_index_headers = [f"{run.label}平均收益" for run in runs] if len(runs) > 1 else ["指数平均收益"]
        rolling_win_headers = ([f"策略胜率(跑赢{self._benchmark_tag(runs, run) or '组合'})" for run in runs]
                               if len(runs) > 1 else ["策略胜率(跑赢指数)"])
        return [
            {"title": "1.1 核心收益", "table": self._table(
                ["指标", *benchmark_headers, "策略", *excess_headers], [
                    ["累计回报率", *[self._pct(value) for value in index_cumulatives],
                     self._pct(strategy_cumulative),
                     *[self._pct(value) for value in excess_cumulatives]],
                    ["年化收益率", *[self._pct(value) for value in index_annualized],
                     self._pct(strategy_annualized),
                     *[self._pct(self._num(strategy_annualized) - self._num(value)) for value in index_annualized]],
                    ["年化波动率", *[self._pct(value) for value in index_volatilities],
                     self._pct(strategy_volatility),
                     *[self._pct(self._num(strategy_volatility) - self._num(value)) for value in index_volatilities]],
                ])},
            {"title": "1.2 分年度收益率", "table": self._table(
                ["年份", *benchmark_headers, "策略", *excess_headers], [
                    [year,
                     *[self._pct(index_returns.get(year)) for index_returns in index_returns_list],
                     self._pct(strategy_returns.get(year)),
                     *[self._pct(self._num(strategy_returns.get(year)) - self._num(index_returns.get(year)))
                       for index_returns in index_returns_list]]
                    for year in years
                ])},
            {"title": "1.3 滚动收益（月度窗口）", "table": self._table(
                ["滚动周期", *rolling_index_headers, "策略平均收益", *rolling_win_headers], rolling_rows)},
        ]

    @classmethod
    def _rolling_row(cls, runs: list[_BenchmarkRun], months: int) -> list[str]:
        """直接消费 V1 滚动聚合导出；数据不足 5 年时展示 V1 返回的 reason。"""
        label = f"{months}个月滚动"
        metrics_list = cls._run_metrics_list(runs)
        dashes = ["-"] * (len(runs) * 2 + 1)
        reason = metrics_list[0].get(f"rolling_return_{months}_reason")
        if reason:
            return [f"{label}（{reason}）", *dashes]
        index_avgs = [m.get(f"index_rolling_return_{months}_avg_return") for m in metrics_list]
        start_avg = metrics_list[0].get(f"start_rolling_return_{months}_avg_return")
        win_rates = [m.get(f"rolling_return_{months}_win_rate") for m in metrics_list]
        if any(value is None for value in index_avgs) or start_avg is None or any(value is None for value in win_rates):
            return [label, *dashes]
        return [label, *[cls._pct(value) for value in index_avgs], cls._pct(start_avg),
                *[cls._pct(value) for value in win_rates]]

    def _risk_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造二、风险类指标章节的全部表格；数值统一取自 V1 指标结果。

        2.2 超额回撤列为两个 V1 回撤值的展示减法（指数-策略，口径见 metrics TODO）。
        """
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        benchmark_headers = self._benchmark_headers(runs)
        index_drawdowns = [self._total_metric(m.get("index_maximum_drawdown"), "drawdown") for m in metrics_list]
        strategy_drawdown = self._total_metric(strategy.get("start_maximum_drawdown"), "drawdown")
        index_years_list = [
            self._metric_by_year((m.get("index_maximum_drawdown") or {}).get("year_maximum_drawdown"), "drawdown")
            for m in metrics_list
        ]
        strategy_years = self._metric_by_year(
            (strategy.get("start_maximum_drawdown") or {}).get("year_maximum_drawdown"), "drawdown")
        years = sorted(set().union(*(set(item) for item in index_years_list)) | set(strategy_years))
        drawdown_rows = [
            [year,
             *[self._pct(-self._num(index_years.get(year))) for index_years in index_years_list],
             self._pct(-self._num(strategy_years.get(year))),
             *[self._pct(self._num(index_years.get(year)) - self._num(strategy_years.get(year)))
               for index_years in index_years_list]]
            for year in years
        ]
        daily_drawdown_threshold = strategy.get("daily_drawdown_threshold")
        if daily_drawdown_threshold is None:
            daily_drawdown_threshold = MetricsRuntimeParamsDTO().daily_drawdown_threshold
        drawdown_excess_headers = ([self._tagged_header("超额回撤", runs, run) for run in runs]
                                   if len(runs) > 1 else ["超额回撤(策略-指数)"])
        return [
            {"title": "2.1 回撤指标", "table": self._table(
                ["指标", *benchmark_headers, "策略"], [
                    ["最大回撤(MDD)", *[self._pct(-self._num(value)) for value in index_drawdowns],
                     self._pct(-self._num(strategy_drawdown))],
                    ["最大回撤修复天数(年度最大)",
                    #  self._integer(metrics.get("index_maximum_number_of_backtest_repair_days")),
                    #  self._integer(metrics.get("start_maximum_number_of_backtest_repair_days"))],
                    *[self._integer(max((m.get("year_index_yearly_max_repair_days") or {}).values(), default=0))
                      for m in metrics_list],
                    self._integer(max((strategy.get("year_start_yearly_max_repair_days") or {}).values(), default=0))],

                    [f"回撤发生次数(单日>{self._percent_label(daily_drawdown_threshold)})",
                     *[self._integer(m.get("index_dd_count")) for m in metrics_list],
                     self._integer(strategy.get("start_dd_count"))],
                ])},
            {"title": "2.2 分年度最大回撤", "table": self._table(
                ["年份", *[f"{run.label}回撤" for run in runs], "策略回撤", *drawdown_excess_headers],
                drawdown_rows)},
        ]

    def _risk_adjusted_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造三、风险调整收益指标章节的表格；超额比率按基准拆行。"""
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        benchmark_headers = self._benchmark_headers(runs)
        excess_row_suffixes = ([f"({tag})" if (tag := self._benchmark_tag(runs, run)) else ""
                                for run in runs]
                               if len(runs) > 1 else [""])
        rows = [
            ["夏普比率",
             *[self._decimal(self._year_all(m.get("index_sharpe_ratios"), "sharpe_ratio")) for m in metrics_list],
             self._decimal(self._year_all(strategy.get("start_sharpe_ratios"), "sharpe_ratio"))],
            ["卡玛比率",
             *[self._decimal(self._year_all(m.get("index_kama_ratio"), "kama_ratio")) for m in metrics_list],
             self._decimal(self._year_all(strategy.get("start_kama_ratio"), "kama_ratio"))],
            ["索提诺比率",
             *[self._decimal(self._year_all(m.get("index_sortino_ratio"), "sortino_ratio")) for m in metrics_list],
             self._decimal(self._year_all(strategy.get("start_sortino_ratio"), "sortino_ratio"))],
        ]
        for run, metrics, suffix in zip(runs, metrics_list, excess_row_suffixes):
            # 行占位与列数联动：指标 + N 个指数列占位 + 该基准的超额值。
            rows.append([f"超额夏普比率{suffix}", *["-"] * len(runs), self._decimal(metrics.get("excess_sharpe"))])
            rows.append([f"超额索提诺比率{suffix}", *["-"] * len(runs), self._decimal(metrics.get("excess_sortino"))])
        return [{"table": self._table(["指标", *benchmark_headers, "策略"], rows)}]

    def _monthly_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造四、月度收益分布章节的全部表格；数值统一取自 V1 指标结果。"""
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        distribution_labels = ["< -5%", "-5%~-2%", "-2%~0%", "0%~2%", "2%~5%", "5%~10%", ">10%"]
        index_distributions = [self._num_list(m.get("index_monthly_distribution")) for m in metrics_list]
        index_distribution_pcts = [self._num_list(m.get("index_monthly_distribution_pct")) for m in metrics_list]
        strategy_distribution = self._num_list(strategy.get("start_monthly_distribution"))
        strategy_distribution_pct = self._num_list(strategy.get("start_monthly_distribution_pct"))
        distribution_rows = [
            [label,
             *[self._integer(self._pick(distribution, index)) for distribution in index_distributions],
             *[self._pct(self._pick(distribution_pct, index) / 100) for distribution_pct in index_distribution_pcts],
             self._integer(self._pick(strategy_distribution, index)),
             self._pct(self._pick(strategy_distribution_pct, index) / 100)]
            for index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总月数", *[self._integer(m.get("total_months")) for m in metrics_list],
             self._integer(strategy.get("total_months"))],
            ["盈利月数", *[self._integer(m.get("index_profit_months")) for m in metrics_list],
             self._integer(strategy.get("start_profit_months"))],
            ["亏损月数", *[self._integer(m.get("index_loss_months")) for m in metrics_list],
             self._integer(strategy.get("start_loss_months"))],
            ["月盈利百分比", *[self._pct(m.get("index_profit_percentage")) for m in metrics_list],
             self._pct(strategy.get("start_profit_percentage"))],
            ["平均月收益率", *[self._pct(self._year_all(m.get("index_sharpe_ratios"), "avg_monthly_return"))
                               for m in metrics_list],
             self._pct(self._year_all(strategy.get("start_sharpe_ratios"), "avg_monthly_return"))],
            ["月收益率标准差", *[self._pct(self._year_all(m.get("index_sharpe_ratios"), "monthly_std_dev"))
                                 for m in metrics_list],
             self._pct(self._year_all(strategy.get("start_sharpe_ratios"), "monthly_std_dev"))],
            ["最大单月收益", *[self._pct(m.get("index_max_monthly_return")) for m in metrics_list],
             self._pct(strategy.get("start_max_monthly_return"))],
            ["最大单月亏损", *[self._pct(m.get("index_max_monthly_loss")) for m in metrics_list],
             self._pct(strategy.get("start_max_monthly_loss"))],
            ["月收益率偏度", *[self._decimal(m.get("index_monthly_return_skewness")) for m in metrics_list],
             self._decimal(strategy.get("start_monthly_return_skewness"))],
            ["月收益率峰度", *[self._decimal(m.get("index_monthly_return_kurtosis")) for m in metrics_list],
             self._decimal(strategy.get("start_monthly_return_kurtosis"))],
        ]
        if len(runs) > 1:
            distribution_headers = [header for run in runs
                                    for header in (f"{run.label}月数", f"{run.label}占比")]
        else:
            distribution_headers = ["指数月数", "指数占比"]
        return [
            {"title": "4.1 月度统计总览", "table": self._table(
                ["指标", *self._benchmark_headers(runs), "策略"], summary_rows)},
            {"title": "4.2 月度收益区间分布", "table": self._table(
                ["收益区间", *distribution_headers, "策略月数", "策略占比"], distribution_rows)},
        ]

    def _daily_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造五、日度收益分布章节的全部表格；数值统一取自 V1 指标结果。"""
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        distribution_labels = ["<-5%", "-5%~-3%", "-3%~-1%", "-1%~0%", "0%~1%", "1%~3%", "3%~5%", ">5%"]
        index_distributions = [self._num_list(m.get("index_days_distribution")) for m in metrics_list]
        index_distribution_pcts = [self._num_list(m.get("index_days_distribution_pct")) for m in metrics_list]
        strategy_distribution = self._num_list(strategy.get("start_days_distribution"))
        strategy_distribution_pct = self._num_list(strategy.get("start_days_distribution_pct"))
        distribution_rows = [
            [label,
             *[self._integer(self._pick(distribution, index)) for distribution in index_distributions],
             *[self._pct(self._pick(distribution_pct, index) / 100) for distribution_pct in index_distribution_pcts],
             self._integer(self._pick(strategy_distribution, index)),
             self._pct(self._pick(strategy_distribution_pct, index) / 100)]
            for index, label in enumerate(distribution_labels)]
        summary_rows = [
            ["总交易日", *[self._integer(m.get("total_trading_days")) for m in metrics_list],
             self._integer(strategy.get("total_trading_days"))],
            ["盈利天数", *[self._integer(m.get("index_profit_days")) for m in metrics_list],
             self._integer(strategy.get("start_profit_days"))],
            ["亏损天数", *[self._integer(m.get("index_loss_days")) for m in metrics_list],
             self._integer(strategy.get("start_loss_days"))],
            ["日盈利百分比", *[self._pct(m.get("index_days_profit_percentage")) for m in metrics_list],
             self._pct(strategy.get("start_days_profit_percentage"))],
            ["日均收益率", *[self._pct(m.get("index_mean_daily_return")) for m in metrics_list],
             self._pct(strategy.get("start_mean_daily_return"))],
            ["日收益率标准差", *[self._pct(m.get("index_daily_return_std")) for m in metrics_list],
             self._pct(strategy.get("start_daily_return_std"))],
            ["最大单日收益", *[self._pct(m.get("index_max_daily_gain")) for m in metrics_list],
             self._pct(strategy.get("start_max_daily_gain"))],
            ["最大单日亏损", *[self._pct(m.get("index_max_daily_loss")) for m in metrics_list],
             self._pct(strategy.get("start_max_daily_loss"))],
            ["日收益率偏度", *[self._decimal(m.get("index_mean_daily_skewness")) for m in metrics_list],
             self._decimal(strategy.get("start_mean_daily_skewness"))],
            ["日收益率峰度", *[self._decimal(m.get("index_mean_daily_kurtosis")) for m in metrics_list],
             self._decimal(strategy.get("start_mean_daily_kurtosis"))],
        ]
        profit_loss_rows = [
            ["平均盈利日收益", *[self._pct(m.get("index_avg_profit_day_return")) for m in metrics_list],
             self._pct(strategy.get("start_avg_profit_day_return"))],
            ["平均亏损日收益", *[self._pct(m.get("index_avg_loss_day_return")) for m in metrics_list],
             self._pct(strategy.get("start_avg_loss_day_return"))],
            ["盈亏比(平均盈利/平均亏损)", *[self._decimal(m.get("index_profit_loss_ratio")) for m in metrics_list],
             self._decimal(strategy.get("start_profit_loss_ratio"))],
            ["单笔最大盈利/最大亏损", *[self._decimal(m.get("index_max_profit_loss_ratio")) for m in metrics_list],
             self._decimal(strategy.get("start_max_profit_loss_ratio"))],
        ]
        if len(runs) > 1:
            distribution_headers = [header for run in runs
                                    for header in (f"{run.label}天数", f"{run.label}占比")]
        else:
            distribution_headers = ["指数天数", "指数占比"]
        overview_headers = ["指标", *self._benchmark_headers(runs), "策略"]
        return [
            {"title": "5.1 日度统计总览", "table": self._table(overview_headers, summary_rows)},
            {"title": "5.2 盈亏比分析", "table": self._table(overview_headers, profit_loss_rows)},
            {"title": "5.3 日度收益区间分布", "table": self._table(
                ["收益区间", *distribution_headers, "策略天数", "策略占比"], distribution_rows)},
        ]

    def _excess_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造六、超额收益分析章节的全部表格；数值按基准逐列展开。"""
        metrics_list = self._run_metrics_list(runs)
        multiple = len(runs) > 1
        value_headers = [self._tagged_header("超额", runs, run) for run in runs] if multiple else ["数值"]
        annualized_list = [self._year_all(m.get("excess_returns"), "annualized_return_diff") for m in metrics_list]
        distribution_labels = ["<-2%", "-2%~0%", "0%~2%", "2%~5%", ">5%"]
        distribution_counts = [self._num_list(m.get("excess_distribution")) for m in metrics_list]
        distribution_pcts = [self._num_list(m.get("excess_distribution_pct")) for m in metrics_list]
        distribution_rows = [
            [label,
             *[cell for counts, pcts in zip(distribution_counts, distribution_pcts)
               for cell in (self._integer(self._pick(counts, index)),
                            self._pct(self._pick(pcts, index) / 100))]]
            for index, label in enumerate(distribution_labels)]
        excess_rows = [
            ["累计超额(策略-指数)", *[self._pct(m.get("excess_cumulative_return")) for m in metrics_list]],
            ["年化超额", *[self._pct(value) for value in annualized_list]],
            ["月超额收益均值", *[self._pct(m.get("average_monthly_excess_return")) for m in metrics_list]],
            ["月超额收益波动率", *[self._pct(m.get("monthly_excess_return_standard_deviation")) for m in metrics_list]],
            ["月超额胜率(>0)", *[self._pct(m.get("monthly_excess_win_rate")) for m in metrics_list]],
            ["最大单月超额", *[self._pct(m.get("max_monthly_excess")) for m in metrics_list]],
        ]
        excess_rolling_rows = [self._excess_rolling_row(runs, months) for months in (1, 3, 6, 12)]
        if multiple:
            distribution_headers = [header for run in runs
                                    for header in (self._tagged_header("月数", runs, run),
                                                   self._tagged_header("占比", runs, run))]
            rolling_headers = ["滚动窗口", *[header for run in runs
                                             for header in (self._tagged_header("平均超额", runs, run),
                                                            self._tagged_header("正超额概率", runs, run))]]
        else:
            distribution_headers = ["月数", "占比"]
            rolling_headers = ["滚动窗口", "平均超额", "正超额概率"]
        return [
            {"title": "6.1 超额收益统计", "table": self._table(
                ["指标", *value_headers], excess_rows)},
            {"title": "6.2 超额收益区间分布", "table": self._table(
                ["超额区间", *distribution_headers], distribution_rows)},
            {"title": "6.3 滚动超额胜率", "table": self._table(
                rolling_headers, excess_rolling_rows)},
        ]

    @classmethod
    def _excess_rolling_row(cls, runs: list[_BenchmarkRun], months: int) -> list[str]:
        """1 个月窗口取 V1 月度超额统计；其余窗口消费 V1 滚动超额聚合导出。"""
        label = f"{months}个月"
        metrics_list = cls._run_metrics_list(runs)
        dashes = ["-"] * (len(runs) * 2)
        if months > 1:
            reason = metrics_list[0].get(f"excess_rolling_return_{months}_reason")
            if reason:
                return [f"{label}（{reason}）", *dashes]
            averages = [m.get(f"excess_rolling_return_{months}_avg_return") for m in metrics_list]
            win_rates = [m.get(f"excess_rolling_return_{months}_win_rate") for m in metrics_list]
            if any(value is None for value in averages) or any(value is None for value in win_rates):
                return [label, *dashes]
        else:
            averages = [m.get("average_monthly_excess_return") for m in metrics_list]
            win_rates = [m.get("monthly_excess_win_rate") for m in metrics_list]
            if all(value is None for value in averages) and all(value is None for value in win_rates):
                return [label, *dashes]
        cells: list[str] = []
        for average, win_rate in zip(averages, win_rates):
            cells.extend([cls._pct(average), cls._pct(win_rate)])
        return [label, *cells]

    def _extreme_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造七、极端行情表现章节的全部表格；数值统一取自 V1 指标结果。

        跑赢次数为 V1 胜率的分子口径（月份以指数为准：指数跌破下跌阈值/
        超过上涨阈值的月份中，策略月收益高于指数月收益的月数）。
        """
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        benchmark_headers = self._benchmark_headers(runs)
        stage_excess_headers = ([self._tagged_header("超额", runs, run) for run in runs]
                                if len(runs) > 1 else ["超额"])
        downturn_threshold = strategy.get("market_downturn_threshold")
        if downturn_threshold is None:
            downturn_threshold = MetricsRuntimeParamsDTO().market_downturn_threshold
        upturn_threshold = strategy.get("market_upturn_threshold")
        if upturn_threshold is None:
            upturn_threshold = MetricsRuntimeParamsDTO().market_upturn_threshold
        daily_extreme_threshold = strategy.get("daily_extreme_threshold")
        if daily_extreme_threshold is None:
            daily_extreme_threshold = MetricsRuntimeParamsDTO().daily_extreme_threshold
        daily_extreme_label = self._percent_label(daily_extreme_threshold)
        downturn_rows = [
            ["阶段月数", *[self._integer(m.get("index_downfall_months_len")) for m in metrics_list],
             self._integer(strategy.get("start_downfall_months_len")), *["-"] * len(runs)],
            ["平均收益", *[self._pct(m.get("index_downfall_avg_return")) for m in metrics_list],
             self._pct(strategy.get("start_downfall_avg_return")),
             *[self._pct(m.get("downfall_excess_avg_return")) for m in metrics_list]],
            ["策略跑赢次数", *["-"] * len(runs),
             self._integer(strategy.get("downfall_outperform_count")),
             *[self._pct(m.get("downfall_win_rate")) for m in metrics_list]]]
        upturn_rows = [
            ["阶段月数", *[self._integer(m.get("index_upward_months_len")) for m in metrics_list],
             self._integer(strategy.get("start_upward_months_len")), *["-"] * len(runs)],
            ["平均收益", *[self._pct(m.get("index_upward_avg_return")) for m in metrics_list],
             self._pct(strategy.get("start_upward_avg_return")),
             *[self._pct(m.get("upward_excess_avg_return")) for m in metrics_list]],
            ["策略跑赢次数", *["-"] * len(runs),
             self._integer(strategy.get("upward_outperform_count")),
             *[self._pct(m.get("upward_win_rate")) for m in metrics_list]]]
        extreme_rows = [
            ["最大单日涨幅", *[self._pct(m.get("index_max_daily_gain")) for m in metrics_list],
             self._pct(strategy.get("start_max_daily_gain"))],
            ["最大单日跌幅", *[self._pct(m.get("index_max_daily_loss")) for m in metrics_list],
             self._pct(strategy.get("start_max_daily_loss"))],
            [f"涨幅>{daily_extreme_label}的天数", *[self._integer(m.get("index_daily_gain_days")) for m in metrics_list],
             self._integer(strategy.get("start_daily_gain_days"))],
            [f"跌幅>{daily_extreme_label}的天数", *[self._integer(m.get("index_daily_loss_days")) for m in metrics_list],
             self._integer(strategy.get("start_daily_loss_days"))],
            [f"涨跌比(涨>{daily_extreme_label}/跌>{daily_extreme_label})",
             *[self._decimal(m.get("index_daily_gain_loss_ratio")) for m in metrics_list],
             self._decimal(strategy.get("start_daily_gain_loss_ratio"))]]
        stage_headers = ["指标", *benchmark_headers, "策略", *stage_excess_headers]
        return [
            {"title": f"7.1 市场下跌阶段（指数月收益 < {self._threshold_label(downturn_threshold)}）",
             "table": self._table(stage_headers, downturn_rows)},
            {"title": f"7.2 市场上涨阶段（指数月收益 > {self._threshold_label(upturn_threshold)}）",
             "table": self._table(stage_headers, upturn_rows)},
            {"title": "7.3 极端单日表现", "table": self._table(
                ["指标", *benchmark_headers, "策略"], extreme_rows)},
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

    def _capital_curve_section(self, runs: list[_BenchmarkRun]) -> list[dict[str, Any]]:
        """构造八、资金曲线特征章节的表格；净值/连涨连跌/创新高统计统一取自 V1 指标结果。"""
        metrics_list = self._run_metrics_list(runs)
        strategy = metrics_list[0]
        index_consecutive_list = [(m.get("index_consecutive") or {}) for m in metrics_list]
        start_consecutive = strategy.get("start_consecutive") or {}
        rows = [
            ["初始净值", *[self._decimal(m.get("index_net_value_left"), 4) for m in metrics_list],
             self._decimal(strategy.get("start_net_value_left"), 4)],
            ["期末净值", *[self._decimal(m.get("index_net_value_right"), 4) for m in metrics_list],
             self._decimal(strategy.get("start_net_value_right"), 4)],
            ["最大连涨月份", *[self._integer(consecutive.get("max_gain_months"))
                               for consecutive in index_consecutive_list],
             self._integer(start_consecutive.get("max_gain_months"))],
            ["最大连跌月份", *[self._integer(consecutive.get("max_loss_months"))
                               for consecutive in index_consecutive_list],
             self._integer(start_consecutive.get("max_loss_months"))],
            ["创新高平均间隔月", *[self._decimal(m.get("index_new_high_avg_interval_months"), 1) for m in metrics_list],
             self._decimal(strategy.get("start_new_high_avg_interval_months"), 1)]]
        return [{"table": self._table(["指标", *self._benchmark_headers(runs), "策略"], rows)}]

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
        """整数指标展示；None 是计算侧 NaN/inf 的统一口径（无法计算），显示 "-" 而非 "0"。"""
        if value is None:
            return "-"
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

    def _conclusion(self, runs: list[_BenchmarkRun], first_date: str, last_date: str) -> list[str]:
        """按基准循环生成结论；累计回报与累计超额直接取自 V1 指标结果。"""
        strategy_return = self._num(runs[0].result.metrics.get("start_cumulative_return"))
        if len(runs) <= 1:
            index_return = self._num(runs[0].result.metrics.get("index_cumulative_return"))
            excess_return = self._num(runs[0].result.metrics.get("excess_cumulative_return"))
            return [
                f"本报告覆盖 {first_date} 至 {last_date}，指数累计回报率为 {index_return:.2%}，策略累计回报率为 {strategy_return:.2%}。",
                f"策略相对指数的累计超额回报为 {excess_return:.2%}。",
            ]
        paragraphs = [
            f"本报告覆盖 {first_date} 至 {last_date}，策略累计回报率为 {strategy_return:.2%}，"
            f"基准指数为 {'、'.join(run.label for run in runs)}。"
        ]
        for run in runs:
            index_return = self._num(run.result.metrics.get("index_cumulative_return"))
            excess_return = self._num(run.result.metrics.get("excess_cumulative_return"))
            paragraphs.append(
                f"{run.label}累计回报率为 {index_return:.2%}，策略相对其的累计超额回报为 {excess_return:.2%}。")
        return paragraphs

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

    @staticmethod
    def _drawdown_series(values: list[float]) -> list[float]:
        """回撤以历史最高净值为基准，输出小于等于 0 的比例序列。"""
        peak = values[0] if values else 1.0
        result = []
        for value in values:
            peak = max(peak, value)
            result.append(value / peak - 1 if peak else 0.0)
        return result

    def _build_chart_data(self, runs: list[_BenchmarkRun]) -> dict[str, Any]:
        """组装图表渲染数据；序列形状与 charts 模块的渲染契约一一对应。

        result_mapper 已提供累计收益对应的净值，不再对累计收益重复复利；
        基准序列按 runs 循环展开，策略序列取首个运行结果（各次运行一致）。
        """
        result = runs[0].result
        dates = self._dates(result.index_df)
        metrics = result.metrics
        annual_strategy = {str(item.get("year")): self._num(item.get("annual_return")) for item in
                           metrics.get("start_returns_rate") or [] if isinstance(item, dict)}
        strategy_nav = self._net_values(result.start_df, "start_return")
        strategy_daily = result.start_df["daily_return"].tolist() if "daily_return" in result.start_df else []
        benchmarks = []
        daily_panels = []
        excess_series = []
        monthly_excess = []
        benchmark_annuals = []
        for run in runs:
            run_result = run.result
            benchmark_nav = self._net_values(run_result.index_df, "index_return")
            daily_returns = (run_result.index_df["daily_return"].tolist()
                             if "daily_return" in run_result.index_df else [])
            benchmarks.append({
                "label": run.label,
                "nav": benchmark_nav,
                "drawdown": self._drawdown_series(benchmark_nav),
                "daily_returns": daily_returns,
            })
            daily_panels.append({"label": run.label, "values": daily_returns})
            tag = self._benchmark_tag(runs, run)
            excess_series.append({
                "label": f"超额({tag})" if tag else ("累计超额收益" if len(runs) <= 1 else "超额"),
                "values": run_result.excess_df["excess_return"].tolist(),
            })
            monthly_excess.append({
                "title": f"月度超额分布（{tag}）" if tag else "月度超额分布",
                "values": [self._num(item.get("monthly_excess_return_diff")) for item in
                           run_result.metrics.get("monthly_excess_returns") or [] if isinstance(item, dict)],
            })
            benchmark_annuals.append({
                "label": run.label,
                "values_by_year": {str(item.get("year")): self._num(item.get("annual_return")) for item in
                                   run_result.metrics.get("index_returns_rate") or [] if isinstance(item, dict)},
            })
        years = sorted(set().union(*(set(item["values_by_year"]) for item in benchmark_annuals)) | set(annual_strategy))
        if not years:
            years = sorted({str(value.year) for value in dates})
        return {
            "dates": dates,
            "benchmarks": benchmarks,
            "strategy_nav": strategy_nav,
            "strategy_drawdown": self._drawdown_series(strategy_nav),
            "strategy_daily_returns": strategy_daily,
            "excess_series": excess_series,
            "annual_returns": {
                "years": years,
                "benchmarks": [{"label": item["label"],
                                "values": [item["values_by_year"].get(year, 0) for year in years]}
                               for item in benchmark_annuals],
                "strategy": [annual_strategy.get(year, 0) for year in years],
            },
            "daily_distribution": {"benchmarks": daily_panels, "strategy": strategy_daily},
            "monthly_excess_by_benchmark": monthly_excess,
        }

strategy_backtest_report_service = StrategyBacktestReportService()
