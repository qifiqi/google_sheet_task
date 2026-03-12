from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from app.exceptions.checkForErrors import checkForErrors
from app.models import db
from app.services.base_google_sheet_service import BaseGoogleSheetService
from app.utils.db_retry import db_retry_manager
from app.utils.db_stock_api import StockAPIClient


class BaseSingleSheetGoogleSheetService(BaseGoogleSheetService):
    """默认单工作表任务的共享基类。"""

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None):
        super().__init__(config, task_id, event_queue=event_queue, app=app)
        self.api_client = StockAPIClient()

    def get_bdl(self, task, name, parameters, config_data, start_index=0):
        """执行单工作表版本的批处理主流程。"""
        success_count = 0
        failed_count = 0

        try:
            total_combinations = self._count_total_combinations(parameters)
            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

            self._log_info(f"将执行 {total_combinations} 个参数组合")

            if start_index > total_combinations:
                self._log_warning(
                    f"任务断点 {start_index} 大于参数组合总数 {total_combinations}，本次跳过执行"
                )
                return 0, 0, "completed"

            resume_index = self._resolve_resume_index(task, start_index)
            self._log_info(f"任务将从第 {resume_index + 1} 个参数组合开始执行")
            success_count = resume_index

            for item_index in range(resume_index, total_combinations):
                self._log_step(item_index + 1, total_combinations, "开始执行参数组合")

                if self._is_task_cancelled():
                    self._log_warning("任务已被取消，停止执行")
                    return success_count, failed_count, "cancelled"

                combination = self._get_parameter_combination_by_index(parameters, item_index)
                self._log_info(f"正在执行第 {item_index + 1}/{total_combinations} 个参数组合: {combination}")

                task.current_step = item_index + 1
                db_retry_manager.commit_with_retry(db.session)

                try:
                    success, result, save_payload, extension_payload = self._execute_batch_item(
                        combination=combination,
                        config_data=config_data,
                        item_index=item_index,
                    )

                    if not success:
                        failed_count += 1
                        self._log_warning(f"第 {item_index + 1} 个参数组合执行失败")
                        return success_count, failed_count, "error"

                    success_count += 1
                    self._log_info(f"第 {item_index + 1} 个参数组合执行成功，{result}")
                    self._save_task_result(item_index, save_payload, result, success)
                    self._after_item_success(
                        combination=combination,
                        result=result,
                        extension_payload=extension_payload,
                    )
                except checkForErrors as exc:
                    task.error = exc
                    self._log_error(str(exc))
                    return success_count, failed_count, "error"
                except Exception as exc:
                    failed_count += 1
                    task.error = exc

                    if self._is_task_cancelled():
                        self._log_info(f"第 {item_index + 1} 个参数组合执行中断（任务已取消）: {str(exc)}")
                        return success_count, failed_count, "cancelled"

                    self._log_error(f"第 {item_index + 1} 个参数组合执行出错: {str(exc)}")
                    return success_count, failed_count, "error"

                self._log_info(
                    f"第 {item_index + 1} 个参数组合执行完成，成功: {success_count}，失败: {failed_count}"
                )

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
        """初始化单工作表连接。"""
        try:
            self._log_info("开始初始化 Google Sheet 连接")
            token_file = config_data.get("token_file", "data/token.json")
            proxy_url = config_data.get("proxy_url")
            self.google_sheet = self._init_single_google_sheet(
                spreadsheet_id=config_data.get("spreadsheet_id"),
                sheet_name=config_data.get("sheet_name", "data"),
                token_file=token_file,
                proxy_url=proxy_url,
            )
            self._log_info("Google Sheet 连接初始化成功")
        except Exception as exc:
            self._log_error(f"初始化 Google Sheet 连接失败: {str(exc)}")
            raise

    def _count_total_combinations(self, parameters) -> int:
        """计算参数组合总数。"""
        total_combinations = 1
        for param_list in parameters:
            total_combinations *= len(param_list)
        return total_combinations

    def _resolve_resume_index(self, task, start_index: int) -> int:
        """统一处理断点恢复起始位置。"""
        if task.current_step >= 1:
            return max(start_index, task.current_step - 1)
        return start_index

    def _after_item_success(
        self,
        *,
        combination: Any,
        result: Dict[str, Any],
        extension_payload: dict[str, Any],
    ) -> None:
        """单项执行成功后的扩展钩子。"""

    def _execute_batch_item(
        self,
        *,
        combination: Any,
        config_data: Dict[str, Any],
        item_index: int,
    ) -> tuple[bool, Dict[str, Any], dict[str, Any], dict[str, Any]]:
        """执行单个批处理单元。"""
        raise NotImplementedError

    def _get_parameter_combination_by_index(self, parameters, index: int):
        """按索引计算参数组合。"""
        raise NotImplementedError
