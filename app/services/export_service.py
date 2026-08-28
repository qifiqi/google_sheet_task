"""统一文件导出服务。"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO, StringIO
from queue import Queue
from threading import Thread
from typing import Any, BinaryIO, Callable, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from app.extensions import db
from app.models import Task, TaskResult
from app.services.backtest_multi_product_service import (
    build_multi_product_global_preview_payload,
)
from app.services.backtest_training_api_service import (
    _build_backtest_result_export_data,
    _build_global_preview_payload,
    _build_global_preview_workbook,
    _build_zip_member_name,
    split_global_preview_payload_by_stock,
)
from app.services.export_file_service import (
    build_c3_worksheets,
    build_c7_stock_code_export_archive,
    build_task_export,
    sanitize_export_filename,
)
from app.services.model_summary_service import model_summary_service
from app.services.task import task_manager
from app.services.xpl_service import xpl_analyzer
from app.services.strategy_backtest_report_service import strategy_backtest_report_service


EXCEL_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZIP_MIMETYPE = "application/zip"
CSV_MIMETYPE = "text/csv; charset=utf-8"
MAX_BATCH_TASKS = 10


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
            raise ValueError("任务暂无可导出结果")
        export = build_task_export(task, results)
        buffer = BytesIO()
        export.workbook.save(buffer)
        buffer.seek(0)
        return GeneratedFile(export.filename, export.mimetype, buffer, buffer.getbuffer().nbytes)

    def export_task_results_by_stock(self, task_id: str) -> GeneratedFile:
        """处理export_task_results_by_stock相关逻辑。"""
        task = self._get_task(task_id)
        results = task_manager.get_task_results(task_id)
        if str(task.task_type or "").strip().lower() != "google_sheet_c7":
            raise ValueError("按股票代码导出仅支持 C7 任务")
        if not results:
            raise ValueError("任务暂无可导出结果")
        export = build_c7_stock_code_export_archive(task, results)
        return GeneratedFile(export.filename, export.mimetype, export.buffer, export.buffer.getbuffer().nbytes)

    def export_task_results_batch(self, task_ids: list[str]) -> GeneratedFile:
        """处理export_task_results_batch相关逻辑。"""
        task_ids = self._validate_task_ids(task_ids)
        if len(task_ids) > MAX_BATCH_TASKS:
            raise ValueError(f"合并导出最多支持 {MAX_BATCH_TASKS} 个任务，当前选择了 {len(task_ids)} 个")

        tasks = Task.query.filter(Task.id.in_(task_ids)).all()
        if not tasks:
            raise LookupError("未找到匹配任务")
        task_map = {task.id: task for task in tasks}
        missing = [task_id for task_id in task_ids if task_id not in task_map]
        if missing:
            raise LookupError(f"任务不存在: {', '.join(missing)}")

        rows = (
            db.session.query(TaskResult.task_id, TaskResult.step_index, TaskResult.result)
            .filter(TaskResult.task_id.in_(task_ids))
            .order_by(TaskResult.task_id, TaskResult.step_index.asc())
            .all()
        )
        result_map: dict[str, list[dict[str, Any]]] = {}
        for task_id, step_index, result_json in rows:
            try:
                parsed = json.loads(result_json) if result_json else {}
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            result_map.setdefault(task_id, []).append({
                "task_id": task_id,
                "step_index": step_index,
                "result": parsed,
            })

        merged_results: list[dict[str, Any]] = []
        for task in sorted(tasks, key=lambda item: item.name or ""):
            for item in result_map.get(task.id, []):
                item["task_name"] = task.name or ""
                merged_results.append(item)
        if not merged_results:
            raise ValueError("所选任务均无结果数据")

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
    ) -> GeneratedFile:
        """处理export_global_preview相关逻辑。"""
        task = self._get_task(task_id)
        payload = self._global_preview_payload(task, ratios_override=ratios_override)
        if payload is None:
            raise LookupError("任务不存在")
        workbook = _build_global_preview_workbook(payload)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        task_name = (payload.get("task") or {}).get("name") or task_id
        filename = f"{sanitize_export_filename(task_name)}_global_preview.xlsx"
        return GeneratedFile(filename, EXCEL_MIMETYPE, buffer, buffer.getbuffer().nbytes)

    def export_global_preview_by_stock(
        self,
        task_id: str,
        ratios_override: list[Any] | None = None,
    ) -> GeneratedStream:
        """处理export_global_preview_by_stock相关逻辑。"""
        task = self._get_task(task_id)
        payload = self._global_preview_payload(task, ratios_override=ratios_override)
        if payload is None:
            raise LookupError("任务不存在")
        task_name = sanitize_export_filename(task.name or task_id)
        return GeneratedStream(
            filename=f"{task_name}_global_preview.zip",
            mimetype=ZIP_MIMETYPE,
            generate=lambda: self._stream_stock_zip(payload, task_name),
        )

    def export_global_preview_batch(self, task_ids: list[str]) -> GeneratedFile:
        """处理export_global_preview_batch相关逻辑。"""
        task_ids = self._validate_task_ids(task_ids)
        if len(task_ids) > MAX_BATCH_TASKS:
            raise ValueError(f"批量导出最多支持 {MAX_BATCH_TASKS} 个任务，当前选择了 {len(task_ids)} 个")

        zip_buffer = BytesIO()
        used_names: set[str] = set()
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as archive:
            for task_id in task_ids:
                task = self._get_task(task_id)
                if task.status != "completed":
                    raise ValueError(f"任务 {task.name or task_id} 尚未完成，不能导出")
                payload = self._global_preview_payload(task)
                if payload is None:
                    raise LookupError(f"任务不存在: {task_id}")
                workbook = _build_global_preview_workbook(payload)
                workbook_buffer = BytesIO()
                workbook.save(workbook_buffer)
                archive.writestr(
                    _build_zip_member_name(task.name, task_id, used_names),
                    workbook_buffer.getvalue(),
                )
        zip_buffer.seek(0)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return GeneratedFile(
            f"backtest_global_preview_batch_{stamp}.zip",
            ZIP_MIMETYPE,
            zip_buffer,
            zip_buffer.getbuffer().nbytes,
        )

    def export_backtest_result(self, result_id: int) -> GeneratedFile:
        """处理export_backtest_result相关逻辑。"""
        task_result = TaskResult.query.filter(TaskResult.id == result_id).first()
        if not task_result:
            raise LookupError("任务结果不存在")
        task = self._get_task(task_result.task_id)
        export_data = _build_backtest_result_export_data(task_result, task)
        buffer, mimetype = xpl_analyzer.export_file(export_data)
        return GeneratedFile(export_data["filename"], mimetype, buffer, buffer.getbuffer().nbytes)

    def export_xpl(self, payload: dict[str, Any]) -> GeneratedFile:
        """处理export_xpl相关逻辑。"""
        if not isinstance(payload, dict) or not payload:
            raise ValueError("请求数据不能为空")
        buffer, mimetype = xpl_analyzer.export_file(payload)
        filename = payload.get("filename") or "xpl_export.csv"
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
            raise ValueError(payload.get("message") or "模型汇总导出失败")
        content = "\ufeff" + (payload.get("content") or "")
        raw = content.encode("utf-8")
        buffer = BytesIO(raw)
        filename = sanitize_export_filename(payload.get("filename") or "model_summary.csv")
        if not filename.lower().endswith(".csv"):
            filename = f"{filename}.csv"
        return GeneratedFile(filename, CSV_MIMETYPE, buffer, len(raw))

    def export_backtest_word(self, payload: dict[str, Any]) -> GeneratedFile:
        """生成策略回测 Word 报告并返回内存字节流。"""
        filename, buffer = strategy_backtest_report_service.generate_word(payload)
        return GeneratedFile(filename, DOCX_MIMETYPE, buffer, buffer.getbuffer().nbytes)

    def _get_task(self, task_id: str) -> Task:
        """按 ID 获取任务。"""
        task = db.session.get(Task, task_id)
        if not task:
            raise LookupError("任务不存在")
        return task

    @staticmethod
    def _validate_task_ids(task_ids: Any) -> list[str]:
        """校验并规范化任务 ID 列表。"""
        if not isinstance(task_ids, list) or not task_ids:
            raise ValueError("请选择至少一个任务")
        normalized = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
        if not normalized:
            raise ValueError("请选择至少一个任务")
        return normalized

    @staticmethod
    def _global_preview_payload(
        task: Task,
        ratios_override: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        """构造全局预览数据。"""
        task_type = str(task.task_type or "").strip().lower()
        if task_type == "backtest_multi_product":
            return build_multi_product_global_preview_payload(task.id, ratios_override=ratios_override)
        return _build_global_preview_payload(task.id)

    def _stream_stock_zip(self, payload: dict[str, Any], task_name: str):
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
                        workbook = _build_global_preview_workbook(stock_payload)
                        filename = f"{sanitize_export_filename(f'{task_name}_{stock_code}')}.xlsx"
                        zip_info = ZipInfo(filename, date_time=datetime.now().timetuple()[:6])
                        zip_info.compress_type = ZIP_STORED
                        with archive.open(zip_info, "w") as xlsx_file:
                            workbook.save(xlsx_file)
            except Exception:
                # 生产线程异常无法再修改已发送的 HTTP 状态，只结束流并保留日志。
                import logging
                logging.getLogger(__name__).exception("全局预览流式导出失败: task_id=%s", task_id)
            finally:
                output_queue.put(finished)

        Thread(target=produce, daemon=True).start()
        while True:
            chunk = output_queue.get()
            if chunk is finished:
                break
            yield chunk


export_service = ExportService()
