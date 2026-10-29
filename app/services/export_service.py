"""统一文件导出服务。"""

from __future__ import annotations

import csv
from app.utils.json_utils import loads, JSONDecodeError
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO, StringIO
from queue import Queue
from threading import Thread
from typing import Any, BinaryIO, Callable, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from app.models import Task, TaskStatus
from app.utils.task_types import TYPE_GOOGLE_SHEET_C1_1, TYPE_GOOGLE_SHEET_C7
from app.exceptions import NotFoundError, ValidationError
from app.repositories import task_repository, task_result_repository
from app.schemas.backtest import StrategyBacktestReportSchema
from app.services.backtest_multi_product_preview import (
    build_multi_product_global_preview_payload,
    build_multi_product_global_preview_word_payload,
)
from app.services.backtest_report_query_service import (
    build_backtest_result_export_data,
    build_global_preview_payload,
    build_global_preview_workbook,
    _build_zip_member_name,
    _infer_backtest_export_model_name,
    split_global_preview_payload_by_stock,
)
from app.services.export_workbook_service import (
    build_c3_worksheets,
    build_c7_stock_code_export_archive,
    build_export_filename,
    build_task_export,
    compose_preview_stem,
    model_version_from_config,
    normalize_filename_date,
    price_adjust_filename_segment,
    sanitize_export_filename,
    EXCEL_MIMETYPE,
    ZIP_MIMETYPE,
)
from app.services.config_manager import get_config_manager
from app.services.docx_pdf_converter import convert_docx_to_pdf
from app.services.model_summary_service import model_summary_service
from app.services.task import task_manager
from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.strategy_backtest_report_service import strategy_backtest_report_service
from app.utils.logger import get_logger
from app.utils.model_version import normalize_model_version
from app.utils.ttl_cache import WORD_EXPORT_TTL_SECONDS, get_or_build_word_export
from app.utils.value_parser import parse_int

logger = get_logger(__name__)

DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIMETYPE = "application/pdf"
CSV_MIMETYPE = "text/csv; charset=utf-8"
MAX_BATCH_TASKS = 10

# Word 导出缓存 TTL 的系统配置键（分钟）；缺省回落到代码默认值。
WORD_EXPORT_CACHE_TTL_CONFIG_KEY = "word_export_cache_ttl_minutes"


def get_word_export_cache_ttl_seconds() -> int:
    """Word 导出缓存 TTL（秒），走系统配置 word_export_cache_ttl_minutes。

    <=0 表示关闭缓存（每次导出都重新生成）；读不到配置时用代码默认值。
    """
    default_minutes = WORD_EXPORT_TTL_SECONDS // 60
    minutes = parse_int(
        get_config_manager().get_config(WORD_EXPORT_CACHE_TTL_CONFIG_KEY, default_minutes),
        default=default_minutes,
    )
    return (minutes if minutes is not None else default_minutes) * 60


@dataclass(frozen=True)
class GeneratedFile:
    """统一描述一个可下载文件。"""

    filename: str
    mimetype: str
    buffer: BinaryIO
    file_size: int | None = None


@dataclass(frozen=True)
class GeneratedStream:
    """描述一个流式下载文件。"""

    filename: str
    mimetype: str
    generate: Callable[[], Iterable[bytes]]


class _ZipStreamWriter:
    """将 ZipFile 输出的字节块写入队列。"""

    def __init__(self, output_queue: Queue):
        """初始化实例状态。"""
        self.output_queue = output_queue
        self.position = 0

    def write(self, data):
        """向输出队列写入字节数据。"""
        if data:
            self.output_queue.put(bytes(data))
            self.position += len(data)
        return len(data)

    def tell(self):
        """返回当前输出位置。"""
        return self.position

    def flush(self):
        """刷新输出状态。"""
        return None

    def writable(self):
        """判断输出对象是否可写。"""
        return True


class ExportService:
    """统一导出业务编排；具体表格格式由现有领域构建器负责。"""

    def export_task_results(self, task_id: str) -> GeneratedFile:
        """处理export_task_results相关逻辑。"""
        task = self._get_task(task_id)
        results = task_manager.get_task_results(task_id)
        if not results:
            raise ValidationError("任务暂无可导出结果")
        export = build_task_export(task, results)
        buffer = BytesIO()
        export.workbook.save(buffer)
        buffer.seek(0)
        return GeneratedFile(export.filename, export.mimetype, buffer, buffer.getbuffer().nbytes)

    def export_task_results_by_stock(self, task_id: str) -> GeneratedFile:
        """处理export_task_results_by_stock相关逻辑。"""
        task = self._get_task(task_id)
        results = task_manager.get_task_results(task_id)
        if str(task.task_type or "").strip().lower() not in (TYPE_GOOGLE_SHEET_C7, TYPE_GOOGLE_SHEET_C1_1):
            raise ValidationError("按股票代码导出仅支持 C7/C1.1 任务")
        if not results:
            raise ValidationError("任务暂无可导出结果")
        export = build_c7_stock_code_export_archive(task, results)
        return GeneratedFile(export.filename, export.mimetype, export.buffer, export.buffer.getbuffer().nbytes)

    def export_task_results_batch(self, task_ids: list[str]) -> GeneratedFile:
        """处理export_task_results_batch相关逻辑。"""
        task_ids = self._validate_task_ids(task_ids)
        if len(task_ids) > MAX_BATCH_TASKS:
            raise ValidationError(f"合并导出最多支持 {MAX_BATCH_TASKS} 个任务，当前选择了 {len(task_ids)} 个")

        tasks = task_repository.list_by_ids(task_ids)
        if not tasks:
            raise NotFoundError("未找到匹配任务")
        task_map = {task["id"]: task for task in tasks}
        missing = [task_id for task_id in task_ids if task_id not in task_map]
        if missing:
            raise NotFoundError(f"任务不存在: {', '.join(missing)}")

        rows = task_result_repository.list_export_rows(task_ids)
        result_map: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            task_id = row["task_id"]
            step_index = row["step_index"]
            result_json = row["result"]
            try:
                parsed = loads(result_json) if result_json else {}
            except (TypeError, JSONDecodeError):
                parsed = {}
            result_map.setdefault(task_id, []).append({
                "task_id": task_id,
                "step_index": step_index,
                "result": parsed,
            })

        merged_results: list[dict[str, Any]] = []
        for task in sorted(tasks, key=lambda item: item["name"] or ""):
            for item in result_map.get(task["id"], []):
                item["task_name"] = task["name"] or ""
                merged_results.append(item)
        if not merged_results:
            raise ValidationError("所选任务均无结果数据")

        worksheets = build_c3_worksheets(merged_results)
        csv_buffer = StringIO(newline="")
        writer = csv.writer(csv_buffer)
        if worksheets:
            writer.writerow(worksheets[0].header)
            for worksheet in worksheets:
                writer.writerows(worksheet.rows)
        raw = csv_buffer.getvalue().encode("utf-8-sig")
        buffer = BytesIO(raw)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = sanitize_export_filename(f"C3_合并导出_{stamp}") + ".csv"
        return GeneratedFile(filename, CSV_MIMETYPE, buffer, len(raw))

    def export_global_preview(
        self,
        task_id: str,
        ratios_override: list[Any] | None = None,
        runtime_params: dict[str, Any] | None = None,
        export_name: str | None = None,
    ) -> GeneratedFile:
        """处理export_global_preview相关逻辑。"""
        task = self._get_task(task_id)
        payload = self._global_preview_payload(
            task,
            ratios_override=ratios_override,
            runtime_params=runtime_params,
        )
        if payload is None:
            raise NotFoundError("任务不存在")
        workbook = build_global_preview_workbook(payload)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        task_name = (payload.get("task") or {}).get("name") or task_id
        # 单文件导出保留基名+时间戳规范（防本地覆盖旧导出）；手输名替换基名。
        base = (
            sanitize_export_filename(export_name)
            if export_name
            else f"{sanitize_export_filename(task_name)}_global_preview"
        )
        kline_start, kline_end = self._preview_kline_bounds(payload)
        filename = build_export_filename(
            base,
            model_version=self._preview_model_text(task, payload),
            kline_start=kline_start,
            kline_end=kline_end,
            price_adjust=price_adjust_filename_segment(task.to_dict().get("config")),
        )
        return GeneratedFile(filename, EXCEL_MIMETYPE, buffer, buffer.getbuffer().nbytes)

    def export_global_preview_by_stock(
        self,
        task_id: str,
        ratios_override: list[Any] | None = None,
        runtime_params: dict[str, Any] | None = None,
        export_name: str | None = None,
    ) -> GeneratedStream:
        """处理export_global_preview_by_stock相关逻辑。"""
        task = self._get_task(task_id)
        payload = self._global_preview_payload(
            task,
            ratios_override=ratios_override,
            runtime_params=runtime_params,
        )
        if payload is None:
            raise NotFoundError("任务不存在")
        # zip 外层保留任务名基名（聚合容器无单一股票语义，需可辨认来源）；
        # 成员文件按新规范（模型版本-股票代码_区间），不带任务名。
        task_name = sanitize_export_filename(export_name or task.name or task_id)
        base = task_name if export_name else f"{task_name}_global_preview"
        model_text = self._preview_model_text(task, payload)
        price_adjust = price_adjust_filename_segment(task.to_dict().get("config"))
        return GeneratedStream(
            filename=build_export_filename(base, model_version=model_text, extension="zip", price_adjust=price_adjust),
            mimetype=ZIP_MIMETYPE,
            generate=lambda: self._stream_stock_zip(payload, model_text, price_adjust=price_adjust),
        )

    def export_global_preview_batch(self, task_ids: list[str]) -> GeneratedFile:
        """处理export_global_preview_batch相关逻辑。"""
        task_ids = self._validate_task_ids(task_ids)
        if len(task_ids) > MAX_BATCH_TASKS:
            raise ValidationError(f"批量导出最多支持 {MAX_BATCH_TASKS} 个任务，当前选择了 {len(task_ids)} 个")

        zip_buffer = BytesIO()
        used_names: set[str] = set()
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as archive:
            for task_id in task_ids:
                task = self._get_task(task_id)
                if task.status != TaskStatus.COMPLETED.value:
                    raise ValidationError(f"任务 {task.name or task_id} 尚未完成，不能导出")
                payload = self._global_preview_payload(task)
                if payload is None:
                    raise NotFoundError(f"任务不存在: {task_id}")
                workbook = build_global_preview_workbook(payload)
                workbook_buffer = BytesIO()
                workbook.save(workbook_buffer)
                kline_start, kline_end = self._preview_kline_bounds(payload)
                # 批量 zip 成员是"每任务一文件"，保留基名+时间戳规范（非按股票拆分场景）。
                member_stem = build_export_filename(
                    f"{sanitize_export_filename(task.name)}_global_preview",
                    model_version=self._preview_model_text(task, payload),
                    kline_start=kline_start,
                    kline_end=kline_end,
                    price_adjust=price_adjust_filename_segment(task.to_dict().get("config")),
                    extension="",
                )
                archive.writestr(
                    _build_zip_member_name(task.name, task_id, used_names, member_stem=member_stem),
                    workbook_buffer.getvalue(),
                )
        zip_buffer.seek(0)
        return GeneratedFile(
            build_export_filename("global_preview_batch", extension="zip"),
            ZIP_MIMETYPE,
            zip_buffer,
            zip_buffer.getbuffer().nbytes,
        )

    def export_backtest_result(self, result_id: int) -> GeneratedFile:
        """处理export_backtest_result相关逻辑。"""
        task_result = task_result_repository.get_export_entity(result_id)
        if not task_result:
            raise NotFoundError("任务结果不存在")
        task = self._get_task(task_result.task_id)
        export_data = build_backtest_result_export_data(task_result, task)
        buffer, mimetype = performance_analyzer.export_file(export_data)
        return GeneratedFile(export_data["filename"], mimetype, buffer, buffer.getbuffer().nbytes)

    def export_performance_analysis(self, payload: dict[str, Any]) -> GeneratedFile:
        """导出绩效分析结果。"""
        if not isinstance(payload, dict) or not payload:
            raise ValidationError("请求数据不能为空")
        buffer, mimetype = performance_analyzer.export_file(payload)
        filename = payload.get("filename") or "performance_analysis_export.csv"
        if not str(filename).lower().endswith(".csv"):
            filename = f"{filename}.csv"
        return GeneratedFile(sanitize_export_filename(filename), mimetype, buffer, buffer.getbuffer().nbytes)

    def export_model_summary(
        self,
        user: Any,
        filters: dict[str, Any],
        *,
        ignore_permissions: bool = False,
    ) -> GeneratedFile:
        """处理export_model_summary相关逻辑。"""
        payload = model_summary_service.export_csv(
            user,
            filters,
            ignore_permissions=ignore_permissions,
        )
        if payload.get("status") != "success":
            raise ValidationError(payload.get("message") or "模型汇总导出失败")
        content = "\ufeff" + (payload.get("content") or "")
        raw = content.encode("utf-8")
        buffer = BytesIO(raw)
        filename = sanitize_export_filename(payload.get("filename") or "model_summary.csv")
        if not filename.lower().endswith(".csv"):
            filename = f"{filename}.csv"
        return GeneratedFile(filename, CSV_MIMETYPE, buffer, len(raw))

    def export_backtest_word(self, report_request: StrategyBacktestReportSchema) -> GeneratedFile:
        """生成策略回测 Word 报告并返回内存字节流。

        请求边界校验由路由层 parse_body 完成；RPT-M 在此按任务构建
        products 载荷后再次过 Schema，generate_word 只接收校验后的模型。
        相同查询条件（展开后的有效载荷一致）在 TTL 内直接回放缓存文件，
        跳过指标计算与图表渲染；缓存落盘 data/word_export_cache/，重启后
        依然有效。TTL 走系统配置 word_export_cache_ttl_minutes（分钟，
        <=0 关闭缓存），缓存条目带 title/task_id/stock_codes 元数据，
        支持管理端按任务定向清理。
        """
        payload = report_request
        if report_request.report_type == "RPT-M":
            if not report_request.task_id:
                raise ValidationError("RPT-M 报告必须传入 task_id")
            if report_request.group_key in (None, ""):
                raise ValidationError("RPT-M 报告必须传入 group_key")
            if not isinstance(report_request.ratios, list):
                raise ValidationError("RPT-M 报告的 ratios 必须是数组")
            word_payload = build_multi_product_global_preview_word_payload(
                report_request.task_id,
                str(report_request.group_key),
                ratios_override=report_request.ratios,
            )
            if word_payload is None:
                raise ValidationError("task_id 不是有效的多产品回测任务")
            payload = StrategyBacktestReportSchema.model_validate(word_payload)
            # 方案组号随请求回填：word_payload 不含 group_key，
            # 默认文件名的方案段（G组号）需要它。
            payload.group_key = report_request.group_key

        if report_request.index_benchmarks:
            payload.index_benchmarks = report_request.index_benchmarks
        # 组合指数开关随请求透传：按任务构建的 word_payload 不含该字段，
        # 不显式回填会丢失前端选择。
        payload.include_composite_benchmark = report_request.include_composite_benchmark
        # 报告元数据/运行参数随请求覆盖任务默认值：重建载荷的 metadata 来自
        # 任务配置、runtime_params 缺省（rf=0），导出弹窗的价格类型只改展示
        # 行，无风险利率经 _runtime_params 进入 V1 引擎重算夏普；RPT-S 载荷
        # 即请求本身，此处合并为恒等操作。
        payload.metadata = {**payload.metadata, **report_request.metadata}
        payload.runtime_params = {**payload.runtime_params, **report_request.runtime_params}

        codes = {
            str(product.get("stock_code") or "").strip()
            for product in payload.products if isinstance(product, dict)
        }
        codes |= {str(item.stock_code or "").strip() for item in payload.index_benchmarks}
        codes.discard("")
        # 默认文件名价格/复权段：按 task_id 回查任务配置（RPT-S 直传 returns /
        # Google Sheet 来源无任务身份时省略该段，回落既有命名）。
        if not str(payload.price_adjust or "").strip() and report_request.task_id:
            try:
                task = self._get_task(str(report_request.task_id))
                payload.price_adjust = price_adjust_filename_segment(task.to_dict().get("config"))
            except NotFoundError:
                payload.price_adjust = None
        cache_meta = {
            "title": payload.title,
            "task_id": report_request.task_id,
            "stock_codes": sorted(codes),
        }
        filename, buffer, file_size = get_or_build_word_export(
            payload,
            lambda: strategy_backtest_report_service.generate_word(payload),
            ttl_seconds=get_word_export_cache_ttl_seconds(),
            meta=cache_meta,
        )
        return GeneratedFile(filename, DOCX_MIMETYPE, buffer, file_size)

    def export_backtest_pdf(self, report_request: StrategyBacktestReportSchema) -> GeneratedFile:
        """生成策略回测 PDF 报告：DOCX 为内容唯一事实源，缓存后经 LibreOffice 转换。

        复用 export_backtest_word 的载荷构建与磁盘缓存：缓存命中时直接取
        DOCX 转换，未命中先按 Word 链路生成并入缓存。转换细节见
        docx_pdf_converter（独立 profile、并发上限、超时终止）。
        下载文件名与 Word 报告同基名，仅后缀换 .pdf。
        """
        word_generated = self.export_backtest_word(report_request)
        filename = str(word_generated.filename)
        stem = filename[:-5] if filename.lower().endswith(".docx") else filename
        pdf_buffer, file_size = convert_docx_to_pdf(word_generated.buffer.read())
        return GeneratedFile(f"{stem}.pdf", PDF_MIMETYPE, pdf_buffer, file_size)

    def _get_task(self, task_id: str) -> Task:
        """按 ID 获取任务（实体供导出构造器消费）。"""
        task = task_repository.get_entity(task_id)
        if not task:
            raise NotFoundError("任务不存在")
        return task

    @staticmethod
    def _validate_task_ids(task_ids: Any) -> list[str]:
        """校验并规范化任务 ID 列表。"""
        if not isinstance(task_ids, list) or not task_ids:
            raise ValidationError("请选择至少一个任务")
        normalized = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
        if not normalized:
            raise ValidationError("请选择至少一个任务")
        return normalized

    @staticmethod
    def _global_preview_payload(
        task: Task,
        ratios_override: list[Any] | None = None,
        runtime_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """构造全局预览数据。

        ``runtime_params``（当前仅无风险利率）只对多品预览生效：单品预览
        沿用执行结果存档指标，没有可重算的口径入口。
        """
        task_type = str(task.task_type or "").strip().lower()
        if task_type == "backtest_multi_product":
            return build_multi_product_global_preview_payload(
                task.id,
                ratios_override=ratios_override,
                runtime_params=runtime_params,
            )
        return build_global_preview_payload(task.id)

    def _stream_stock_zip(self, payload: dict[str, Any], model_text: str = "", price_adjust: str = ""):
        """按股票流式生成 ZIP 文件。"""
        output_queue: Queue = Queue(maxsize=8)
        finished = object()
        task_id = str((payload.get("task") or {}).get("id") or "")

        def produce():
            """生成并输出压缩包内容。"""
            try:
                stock_payloads = sorted(
                    split_global_preview_payload_by_stock(payload or {}),
                    key=lambda item: item[0],
                )
                with ZipFile(_ZipStreamWriter(output_queue), "w", ZIP_STORED) as archive:
                    for stock_code, stock_payload in stock_payloads:
                        workbook = build_global_preview_workbook(stock_payload)
                        stock_start, stock_end = self._preview_kline_bounds(stock_payload)
                        # 新规范：成员名 = 模型版本-价格复权-股票代码_K线起-K线止（无任务名/时间戳，外层 zip 已带）。
                        stem = compose_preview_stem(model_text, stock_code, stock_start, stock_end, price_adjust=price_adjust)
                        filename = f"{sanitize_export_filename(stem)}.xlsx"
                        zip_info = ZipInfo(filename, date_time=datetime.now().timetuple()[:6])
                        zip_info.compress_type = ZIP_STORED
                        with archive.open(zip_info, "w") as xlsx_file:
                            workbook.save(xlsx_file)
            except Exception:
                # 生产线程异常无法再修改已发送的 HTTP 状态，只结束流并保留日志。
                logger.exception("全局预览流式导出失败: task_id=%s", task_id)
            finally:
                output_queue.put(finished)

        Thread(target=produce, daemon=True).start()
        while True:
            chunk = output_queue.get()
            if chunk is finished:
                break
            yield chunk

    @staticmethod
    def _preview_model_text(task: Task, payload: dict[str, Any]) -> str:
        """预览导出的模型段：多品组合无单一模型语义省略。

        单品优先取结果打标版本（唯一才写，混版本省略），回落按任务配置推断族名。
        """
        if str(task.task_type or "").strip().lower() == "backtest_multi_product":
            return ""
        versions = {
            normalized
            for group in payload.get("groups") or []
            if isinstance(group, dict)
            for column in group.get("columns") or []
            if isinstance(column, dict)
            for normalized in (normalize_model_version(column.get("model_version")),)
            if normalized
        }
        if len(versions) == 1:
            return next(iter(versions))
        task_config = task.to_dict().get("config") or {}
        config_version = model_version_from_config(task_config)
        if config_version:
            return config_version
        return _infer_backtest_export_model_name(task_config, task.task_type)

    @staticmethod
    def _preview_kline_bounds(payload: dict[str, Any]) -> tuple[str, str]:
        """预览载荷的真实 K 线包络（min起~max止）；缺失返回 ("", "")。

        多品取 products[].start_date/end_date（收益行首末），单品取分组 period
        （"起/止" 文本）；两者皆缺回落任务请求区间 task.start_date/end_date。
        """
        starts: list[str] = []
        ends: list[str] = []

        def _collect(start_raw: Any, end_raw: Any) -> None:
            start = normalize_filename_date(start_raw)
            end = normalize_filename_date(end_raw)
            if start and end:
                starts.append(start)
                ends.append(end)

        for product in payload.get("products") or []:
            if isinstance(product, dict):
                _collect(product.get("start_date"), product.get("end_date"))
        if not starts:
            for group in payload.get("groups") or []:
                if not isinstance(group, dict):
                    continue
                period_parts = str(group.get("period") or "").split("/")
                _collect(
                    period_parts[0] if period_parts else "",
                    period_parts[1] if len(period_parts) > 1 else "",
                )
        if starts:
            return min(starts), max(ends)
        task_info = payload.get("task") or {}
        if isinstance(task_info, dict):
            start = normalize_filename_date(task_info.get("start_date"))
            end = normalize_filename_date(task_info.get("end_date"))
            if start and end:
                return start, end
        return "", ""


export_service = ExportService()
