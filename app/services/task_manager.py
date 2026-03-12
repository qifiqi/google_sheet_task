import uuid
import threading
import queue
import json
# 获取当前应用实例，传递给后台线程
from flask import current_app
from datetime import datetime
from typing import Dict, Any, Optional
from app.models import Task, TaskResult, db
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_service_C4 import GoogleSheetService as GoogleSheetServiceC4
from app.services.google_sheet_service_C5 import GoogleSheetService as GoogleSheetServiceC5
from app.utils.logger import get_logger, get_task_logger
from app.utils.database import transaction_required, safe_update
from app.services.config_manager import get_config_manager
from app.services.config_schema import normalize_task_config, validate_task_config
from app.services.task_query_service import task_query_service
from app.services.task_repository import task_repository
from app.services.task_runtime_registry import task_runtime_registry
from app.services.task_status_service import task_status_service

logger = get_logger(__name__)

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        # 保留属性名用于兼容既有调用，实际运行态资源交给注册表维护。
        self.running_tasks = task_runtime_registry.running_tasks
        self.task_events = task_runtime_registry.task_events
        # 不再在初始化时缓存配置，而是每次动态获取
    
    def _get_config(self, key: str, default: Any = None) -> Any:
        """动态获取配置，确保实时生效"""
        config_manager = get_config_manager()
        return config_manager.get_config(key, default)
    
    @transaction_required
    def create_task(self, name: str, description: str, task_type: str, config: Dict[str, Any]) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        
        # 确保配置被正确序列化
        normalized_config = normalize_task_config(config, task_type=task_type)
        validate_task_config(normalized_config, task_type=task_type)
        config_str = json.dumps(normalized_config) if isinstance(normalized_config, dict) else str(normalized_config)
        
        # 任务落库统一交给仓储层，TaskManager 只保留编排和校验职责。
        task = task_repository.create_task(
            task_id=task_id,
            name=name,
            description=description,
            task_type=task_type,
            config_str=config_str,
            status='pending',
        )
        
        # 使用任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.create")
        task_logger.info(f"创建任务成功 - 名称: {name}, 类型: {task_type}, 配置项数量: {len(config) if isinstance(config, dict) else 'N/A'}")
        
        logger.info(f"创建任务: {task_id} - {name}")
        return task_id
    
    def start_task(self, task_id: str) -> bool:
        """启动任务"""
        # 创建任务专用日志记录器
        task_logger = get_task_logger(task_id, f"{__name__}.start")
        
        # 动态获取最大并发任务数配置，确保实时生效
        max_concurrent = int(self._get_config('max_concurrent_tasks', 5))
        
        running_count = task_runtime_registry.count_running_tasks()
        if running_count >= max_concurrent:
            error_msg = f"任务队列已满，无法启动任务 (当前运行: {running_count}, 最大并发数: {max_concurrent})"
            task_logger.warning(error_msg)
            logger.warning(f"任务队列已满，无法启动任务: {task_id} (最大并发数: {max_concurrent})")
            return False
        
        task = Task.query.get(task_id)
        if not task:
            error_msg = "任务不存在"
            task_logger.error(error_msg)
            logger.error(f"任务不存在: {task_id}")
            return False
        
        if task.status != 'pending':
            error_msg = f"任务状态不是pending，当前状态: {task.status}"
            task_logger.warning(error_msg)
            logger.warning(f"任务状态不是pending，无法启动: {task_id}")
            return False
        
        task_logger.info(f"开始启动任务 - 名称: {task.name}, 类型: {task.task_type}")
        
        # 创建事件队列
        task_runtime_registry.create_task_event_queue(task_id)
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
        else:
            error_msg = f"不支持的任务类型: {task.task_type}"
            task_logger.error(error_msg)
            logger.error(f"不支持的任务类型: {task.task_type}")
            return False
        
        # thread.daemon = True
        task_runtime_registry.register_thread(task_id, thread)
        thread.start()
        
        task_logger.info("任务执行线程启动成功")
        logger.info(f"启动任务: {task_id}")
        return True

    @transaction_required
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = Task.query.get(task_id)
        if not task_status_service.can_cancel(task):
            return False
        
        # 使用safe_update更新任务状态
        safe_update(task, commit=False, status='cancelled', end_time=datetime.now())
        
        # 清理资源
        task_runtime_registry.clear_task_runtime(task_id)
        
        self._add_task_log(task_id, 'info', f'任务已取消')
        logger.info(f"取消任务: {task_id}")
        return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务详情状态。"""
        # 查询能力已下沉到查询服务，这里保留兼容入口。
        return task_query_service.get_task_status(task_id)

    def get_all_tasks(self, task_type: Optional[str] = None) -> list:
        """获取任务列表。"""
        # 列表查询统一委托给查询服务，避免管理器继续膨胀。
        return task_query_service.get_all_tasks(task_type=task_type)

    def check_local_task_status(self, task_id: str) -> Dict[str, Any]:
        """检查任务在本地运行态中的真实状态。"""
        # 运行态判断依赖注册表和日志能力，这里只做参数转发与兼容。
        return task_query_service.check_local_task_status(
            task_id=task_id,
            running_tasks=task_runtime_registry.running_tasks,
            get_task_logs=self.get_task_logs,
            get_config=self._get_config,
        )

    def restart_task(self, task_id: str, resume_from_checkpoint: bool = True) -> Dict[str, Any]:
        """重启任务"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}

            # 检查任务状态
            status_check = self.check_local_task_status(task_id)
            restart_validation = task_status_service.validate_restart(task, status_check)
            if restart_validation["status"] != "success":
                return restart_validation
            
            # 停止现有任务（如果在运行）
            if task_id in self.running_tasks:
                try:
                    self.cancel_task(task_id)
                    logger.info(f"已停止原有任务线程: {task_id}")
                except Exception as e:
                    logger.warning(f"停止原有任务线程失败: {str(e)}")
            
            # 清理任务状态
            task_runtime_registry.remove_task_event_queue(task_id)
            restart_plan = task_status_service.build_restart_plan(task, resume_from_checkpoint)
            if restart_plan["reset_current_step"]:
                task.current_step = 0

            # 根据重启计划决定是否清理历史结果。
            if restart_plan["clear_history_results"]:
                # 删除该任务历史结果，避免新一轮执行与旧结果混淆。
                task_repository.delete_task_results(task_id)

            self._add_task_log(task_id, 'info', restart_plan["log_message"])
            
            # 重置任务状态 - 清空开始和结束时间，确保重启后时间信息正确
            safe_update(
                task,
                commit=True,
                status='pending',
                error_message=None,
                start_time=restart_plan["start_time"],
                end_time=None,
            )
            
            # 重新启动任务
            success = self.start_task(task_id)
            
            if success:
                restart_reason = restart_validation["restart_reason"]
                self._add_task_log(task_id, 'info', f'任务重启成功，原因: {restart_reason}')
                return {
                    "status": "success", 
                    "message": "任务重启成功",
                    "restart_from_step": restart_plan["restart_step"],
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
            original_task = task_repository.get_task(original_task_id)
            if not original_task:
                raise ValueError("原任务不存在")
            
            # 创建新的任务ID
            new_task_id = str(uuid.uuid4())
            
            # 重启任务复制逻辑下沉到仓储层，避免 TaskManager 直接拼装模型。
            task_repository.create_restart_task(original_task, new_task_id)
            
            logger.info(f"创建重启任务: {new_task_id} (基于 {original_task_id})")
            return new_task_id
            
        except Exception as e:
            logger.error(f"创建重启任务失败: {str(e)}")
            raise
    
    def get_task_logs(self, task_id: str, limit: int = 500) -> list:
        """获取任务日志。"""
        # 统一走查询服务，避免 API 与历史调用各自维护一套实现。
        return task_query_service.get_task_logs(task_id=task_id, limit=limit)

    def get_task_results(self, task_id: str, page: int | None = None, per_page: int | None = None):
        """获取任务结果。"""
        # 结果查询支持分页，具体聚合逻辑统一收敛到查询服务。
        return task_query_service.get_task_results(task_id=task_id, page=page, per_page=per_page)

    def delete_task(self, task_id: str) -> bool:
        """删除任务及其相关数据"""
        try:
            with current_app.app_context():
                # 检查任务是否存在
                task = task_repository.get_task(task_id)
                if not task:
                    logger.warning(f"任务不存在: {task_id}")
                    return False
                
                # 如果任务正在运行，先取消任务
                if task.status == 'running':
                    # 直接更新状态，避免嵌套事务
                    task.status = 'cancelled'
                    task.end_time = datetime.now()
                
                # 级联删除交给仓储层，减少 TaskManager 中的持久化细节。
                task_repository.delete_task_with_relations(task)
                
                # 清理内存中的任务事件队列
                task_runtime_registry.clear_task_runtime(task_id)
                
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
            task = task_repository.get_task(task_id)
            status_validation = task_status_service.validate_config_update(task)
            if status_validation["status"] != "success":
                return status_validation
            
            # 验证配置
            if not isinstance(new_config, dict):
                return {"status": "error", "message": "配置格式不正确"}
            
            # 确保配置被正确序列化
            normalized_config = normalize_task_config(new_config, task_type=task.task_type)
            validate_task_config(normalized_config, task_type=task.task_type)
            config_str = json.dumps(normalized_config)
            
            # 配置写回统一走仓储层，便于后续继续拆分写侧职责。
            task = task_repository.update_task_config(
                task,
                config_str,
                update_name=update_name,
                update_description=update_description,
            )
            
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

    def _finalize_task_execution(self, task_id: str, task_result: str, task_logger, app) -> None:
        """根据执行结果统一回写任务最终状态。"""
        task = Task.query.get(task_id)
        if not task:
            task_logger.warning("任务执行结束时未找到任务记录，跳过状态回写")
            return

        if task.status == 'cancelled':
            task.end_time = datetime.now()
            db.session.commit()
            message = '任务执行完成，状态: cancelled（任务被取消）'
        elif task_result == 'cancelled':
            task.status = 'cancelled'
            task.end_time = datetime.now()
            db.session.commit()
            message = '任务执行完成，状态: cancelled（执行过程中被取消）'
        elif task_result == 'completed':
            task.status = 'completed'
            task.end_time = datetime.now()
            db.session.commit()
            message = '任务执行完成，状态: completed'
        else:
            task.status = 'error'
            task.end_time = datetime.now()
            db.session.commit()
            message = '任务执行完成，状态: error'

        task_logger.info(message)
        self._add_task_log(task_id, 'info', message, app)

    def _mark_task_error(self, task_id: str, error: Exception, task_logger, app) -> None:
        """统一处理执行器异常状态落库与日志记录。"""
        try:
            with app.app_context():
                task = Task.query.get(task_id)
                if task:
                    task.status = 'error'
                    task.error_message = str(error)
                    task.end_time = datetime.now()
                    db.session.commit()
        except Exception as update_error:
            task_logger.error(f"更新任务状态失败: {str(update_error)}")

        self._add_task_log(task_id, 'error', f'任务执行失败: {str(error)}', app)

    def _cleanup_task_runtime(self, task_id: str, task_logger) -> None:
        """统一清理线程登记和事件队列。"""
        if task_runtime_registry.has_thread(task_id):
            task_runtime_registry.remove_thread(task_id)
            task_logger.info("清理任务线程资源")
        if task_runtime_registry.has_task_event_queue(task_id):
            task_runtime_registry.remove_task_event_queue(task_id)
            task_logger.info("清理任务事件队列")

        task_logger.info("任务执行器退出")
    
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
                service = GoogleSheetService(config, task_id, task_runtime_registry.get_task_event_queue(task_id), app)
                
                task_logger.info("开始执行任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                self._finalize_task_execution(task_id, task_result, task_logger, app)
            
        except Exception as e:
            task_logger.exception(f"执行任务失败: {str(e)}")
            self._mark_task_error(task_id, e, task_logger, app)
        
        finally:
            self._cleanup_task_runtime(task_id, task_logger)

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
                service = GoogleSheetServiceC4(config, task_id, task_runtime_registry.get_task_event_queue(task_id), app)
                
                task_logger.info("开始执行 C4 任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                self._finalize_task_execution(task_id, task_result, task_logger, app)
        
        except Exception as e:
            task_logger.exception(f"执行 C4 任务失败: {str(e)}")
            self._mark_task_error(task_id, e, task_logger, app)
        
        finally:
            self._cleanup_task_runtime(task_id, task_logger)

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
                service = GoogleSheetServiceC5(config, task_id, task_runtime_registry.get_task_event_queue(task_id), app)
                
                task_logger.info("开始执行 C5 任务业务逻辑")
                
                # 执行任务
                task_result = service.execute_task()
                self._finalize_task_execution(task_id, task_result, task_logger, app)
        
        except Exception as e:
            task_logger.exception(f"执行 C5 任务失败: {str(e)}")
            self._mark_task_error(task_id, e, task_logger, app)
        
        finally:
            self._cleanup_task_runtime(task_id, task_logger)

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
    

# 全局任务管理器实例
task_manager = TaskManager()
