import time
import uuid
import threading
import queue
import json
from itertools import product
from functools import reduce
import operator
# 获取当前应用实例，传递给后台线程
from flask import current_app
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import or_
from app.models import Task, TaskLog, TaskResult, GoogleSheet, db
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_service_C4 import GoogleSheetService as GoogleSheetServiceC4
from app.services.google_sheet_service_C5 import GoogleSheetService as GoogleSheetServiceC5
from app.utils.logger import get_logger, get_task_logger
from app.utils.database import transaction_required, safe_delete, safe_update, safe_create
from app.services.config_manager import get_config_manager
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.services.google_sheet_registry_service import get_google_sheet_registry_service

logger = get_logger(__name__)

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.running_tasks: Dict[str, threading.Thread] = {}
        self.task_events: Dict[str, queue.Queue] = {}
        self.task_stop_events: Dict[str, threading.Event] = {}
        self.start_errors: Dict[str, str] = {}
        self.task_token_occupancy: Dict[str, int] = {}
        # 不再在初始化时缓存配置，而是每次动态获取
    
    def _get_config(self, key: str, default: Any = None) -> Any:
        """动态获取配置，确保实时生效"""
        config_manager = get_config_manager()
        return config_manager.get_config(key, default)

    def _normalize_task_config_for_type(self, task_type: str, config):
        if not isinstance(config, dict):
            return config
        normalized = dict(config)
        if task_type in ('google_sheet_C4', 'google_sheet_C5'):
            normalized.pop('spreadsheet_id', None)
            normalized.pop('sheet_name', None)
        if task_type == 'backtest_training' and not normalized.get('token_id'):
            token_id = (
                self._get_config('backtest_training_token_id')
                or self._get_config('backtest_token_id')
                or self._get_config('google_sheet_backtest_token_id')
            )
            if token_id not in (None, '', 0, '0'):
                normalized['token_type'] = normalized.get('token_type', 'file')
                normalized['token_id'] = token_id
        return normalized
    
    @transaction_required
    def create_task(self, name: str, description: str, task_type: str, config: Dict[str, Any]) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        config = self._normalize_task_config_for_type(task_type, config)

        if isinstance(config, dict):
            config = get_google_sheet_token_service().prepare_task_config(config)
        
        # 确保配置被正确序列化
        config_str = json.dumps(config) if isinstance(config, dict) else str(config)
        
        task = safe_create(
            Task,
            id=task_id,
            name=name,
            description=description,
            task_type=task_type,
            config=config_str,
            status='pending'
        )

        if isinstance(config, dict):
            self._ensure_google_sheet_occupancy(task_id, config)
        
        # 使用任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.create")
        task_logger.info(f"创建任务成功 - 名称: {name}, 类型: {task_type}, 配置项数量: {len(config) if isinstance(config, dict) else 'N/A'}")
        
        logger.info(f"创建任务: {task_id} - {name}")
        return task_id

    def create_and_start_task(self, name: str, description: str, task_type: str, config: Dict[str, Any]):
        """创建并启动任务，供路由层直接调用。"""
        task_id = self.create_task(name, description, task_type, config)
        if self.start_task(task_id):
            return {"status": "success", "task_id": task_id, "message": "任务创建并启动成功"}, 200
        return {
            "status": "error",
            "task_id": task_id,
            "message": self.get_start_error(task_id)
        }, 400

    def batch_create_and_start_task(self, data: Dict[str, Any]):
        """C31 批量拆分为多个 C3 任务并尝试启动。"""
        if not isinstance(data, dict):
            raise ValueError("批量任务请求体必须是 JSON 对象")

        config = data.get('config') or {}
        if not isinstance(config, dict):
            raise ValueError("缺少有效的 config 配置")

        base_name = str(config.get('base_task_name') or data.get('name') or '').strip()
        if not base_name:
            raise ValueError("缺少 base_task_name")

        description = str(data.get('description') or config.get('task_description') or '').strip()
        child_task_type = 'google_sheet'

        sheets = config.get('sheets') or []
        stock_codes = config.get('stock_codes') or []
        parameter_groups = config.get('parameters') or []

        if not isinstance(sheets, list) or not sheets:
            raise ValueError("至少需要一组 sheets 配置")
        if not isinstance(stock_codes, list) or not stock_codes:
            raise ValueError("至少需要一个 stock_codes")
        if not isinstance(parameter_groups, list) or not parameter_groups:
            raise ValueError("至少需要一组 parameters")

        normalized_groups = self._normalize_c31_parameter_groups(parameter_groups)

        parameter_combinations = list(product(*normalized_groups))
        if not parameter_combinations:
            raise ValueError("未生成任何参数组合")

        sheet_count = len([sheet for sheet in sheets if isinstance(sheet, dict) and str(sheet.get('spreadsheet_id') or '').strip()])
        combination_count = len(parameter_combinations)
        if not self._is_count_compatible(combination_count, sheet_count):
            raise ValueError(
                f"参数组合数({combination_count})与Sheet数({sheet_count})必须相等，或其中一方是另一方的整数倍"
            )

        sheet_dict = {}
        for sheet in sheets:
            sheet_title = str(sheet.get('title') or '').strip()
            s_t = sheet_title.strip().strip("]").split('-')
            year_n,sort_n = s_t[-2], int(s_t[-1])
            sheet['sort_n'],sheet['year_n'] = sort_n,year_n
            if year_n not in sheet_dict:
                sheet_dict[year_n] = []
            sheet_dict[year_n].append(sheet)


        for k,v in sheet_dict.items():
            if len(v) != combination_count:
                raise ValueError(
                    f"{k} 所含有的表格数，无法对齐参数数量，{combination_count},检查是否是参数设置过多还是表格创建过少"
                )


        created_task_ids = []
        started_task_ids = []
        failed_to_start = []
        child_summaries = []
        sequence = 1

        shared_config = {
            key: value for key, value in config.items()
            if key not in {
                'base_task_name', 'task_description', 'stock_codes',
                'parameters', 'parameter_dimensions', 'sheets'
            }
        }

        # 批量任务默认使用随机 token
        if 'token_id' not in shared_config or not shared_config.get('token_id'):
            from app.services.google_sheet_token_service import RANDOM_TOKEN_VALUE
            shared_config['token_type'] = 'file'
            shared_config['token_id'] = RANDOM_TOKEN_VALUE


        for stock_code in stock_codes:
            stock_code = str(stock_code).strip()
            if not stock_code:
                continue

            for i, parameter_combo in enumerate(parameter_combinations):
                _sheet = [sheet_dict[k][i] for k in sheet_dict.keys()]

                for sheet in _sheet:
                    if not isinstance(sheet, dict):
                        continue

                    spreadsheet_id = str(sheet.get('spreadsheet_id') or '').strip()
                    sheet_name = str(sheet.get('sheet_name') or '').strip()
                    sheet_title = str(sheet.get('title') or '').strip()
                    sort_n = sheet.get('sort_n')
                    year_n = str(sheet.get('year_n') or '').strip()
                    if not spreadsheet_id:
                        continue

                    child_parameters = self._materialize_c31_parameter_combo(parameter_combo)
                    task_name = f"{base_name}-{year_n}-{sort_n}"

                    child_config = dict(shared_config)
                    child_config.update({
                        'spreadsheet_id': spreadsheet_id,
                        'sheet_name': sheet_name,
                        'title': sheet_title or None,
                        'stock_code': stock_code,
                        'year_n':year_n,
                        'parameters': child_parameters,
                    })

                    combo_count = reduce(operator.mul, [len(p) for p in child_parameters], 1)
                    _description = '批量执行 {} 个参数组合'.format(combo_count)
                    task_id = self.create_task(task_name, _description, child_task_type, child_config)
                    created_task_ids.append(task_id)

                    started = self.start_task(task_id)
                    if started:
                        started_task_ids.append(task_id)
                    else:
                        failed_to_start.append({
                            "task_id": task_id,
                            "task_name": task_name,
                            "error": self.get_start_error(task_id)
                        })

                    child_summaries.append({
                        "task_id": task_id,
                        "task_name": task_name,
                        "spreadsheet_id": spreadsheet_id,
                        "sheet_name": sheet_name,
                        "stock_code": stock_code,
                        "parameters": child_parameters,
                        "started": started
                    })
                    sequence += 1
                    time.sleep(0.5)

        if not created_task_ids:
            raise ValueError("没有生成任何子任务，请检查 sheets / stock_codes / parameters 配置")

        status = "success" if started_task_ids else "error"
        message = (
            f"C31 已拆分创建 {len(created_task_ids)} 个 C3 任务，"
            f"成功启动 {len(started_task_ids)} 个，未启动 {len(failed_to_start)} 个"
        )
        http_status = 200 if started_task_ids else 400

        return {
            "status": status,
            "message": message,
            "task_id": started_task_ids[0] if started_task_ids else created_task_ids[0],
            "task_ids": created_task_ids,
            "started_task_ids": started_task_ids,
            "failed_to_start": failed_to_start,
            "total_created": len(created_task_ids),
            "total_started": len(started_task_ids),
            "children": child_summaries,
        }, http_status

    def _materialize_c31_parameter_combo(self, parameter_combo):
        """把 C31 选中的单次组合整理成单个 C3 任务需要的完整二维数组。"""
        rows = []
        for item in parameter_combo:
            if not isinstance(item, list) or not item:
                raise ValueError("参数组合项必须是非空一维数组")
            rows.append(item)
        return rows

    def _normalize_c31_parameter_groups(self, parameter_groups):
        normalized_groups = []
        for idx, group in enumerate(parameter_groups, start=1):
            if not isinstance(group, list) or not group:
                raise ValueError(f"参数组 {idx} 必须是非空数组")

            if all(isinstance(group_item, list) for group_item in group):
                candidate_group = []
                for group_item in group:
                    if not isinstance(group_item, list) or not group_item:
                        raise ValueError(f"参数组 {idx} 的二维子项必须是非空一维数组")
                    candidate_group.append(group_item)
                normalized_groups.append(candidate_group)
            else:
                normalized_groups.append([group])
        return normalized_groups

    def _is_count_compatible(self, left_count: int, right_count: int) -> bool:
        if left_count <= 0 or right_count <= 0:
            return False
        return (
            left_count == right_count
            or left_count % right_count == 0
            or right_count % left_count == 0
        )


    def start_task(self, task_id: str) -> bool:
        """启动任务"""
        self.start_errors.pop(task_id, None)
        acquired_token_id = None
        if task_id in self.running_tasks and self.running_tasks[task_id].is_alive():
            error_msg = "任务已在启动或运行中，拒绝重复启动"
            self.start_errors[task_id] = error_msg
            logger.warning(f"重复启动任务被拒绝: {task_id}")
            return False
        # 创建任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.start")
        
        # 动态获取最大并发任务数配置，确保实时生效
        # 系统级并发限制：控制同时运行中的任务总数。
        # 这和 token 占用限制不同，后者由 GoogleSheetTokenService 单独判断。
        max_concurrent = int(self._get_config('max_concurrent_tasks', 5))
        
        self.running_tasks.pop(task_id, None)
        if len(self.running_tasks) >= max_concurrent:
            error_msg = f"任务队列已满，无法启动任务 (当前运行: {len(self.running_tasks)}, 最大并发数: {max_concurrent})"
            self.start_errors[task_id] = error_msg
            task_logger.warning(error_msg)
            logger.warning(f"任务队列已满，无法启动任务: {task_id} (最大并发数: {max_concurrent})")
            return False
        
        task = Task.query.get(task_id)
        if not task:
            error_msg = "任务不存在"
            self.start_errors[task_id] = error_msg
            if acquired_token_id:
                get_google_sheet_token_service().release_usage(acquired_token_id)
                self.task_token_occupancy.pop(task_id, None)
            task_logger.error(error_msg)
            logger.error(f"任务不存在: {task_id}")
            return False
        
        if task.status != 'pending':
            error_msg = f"任务状态不是pending，当前状态: {task.status}"
            self.start_errors[task_id] = error_msg
            task_logger.warning(error_msg)
            logger.warning(f"任务状态不是pending，无法启动: {task_id}")
            return False

        try:
            config_data = json.loads(task.config) if isinstance(task.config, str) else (task.config or {})
            self._ensure_google_sheet_occupancy(task_id, config_data)
            token_id = config_data.get('token_id')
            if token_id:
                token_service = get_google_sheet_token_service()
                token_service.validate_task_start(config_data)
                token_service.increment_usage(token_id)
                acquired_token_id = int(token_id)
                self.task_token_occupancy[task_id] = acquired_token_id
        except Exception as e:
            error_msg = str(e)
            self.start_errors[task_id] = error_msg
            task_logger.warning(f"Token校验失败，无法启动任务: {error_msg}")
            logger.warning(f"Token校验失败，任务无法启动: {task_id}, {error_msg}")
            return False
        
        task_logger.info(f"开始启动任务 - 名称: {task.name}, 类型: {task.task_type}")
        
        # 创建事件队列
        self.task_events[task_id] = queue.Queue()
        self.task_stop_events[task_id] = threading.Event()
        task_logger.info("创建任务事件队列成功")

        app = current_app._get_current_object()
        
        # 根据任务类型启动相应的执行器
        if task.task_type == 'google_sheet':
            thread = threading.Thread(target=self._execute_google_sheet_task, args=(task_id, app),name=task_id)
            task_logger.info("创建Google Sheet任务执行线程")
        elif task.task_type == 'google_sheet_C4':
            thread = threading.Thread(target=self._execute_google_sheet_C4_task, args=(task_id, app),name=task_id)
            task_logger.info("创建Google Sheet C4 任务执行线程")
        elif task.task_type == 'google_sheet_C5':
            thread = threading.Thread(target=self._execute_google_sheet_C5_task, args=(task_id, app),name=task_id)
            task_logger.info("创建Google Sheet C5 任务执行线程")
        elif task.task_type == 'backtest_training':
            thread = threading.Thread(target=self._execute_backtest_training_task, args=(task_id, app),name=task_id)
            task_logger.info("创建回测数据训练任务执行线程")
        else:
            error_msg = f"不支持的任务类型: {task.task_type}"
            self.start_errors[task_id] = error_msg
            self.task_events.pop(task_id, None)
            self.task_stop_events.pop(task_id, None)
            self._release_task_token_occupancy(task_id)
            self._release_google_sheet_occupancy(task_id)
            task_logger.error(error_msg)
            logger.error(f"不支持的任务类型: {task.task_type}")
            return False
        
        # thread.daemon = True
        self.running_tasks[task_id] = thread
        try:
            thread.start()
        except Exception as e:
            self.running_tasks.pop(task_id, None)
            self.task_events.pop(task_id, None)
            self.task_stop_events.pop(task_id, None)
            self._release_task_token_occupancy(task_id)
            self._release_google_sheet_occupancy(task_id)
            error_msg = f"任务线程启动失败: {str(e)}"
            self.start_errors[task_id] = error_msg
            task_logger.error(error_msg)
            logger.error(f"任务线程启动失败: {task_id}, err={str(e)}")
            return False
        
        task_logger.info("任务执行线程启动成功")
        logger.info(f"启动任务: {task_id}")
        return True

    def _release_task_token_occupancy(self, task_id: str):
        # token 占用数是“运行中占用”，不是累计次数。
        # 因此任务在线程结束、报错或被取消时，需要在 finally 里统一释放。
        token_id = self.task_token_occupancy.pop(task_id, None)
        if token_id:
            try:
                get_google_sheet_token_service().release_usage(token_id)
            except Exception as e:
                logger.warning(f"release token occupancy failed: task_id={task_id}, token_id={token_id}, err={str(e)}")

    def _ensure_google_sheet_occupancy(self, task_id: str, config: Dict[str, Any] | None):
        if not isinstance(config, dict):
            return
        sheet_ids: list[int] = []

        direct_sheet_id = config.get('google_sheet_id')
        if direct_sheet_id:
            sheet_ids.append(int(direct_sheet_id))

        spreadsheet_id = config.get('spreadsheet_id')
        if spreadsheet_id:
            matched_sheet = GoogleSheet.query.filter_by(spreadsheet_id=str(spreadsheet_id)).first()
            if matched_sheet:
                sheet_ids.append(int(matched_sheet.id))

        sheets = config.get('sheets')
        if isinstance(sheets, list):
            for item in sheets:
                if not isinstance(item, dict):
                    continue
                item_sheet_id = item.get('google_sheet_id')
                if item_sheet_id:
                    sheet_ids.append(int(item_sheet_id))
                    continue
                item_spreadsheet_id = item.get('spreadsheet_id')
                if item_spreadsheet_id:
                    matched_sheet = GoogleSheet.query.filter_by(spreadsheet_id=str(item_spreadsheet_id)).first()
                    if matched_sheet:
                        sheet_ids.append(int(matched_sheet.id))

        for sheet_id in sorted(set(sheet_ids)):
            get_google_sheet_registry_service().acquire_for_task(sheet_id, task_id)

    def _release_google_sheet_occupancy(self, task_id: str):
        try:
            released = get_google_sheet_registry_service().release_for_task(task_id)
            if not released:
                task = Task.query.get(task_id)
                if task:
                    config_data = json.loads(task.config) if isinstance(task.config, str) else (task.config or {})
                    if isinstance(config_data, dict) and config_data.get('google_sheet_id'):
                        logger.warning(f"google sheet occupancy release skipped: task_id={task_id}, google_sheet_id={config_data.get('google_sheet_id')}")
        except Exception as e:
            logger.warning(f"release google sheet occupancy failed: task_id={task_id}, err={str(e)}")

    def get_start_error(self, task_id: str) -> str:
        return self.start_errors.get(task_id, '任务启动失败')

    @transaction_required
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = Task.query.get(task_id)
        if not task:
            return False

        if task.status in ['completed', 'cancelled', 'error']:
            return False

        was_pending = task.status == 'pending'
        stop_event = self.task_stop_events.get(task_id)
        if stop_event:
            stop_event.set()

        # 使用safe_update更新任务状态
        safe_update(task, commit=False, status='cancelled', end_time=datetime.now())

        # pending 状态的任务需要立即释放资源，因为没有运行线程
        if was_pending:
            self._release_task_token_occupancy(task_id)
            self._release_google_sheet_occupancy(task_id)

        # 清理资源

        self._add_task_log(task_id, 'info', f'任务已取消')
        logger.info(f"取消任务: {task_id}")
        return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = Task.query.get(task_id)
        if not task:
            return None
        
        return task.to_dict()
    
    def get_all_tasks(self, task_type: Optional[str] = None) -> list:
        """获取所有任务"""
        query = Task.query
        if task_type:
            query = query.filter_by(task_type=task_type)
        tasks = query.order_by(Task.created_at.desc()).all()
        return [task.to_dict() for task in tasks]

    def get_tasks_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页获取任务列表，并返回当前筛选条件下的统计信息。"""
        page = max(page or 1, 1)
        per_page = max(min(per_page or 10, 100), 1)

        query = Task.query
        if task_type:
            query = query.filter(Task.task_type == task_type)

        if status and status != 'all':
            query = query.filter(Task.status == status)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                pattern = f"%{keyword}%"
                query = query.filter(
                    or_(
                        Task.name.ilike(pattern),
                        Task.description.ilike(pattern),
                        Task.id.ilike(pattern),
                    )
                )

        ordered_query = query.order_by(Task.created_at.desc())
        pagination = ordered_query.paginate(page=page, per_page=per_page, error_out=False)
        items = [task.to_dict() for task in pagination.items]

        total = query.count()
        completed_tasks = query.filter(Task.status == 'completed').count()
        running_tasks = query.filter(Task.status == 'running').count()
        error_tasks = query.filter(Task.status == 'error').count()
        pending_tasks = query.filter(Task.status == 'pending', Task.current_step > 0).count()

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        today_new_tasks = query.filter(
            Task.created_at >= today_start,
            Task.created_at < tomorrow_start
        ).count()

        completed_with_duration = query.filter(
            Task.status == 'completed',
            Task.start_time.isnot(None),
            Task.end_time.isnot(None)
        ).all()
        duration_minutes = []
        for task in completed_with_duration:
            if task.start_time and task.end_time and task.end_time > task.start_time:
                duration_minutes.append((task.end_time - task.start_time).total_seconds() / 60)

        avg_duration_minutes = round(sum(duration_minutes) / len(duration_minutes)) if duration_minutes else 0
        success_rate = round((completed_tasks / (completed_tasks + error_tasks) * 100), 1) if (completed_tasks + error_tasks) > 0 else 0
        error_rate = round((error_tasks / total * 100), 1) if total > 0 else 0

        return {
            "tasks": items,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_prev": pagination.has_prev,
                "has_next": pagination.has_next,
            },
            "statistics": {
                "total_tasks": total,
                "completed_tasks": completed_tasks,
                "running_tasks": running_tasks,
                "error_tasks": error_tasks,
                "pending_tasks": pending_tasks,
                "today_new_tasks": today_new_tasks,
                "success_rate": success_rate,
                "error_rate": error_rate,
                "avg_duration_minutes": avg_duration_minutes,
            }
        }
    
    def check_local_task_status(self, task_id: str) -> Dict[str, Any]:
        """检查本地任务状态，识别可能挂死的任务"""
        task = Task.query.get(task_id)
        if not task:
            return {"status": "not_found", "message": "任务不存在"}
        
        # 检查数据库状态
        db_status = task.status

        if task_id in self.running_tasks:
            # 检查内存中是否还有运行的线程
            thread = self.running_tasks.get(task_id)

            memory_running = thread.is_alive()
        else:
            memory_running = False
        # 获取最新的任务结果
        latest_result = TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.timestamp.desc()).first()
        
        # 从日志文件获取最新的日志时间
        latest_log_time = None
        task_logs = self.get_task_logs(task_id)
        if task_logs:
            # get_task_logs 返回按时间正序排列的日志，最后一条是最新的
            latest_log_time = task_logs[-1]['timestamp']
        
        # 判断任务状态
        status_check = {
            "task_id": task_id,
            "db_status": db_status,
            "memory_running": memory_running,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "latest_result_time": latest_result.timestamp.isoformat() if latest_result else None,
            "latest_log_time": latest_log_time,
            "can_restart": False,
            "restart_reason": None
        }
        
        # 识别可能需要重启的情况
        if db_status == 'running' and not memory_running:
            status_check["can_restart"] = True
            status_check["restart_reason"] = "任务在数据库中显示为运行状态，但内存中没有对应的线程"
        elif db_status == 'running' and memory_running:
            # 检查是否长时间没有更新
            import datetime
            timeout_seconds = self._get_config('task_status_check_timeout', 600)  # 默认10分钟
            
            now = datetime.datetime.now()
            if latest_log_time:
                try:
                    # 将ISO格式时间字符串转换为datetime对象
                    latest_time = datetime.datetime.fromisoformat(latest_log_time)
                    time_diff = now - latest_time
                    if time_diff.total_seconds() > timeout_seconds:
                        timeout_minutes = timeout_seconds // 60
                        status_check["can_restart"] = True
                        status_check["restart_reason"] = f"任务超过{timeout_minutes}分钟没有日志更新，可能已挂死"
                except:
                    status_check["restart_reason"] = "任务正在正常运行"
            else:
                status_check["restart_reason"] = "任务正在正常运行"
        else:
            # 为非运行状态提供状态描述
            if db_status == 'pending':
                status_check["restart_reason"] = "任务处于待执行状态"
            elif db_status == 'completed':
                status_check["restart_reason"] = "任务已完成"
            elif db_status == 'error':
                status_check["restart_reason"] = "任务执行出错"
            elif db_status == 'cancelled':
                status_check["restart_reason"] = "任务已被取消"
            else:
                status_check["restart_reason"] = f"任务状态: {db_status}"
        
        return status_check
    
    def restart_task(self, task_id: str, resume_from_checkpoint: bool = True) -> Dict[str, Any]:
        """重启任务"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}
            
            # 检查任务状态
            status_check = self.check_local_task_status(task_id)
            
            # 检查是否可以重启（放宽条件，允许pending、completed、error、cancelled状态的任务重启）
            if task.status == 'running':
                # 如果任务正在运行，检查是否真的在运行
                if not status_check.get("can_restart", False):
                    return {"status": "error", "message": "任务正在运行中，无法重启"}
            elif task.status not in ['pending', 'completed', 'error', 'cancelled']:
                return {"status": "error", "message": f"任务状态 '{task.status}' 不允许重启"}
            
            # 停止现有任务（如果在运行）
            if task_id in self.running_tasks:
                try:
                    thread = self.running_tasks.get(task_id)
                    self.cancel_task(task_id)
                    if thread and thread.is_alive():
                        thread.join(timeout=3.0)
                    logger.info(f"已停止原有任务线程: {task_id}")
                except Exception as e:
                    logger.warning(f"停止原有任务线程失败: {str(e)}")
            
            # 清理任务状态
            alive_thread = self.running_tasks.get(task_id)
            if alive_thread and alive_thread.is_alive():
                return {"status": "error", "message": "task is still stopping, please retry shortly"}
            if task_id in self.task_events:
                del self.task_events[task_id]
            if task_id in self.task_stop_events:
                del self.task_stop_events[task_id]
            start_time = None
            # 根据断点恢复设置，决定从哪里开始
            if resume_from_checkpoint:
                # 从断点继续，保持current_step
                restart_step = task.current_step
                self._add_task_log(task_id, 'info', f'从断点重启任务，从第 {restart_step} 步继续')
                start_time = task.start_time
            else:
                # 从头开始：重置步骤并清空历史结果（保留日志）
                restart_step = 0
                task.current_step = 0

                # 删除该任务历史结果，避免新一轮执行与旧结果混淆
                self._release_task_token_occupancy(task_id)
                self._release_google_sheet_occupancy(task_id)
                TaskResult.query.filter_by(task_id=task_id).delete()
                db.session.commit()

                self._add_task_log(task_id, 'info', '重新开始任务，从第 1 步开始（已清空历史结果）')
            
            # 重置任务状态 - 清空开始和结束时间，确保重启后时间信息正确
            safe_update(task, commit=True, status='pending', error_message=None, start_time=start_time, end_time=None)
            
            # 重新启动任务
            success = self.start_task(task_id)
            
            if success:
                # 确定重启原因
                restart_reason = status_check.get("restart_reason")
                if not restart_reason:
                    if task.status == 'pending':
                        restart_reason = "用户手动重启待执行任务"
                    elif task.status == 'completed':
                        restart_reason = "用户手动重启已完成任务"
                    elif task.status == 'error':
                        restart_reason = "用户手动重启错误任务"
                    elif task.status == 'cancelled':
                        restart_reason = "用户手动重启已取消任务"
                    else:
                        restart_reason = "用户手动重启"
                
                self._add_task_log(task_id, 'info', f'任务重启成功，原因: {restart_reason}')
                return {
                    "status": "success", 
                    "message": "任务重启成功",
                    "restart_from_step": restart_step,
                    "restart_reason": restart_reason
                }
            else:
                return {"status": "error", "message": "任务重启失败"}
                
        except Exception as e:
            logger.error(f"重启任务失败: {task_id}, 错误: {str(e)}")
            return {"status": "error", "message": f"重启任务失败: {str(e)}"}
    
    def create_restart_task(self, original_task_id: str) -> str:
        """基于原任务创建新的重启任务"""
        try:
            original_task = Task.query.get(original_task_id)
            if not original_task:
                raise ValueError("原任务不存在")
            
            # 创建新的任务ID
            new_task_id = str(uuid.uuid4())
            
            # 复制原任务配置
            original_config = json.loads(original_task.config) if isinstance(original_task.config, str) else original_task.config
            original_config = self._normalize_task_config_for_type(original_task.task_type, original_config)
            
            # 创建新任务，名称添加重启标识
            new_task = Task(
                id=new_task_id,
                name=f"{original_task.name} (重启)",
                description=f"基于任务 {original_task_id} 重启",
                task_type=original_task.task_type,
                config=json.dumps(original_config),
                status='pending'
            )
            
            db.session.add(new_task)
            db.session.commit()

            if isinstance(original_config, dict):
                self._ensure_google_sheet_occupancy(new_task_id, original_config)
            
            logger.info(f"创建重启任务: {new_task_id} (基于 {original_task_id})")
            return new_task_id
            
        except Exception as e:
            logger.error(f"创建重启任务失败: {str(e)}")
            raise
    
    def get_task_logs(self, task_id: str, limit: int = 500) -> list:
        """获取任务日志（从数据库读取最新的日志）"""
        from app.models import TaskLog
        
        try:
            # 获取最新的limit条日志，按时间倒序获取，然后再正序返回
            logs = TaskLog.query.filter_by(task_id=task_id).order_by(TaskLog.timestamp.desc()).limit(limit).all()
            # 反转列表，使其按时间正序排列（最早的在前）
            logs.reverse()
            return [log.to_dict() for log in logs]
        except Exception as e:
            logger.error(f"获取任务日志失败: {str(e)}")
            return []
    
    def get_task_results(self, task_id: str, page: int | None = None, per_page: int | None = None):
        """获取任务结果

        如果提供 page 和 per_page，则使用数据库分页；
        否则返回该任务的所有结果列表。
        """
        query = TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.step_index.asc())

        if page is not None and per_page is not None:
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            items = [result.to_dict() for result in pagination.items]

            # 计算全局成功/失败数量（与分页无关，基于整个任务结果集）
            total = pagination.total
            success_total = query.filter_by(success=True).count()
            failed_total = total - success_total

            return {
                "items": items,
                "total": total,
                "pages": pagination.pages,
                "current_page": page,
                "per_page": per_page,
                "total_success": success_total,
                "total_failed": failed_total,
            }

        results = query.all()
        return [result.to_dict() for result in results]
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务及其相关数据"""
        try:
            with current_app.app_context():
                # 检查任务是否存在
                task = Task.query.get(task_id)
                if not task:
                    logger.warning(f"任务不存在: {task_id}")
                    return False
                
                # 如果任务正在运行，先取消任务
                if task.status == 'running':
                    # 直接更新状态，避免嵌套事务
                    task.status = 'cancelled'
                    task.end_time = datetime.now()
                    self._release_task_token_occupancy(task_id)
                self._release_google_sheet_occupancy(task_id)
                
                # 删除任务结果
                TaskResult.query.filter_by(task_id=task_id).delete()
                
                # 删除任务日志
                TaskLog.query.filter_by(task_id=task_id).delete()
                
                # 删除任务本身
                db.session.delete(task)
                
                # 提交事务
                db.session.commit()
                
                # 清理内存中的任务事件队列
                if task_id in self.task_events:
                    del self.task_events[task_id]
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                if task_id in self.task_stop_events:
                    self.task_stop_events[task_id].set()
                    del self.task_stop_events[task_id]
                
                logger.info(f"任务删除成功: {task_id}")
                return True
                
        except Exception as e:
            logger.error(f"删除任务失败: {task_id}, 错误: {str(e)}")
            db.session.rollback()
            return False
    
    @transaction_required
    def update_task_config(self, task_id: str, new_config: Dict[str, Any], update_name: str = None, update_description: str = None) -> Dict[str, Any]:
        """更新任务配置
        
        Args:
            task_id: 任务ID
            new_config: 新的配置字典
            update_name: 可选的新任务名称
            update_description: 可选的新任务描述
            
        Returns:
            包含状态和消息的字典
        """
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}
            
            # 只允许修改非运行中的任务
            if task.status == 'running':
                return {"status": "error", "message": "正在运行的任务无法直接修改配置，请先停止任务"}
            
            # 验证配置
            if not isinstance(new_config, dict):
                return {"status": "error", "message": "配置格式不正确"}
            
            # 确保配置被正确序列化
            new_config = self._normalize_task_config_for_type(task.task_type, new_config)

            old_config = json.loads(task.config) if task.config else {}
            old_google_sheet_id = old_config.get('google_sheet_id') if isinstance(old_config, dict) else None
            new_google_sheet_id = new_config.get('google_sheet_id')

            if old_google_sheet_id != new_google_sheet_id:
                if old_google_sheet_id:
                    self._release_google_sheet_occupancy(task_id)
                if new_google_sheet_id:
                    self._ensure_google_sheet_occupancy(task_id, new_config)

            config_str = json.dumps(new_config)
            
            # 更新配置
            task.config = config_str
            
            # 如果提供了新名称或描述，也更新
            if update_name:
                task.name = update_name
            if update_description:
                task.description = update_description
            
            db.session.commit()
            
            # 记录日志
            task_logger = get_task_logger(task_id, f"{__name__}.update_config")
            task_logger.info(f"任务配置已更新")
            
            self._add_task_log(task_id, 'info', '任务配置已更新')
            
            logger.info(f"任务配置更新成功: {task_id}")
            return {"status": "success", "message": "任务配置更新成功", "task": task.to_dict()}
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"更新任务配置失败: {task_id}, 错误: {str(e)}")
            return {"status": "error", "message": f"更新任务配置失败: {str(e)}"}
    
    def _execute_google_sheet_task(self, task_id: str, app):
        """执行Google Sheet任务"""
        # 创建任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.{task_id}")
        
        try:
            # 使用传递的应用实例创建应用上下文
            with app.app_context():
                task = Task.query.get(task_id)
                if not task:
                    task_logger.error("任务不存在")
                    return
                
                task_logger.info(f"开始执行Google Sheet任务: {task.name}")
                
                # 更新任务状态
                task.status = 'running'
                task.start_time = datetime.now()
                db.session.commit()
                
                self._add_task_log(task_id, 'info', '开始执行Google Sheet任务', app)
                
                # 创建Google Sheet服务
                config = task.config
                service = GoogleSheetService(config, task_id, self.task_events.get(task_id), app, self.task_stop_events.get(task_id))
                
                task_logger.info("开始执行任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                
                # 检查任务当前状态（可能在执行过程中被取消）
                task = Task.query.get(task_id)
                if task and task.status == 'cancelled':
                    # 任务已被取消，保持cancelled状态
                    task.end_time = datetime.now()
                    db.session.commit()
                    task_logger.info('任务执行完成，状态: cancelled（任务被取消）')
                    self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（任务被取消）', app)
                else:
                    # 根据执行结果更新状态
                    # task_result 可能是: 'completed', 'error', 'cancelled'
                    if task_result == 'cancelled':
                        # 任务在执行过程中被取消
                        task.status = 'cancelled'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: cancelled（执行过程中被取消）')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（执行过程中被取消）', app)
                    elif task_result == 'completed':
                        # 任务成功完成
                        task.status = 'completed'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: completed')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: completed', app)
                    else:
                        # 任务执行出错
                        task.status = 'error'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: error')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: error', app)
            
        except Exception as e:
            task_logger.exception(f"执行任务失败: {str(e)}")
            
            # 更新任务状态为错误
            try:
                with app.app_context():
                    task = Task.query.get(task_id)
                    if task:
                        task.status = 'error'
                        task.error_message = str(e)
                        task.end_time = datetime.now()
                        db.session.commit()
            except Exception as update_error:
                task_logger.error(f"更新任务状态失败: {str(update_error)}")
            
            self._add_task_log(task_id, 'error', f'任务执行失败: {str(e)}', app)
        
        finally:
            with app.app_context():
                self._release_task_token_occupancy(task_id)
                self._release_google_sheet_occupancy(task_id)
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
            if task_id in self.task_stop_events:
                del self.task_stop_events[task_id]
                task_logger.info("stop event cleaned")
                task_logger.info("清理任务事件队列")
            
            task_logger.info("任务执行器退出")

    def _execute_google_sheet_C4_task(self, task_id: str, app):
        """执行Google Sheet C4 任务"""
        # 创建任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.C4.{task_id}")
        
        try:
            # 使用传递的应用实例创建应用上下文
            with app.app_context():
                task = Task.query.get(task_id)
                if not task:
                    task_logger.error("任务不存在")
                    return
                
                task_logger.info(f"开始执行Google Sheet C4 任务: {task.name}")
                
                # 原子方式将任务置为 running，防止并发重复启动
                rows = Task.query.filter(
                    Task.id == task_id,
                    Task.status != 'running'
                ).update({
                    'status': 'running',
                    'start_time': datetime.now()
                }, synchronize_session=False)
                db.session.commit()
                if rows == 0:
                    task_logger.warning('任务已在运行，拒绝并发启动 (C4)')
                    self._add_task_log(task_id, 'warn', '任务已在运行，拒绝并发启动 (C4)', app)
                    return
                
                self._add_task_log(task_id, 'info', '开始执行Google Sheet C4 任务', app)
                
                # 创建Google Sheet C4 服务
                config = task.config
                service = GoogleSheetServiceC4(config, task_id, self.task_events.get(task_id), app, self.task_stop_events.get(task_id))
                
                task_logger.info("开始执行 C4 任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                
                # 检查任务当前状态（可能在执行过程中被取消）
                task = Task.query.get(task_id)
                if task and task.status == 'cancelled':
                    # 任务已被取消，保持cancelled状态
                    task.end_time = datetime.now()
                    db.session.commit()
                    task_logger.info('任务执行完成，状态: cancelled（任务被取消）')
                    self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（任务被取消）', app)
                else:
                    # 根据执行结果更新状态
                    # task_result 可能是: 'completed', 'error', 'cancelled'
                    if task_result == 'cancelled':
                        # 任务在执行过程中被取消
                        task.status = 'cancelled'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: cancelled（执行过程中被取消）')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（执行过程中被取消）', app)
                    elif task_result == 'completed':
                        # 任务成功完成
                        task.status = 'completed'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: completed')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: completed', app)
                    else:
                        # 任务执行出错
                        task.status = 'error'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: error')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: error', app)
        
        except Exception as e:
            task_logger.exception(f"执行 C4 任务失败: {str(e)}")
            
            # 更新任务状态为错误
            try:
                with app.app_context():
                    task = Task.query.get(task_id)
                    if task:
                        task.status = 'error'
                        task.error_message = str(e)
                        task.end_time = datetime.now()
                        db.session.commit()
            except Exception as update_error:
                task_logger.error(f"更新任务状态失败: {str(update_error)}")
            
            self._add_task_log(task_id, 'error', f'任务执行失败: {str(e)}', app)
        
        finally:
            with app.app_context():
                self._release_task_token_occupancy(task_id)
                self._release_google_sheet_occupancy(task_id)
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
            if task_id in self.task_stop_events:
                del self.task_stop_events[task_id]
                task_logger.info("stop event cleaned")
                task_logger.info("清理任务事件队列")
            
            task_logger.info("任务执行器退出")

    def _execute_google_sheet_C5_task(self, task_id: str, app):
        """执行Google Sheet C5 任务"""
        # 创建任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.C5.{task_id}")
        
        try:
            # 使用传递的应用实例创建应用上下文
            with app.app_context():
                task = Task.query.get(task_id)
                if not task:
                    task_logger.error("任务不存在")
                    return
                
                task_logger.info(f"开始执行Google Sheet C5 任务: {task.name}")
                
                # 原子方式将任务置为 running，防止并发重复启动
                rows = Task.query.filter(
                    Task.id == task_id,
                    Task.status != 'running'
                ).update({
                    'status': 'running',
                    'start_time': datetime.now()
                }, synchronize_session=False)
                db.session.commit()
                if rows == 0:
                    task_logger.warning('任务已在运行，拒绝并发启动 (C5)')
                    self._add_task_log(task_id, 'warn', '任务已在运行，拒绝并发启动 (C5)', app)
                    return
                
                self._add_task_log(task_id, 'info', '开始执行Google Sheet C5 任务', app)
                
                # 创建Google Sheet C5 服务
                config = task.config
                service = GoogleSheetServiceC5(config, task_id, self.task_events.get(task_id), app, self.task_stop_events.get(task_id))
                
                task_logger.info("开始执行 C5 任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                
                # 检查任务当前状态（可能在执行过程中被取消）
                task = Task.query.get(task_id)
                if task and task.status == 'cancelled':
                    # 任务已被取消，保持cancelled状态
                    task.end_time = datetime.now()
                    db.session.commit()
                    task_logger.info('任务执行完成，状态: cancelled（任务被取消）')
                    self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（任务被取消）', app)
                else:
                    # 根据执行结果更新状态
                    # task_result 可能是: 'completed', 'error', 'cancelled'
                    if task_result == 'cancelled':
                        # 任务在执行过程中被取消
                        task.status = 'cancelled'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: cancelled（执行过程中被取消）')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: cancelled（执行过程中被取消）', app)
                    elif task_result == 'completed':
                        # 任务成功完成
                        task.status = 'completed'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: completed')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: completed', app)
                    else:
                        # 任务执行出错
                        task.status = 'error'
                        task.end_time = datetime.now()
                        db.session.commit()
                        task_logger.info('任务执行完成，状态: error')
                        self._add_task_log(task_id, 'info', f'任务执行完成，状态: error', app)
        
        except Exception as e:
            task_logger.exception(f"执行 C5 任务失败: {str(e)}")
            
            # 更新任务状态为错误
            try:
                with app.app_context():
                    task = Task.query.get(task_id)
                    if task:
                        task.status = 'error'
                        task.error_message = str(e)
                        task.end_time = datetime.now()
                        db.session.commit()
            except Exception as update_error:
                task_logger.error(f"更新任务状态失败: {str(update_error)}")
            
            self._add_task_log(task_id, 'error', f'任务执行失败: {str(e)}', app)
        
        finally:
            with app.app_context():
                self._release_task_token_occupancy(task_id)
                self._release_google_sheet_occupancy(task_id)
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
            if task_id in self.task_stop_events:
                del self.task_stop_events[task_id]
                task_logger.info("stop event cleaned")
                task_logger.info("清理任务事件队列")
            
            task_logger.info("任务执行器退出")

    def _add_task_log(self, task_id: str, level: str, message: str, app=None):
        """添加任务日志"""
        from app.models import TaskLog
        
        try:
            if app:
                # 在后台线程中使用传递的应用实例
                with app.app_context():
                    log = TaskLog(
                        task_id=task_id,
                        level=level,
                        message=message
                    )
                    db.session.add(log)
                    db.session.commit()
            else:
                # 在主线程中使用当前应用上下文
                from flask import current_app
                with current_app.app_context():
                    log = TaskLog(
                        task_id=task_id,
                        level=level,
                        message=message
                    )
                    db.session.add(log)
                    db.session.commit()
        except Exception as e:
            logger.error(f"添加任务日志失败: {str(e)}")

    def _execute_backtest_training_task(self, task_id: str, app):
        """执行回测数据训练任务"""
        task_logger = get_task_logger(task_id, f"{__name__}.backtest.{task_id}")

        try:
            with app.app_context():
                task = Task.query.get(task_id)
                if not task:
                    task_logger.error("任务不存在")
                    return

                task_logger.info(f"开始执行回测数据训练任务: {task.name}")

                rows = Task.query.filter(
                    Task.id == task_id,
                    Task.status != 'running'
                ).update({
                    'status': 'running',
                    'start_time': datetime.now()
                }, synchronize_session=False)
                db.session.commit()
                if rows == 0:
                    task_logger.warning('任务已在运行，拒绝并发启动')
                    self._add_task_log(task_id, 'warn', '任务已在运行，拒绝并发启动', app)
                    return

                self._add_task_log(task_id, 'info', '开始执行回测数据训练任务', app)

                from app.services.backtest_training_service import BacktestTrainingService
                config = task.config
                service = BacktestTrainingService(config, task_id, self.task_events.get(task_id), app, self.task_stop_events.get(task_id))

                task_result = service.execute_task()

                task = Task.query.get(task_id)
                if task and task.status == 'cancelled':
                    task.end_time = datetime.now()
                    db.session.commit()
                    task_logger.info('任务执行完成，状态: cancelled')
                    self._add_task_log(task_id, 'info', '任务执行完成，状态: cancelled', app)
                else:
                    if task_result == 'cancelled':
                        status = 'cancelled'
                    elif task_result == 'completed':
                        status = 'completed'
                    else:
                        status = 'error'
                    safe_update(Task, task_id, status=status, end_time=datetime.now())
                    task_logger.info(f'任务执行完成，状态: {status}')
                    self._add_task_log(task_id, 'info', f'任务执行完成，状态: {status}', app)

        except Exception as e:
            task_logger.error(f"任务执行失败: {str(e)}")
            self._add_task_log(task_id, 'error', f'任务执行失败: {str(e)}', app)
            safe_update(Task, task_id, status='error', end_time=datetime.now())
        finally:
            self.running_tasks.pop(task_id, None)
            self.task_events.pop(task_id, None)
            self.task_stop_events.pop(task_id, None)
            self._release_task_token_occupancy(task_id)
            self._release_google_sheet_occupancy(task_id)

# 全局任务管理器实例
task_manager = TaskManager()
