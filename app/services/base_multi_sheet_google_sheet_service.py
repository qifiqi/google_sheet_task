from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from app.exceptions.checkForErrors import checkForErrors
from app.models import db
from app.services.base_google_sheet_service import BaseGoogleSheetService
from app.utils.db_retry import db_retry_manager
from app.utils.db_stock_api import StockAPIClient


class BaseMultiSheetGoogleSheetService(BaseGoogleSheetService):
    """C4/C5 多工作表任务的共享基类。"""

    use_advisory_lock = True

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None):
        super().__init__(config, task_id, event_queue=event_queue, app=app)
        self.api_client = StockAPIClient()

    def _run_task(self, task, name, parameters, config_data):
        """执行多工作表版本的批处理主流程。"""
        success_count, failed_count, task_status = self.get_bdl(task, name, parameters, config_data)
        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "task_status": task_status,
        }

    def get_bdl(self, task, name, parameters, config_data):
        """执行共享的多工作表批处理骨架。"""
        success_count = 0
        failed_count = 0

        try:
            batch_plan = self._build_batch_plan(parameters, config_data)
            total_combinations = batch_plan["total_combinations"]

            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

            self._log_info(f"将执行 {total_combinations} 个参数组合")

            start_index = task.current_step - 1 if task.current_step >= 1 else 0
            if start_index < 0:
                start_index = 0
            self._log_info(f"任务将从第 {start_index + 1} 个参数组合开始执行")

            success_count = start_index
            self._prepare_sheet_inputs(config_data)

            initial_wait_seconds = int(batch_plan.get("initial_wait_seconds", 20) or 0)
            if initial_wait_seconds > 0:
                self._log_info(f"所有表格均已清空，等待 {initial_wait_seconds} 秒后开始执行")
                self._sleep_seconds(initial_wait_seconds)

            processed_index = 0
            runtime_context = self._create_runtime_context(config_data)

            for batch in batch_plan["batches"]:
                for item in batch["items"]:
                    if processed_index < start_index:
                        processed_index += 1
                        continue

                    if self._is_task_cancelled():
                        self._log_warning("任务已被取消，停止执行")
                        return success_count, failed_count, "cancelled"

                    current_step = processed_index + 1
                    self._log_step(current_step, total_combinations, "开始执行参数组合")
                    self._log_info(f"正在执行第 {current_step}/{total_combinations} 个参数组合")

                    task.current_step = current_step
                    db_retry_manager.commit_with_retry(db.session)

                    try:
                        success, result, save_payload = self._execute_batch_item(
                            batch=batch,
                            item=item,
                            config_data=config_data,
                            runtime_context=runtime_context,
                        )

                        if not success:
                            failed_count += 1
                            self._log_warning(f"第 {current_step} 个参数组合执行失败")
                            return success_count, failed_count, "error"

                        success_count += 1
                        self._log_info(f"第 {current_step} 个参数组合执行成功，{result}")
                        self._save_task_result(current_step - 1, save_payload, result, success)
                        self._after_item_success(
                            item=item,
                            result=result,
                            runtime_context=runtime_context,
                            current_step=current_step,
                        )
                    except checkForErrors as exc:
                        task.error = exc
                        self._log_error(str(exc))
                        return success_count, failed_count, "error"
                    except Exception as exc:
                        failed_count += 1
                        task.error = exc

                        if self._is_task_cancelled():
                            self._log_info(f"第 {current_step} 个参数组合执行中断（任务已取消）: {str(exc)}")
                            return success_count, failed_count, "cancelled"

                        self._log_error(f"第 {current_step} 个参数组合执行出错: {str(exc)}")
                        return success_count, failed_count, "error"

                    processed_index += 1

            self._log_info(f"批量数据处理完成，总成功 {success_count}，总失败 {failed_count}")
            return success_count, failed_count, "completed"
        except Exception as exc:
            task.error = exc
            if self._is_task_cancelled():
                self._log_info(f"批量数据处理中断（任务已取消）: {str(exc)}")
                return success_count, failed_count, "cancelled"

            self._log_error(f"批量数据处理失败: {traceback.format_exc()}")
            return 0, 1, "error"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def send_stock_template_param_data(self, payload: Dict, log) -> int:
        """发送股票模板参数数据。"""
        try:
            self._log_api("发送股票模板参数数据", f"payload: {payload}")
            result = self.api_client.insert_stock_template_param(payload)
            self._log_api("发送股票模板参数数据成功", f"ID: {result}")
            return result
        except Exception as exc:
            self._log_api_error("发送股票模板参数数据", str(exc))
            log("error", f"发送股票模板参数数据失败: {str(exc)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def get_single_stock_template_param(self, stock_no: str) -> Optional[Dict]:
        """获取单个股票模板参数。"""
        try:
            self._log_api("获取股票模板参数", f"stock_no: {stock_no}")
            result = self.api_client.get_single_stock_template_param(stock_no)
            self._log_api("获取股票模板参数成功", f"返回结果类型: {type(result)}")
            return result
        except Exception as exc:
            self._log_api_error("获取股票模板参数", str(exc))
            raise

    def _init_google_sheet(self, config_data: Dict[str, Any]):
        """初始化多工作表连接。"""
        try:
            self._log_info("开始初始化 Google Sheet 连接")
            token_file = config_data.get("token_file", "data/token.json")
            proxy_url = config_data.get("proxy_url")
            self.google_sheets = self._init_multi_google_sheets(
                sheets=config_data.get("sheets"),
                token_file=token_file,
                proxy_url=proxy_url,
            )
        except Exception as exc:
            self._log_error(f"初始化 Google Sheet 连接失败: {str(exc)}")
            raise

    def _prepare_sheet_inputs(self, config_data: Dict[str, Any]) -> None:
        """清空多工作表输入区域，具体列位由子类提供。"""
        input_column_a, input_column_b = self._get_input_columns(config_data)

        for google_sheet in self.google_sheets:
            row_count = google_sheet.get_last_row("A")
            if row_count < 10:
                continue

            self._log_info(
                f"{google_sheet.title} 当前 A 列行数 {row_count}，准备清空 {input_column_a} 到 {input_column_b}"
            )
            google_sheet.clear_range(f"{input_column_a}2:{input_column_b}{row_count + 2}")

    def _is_task_cancelled(self) -> bool:
        """检查任务是否已经取消。"""
        task_status = self._query_task_status()
        return bool(not task_status or task_status == "cancelled")

    def _query_task_status(self) -> Optional[str]:
        """读取当前任务状态，供批处理循环统一复用。"""
        row = db.session.execute(
            text("SELECT status FROM tasks WHERE id = :task_id"),
            {"task_id": self.task_id},
        ).fetchone()
        return getattr(row, "status", None) if row else None

    def _sleep_seconds(self, seconds: int) -> None:
        """统一包装睡眠逻辑，便于后续扩展测试替身。"""
        import time

        time.sleep(seconds)

    def _create_runtime_context(self, config_data: Dict[str, Any]) -> dict[str, Any]:
        """创建批处理运行时上下文。"""
        return {}

    def _after_item_success(
        self,
        *,
        item: Any,
        result: Dict[str, Any],
        runtime_context: dict[str, Any],
        current_step: int,
    ) -> None:
        """单项执行成功后的扩展钩子，默认无需额外动作。"""

    def _build_batch_plan(self, parameters, config_data: Dict[str, Any]) -> dict[str, Any]:
        """构建批处理执行计划。"""
        raise NotImplementedError

    def _execute_batch_item(
        self,
        *,
        batch: dict[str, Any],
        item: Any,
        config_data: Dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> tuple[bool, Dict[str, Any], dict[str, Any]]:
        """执行单个批处理单元，并返回结果与保存载荷。"""
        raise NotImplementedError

    def _get_input_columns(self, config_data: Dict[str, Any]) -> tuple[str, str]:
        """返回输入区域列位。"""
        raise NotImplementedError
