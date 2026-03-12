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

logger = get_logger(__name__)

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.running_tasks: Dict[str, threading.Thread] = {}
        self.task_events: Dict[str, queue.Queue] = {}
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
        
        if len(self.running_tasks) >= max_concurrent:
            error_msg = f"任务队列已满，无法启动任务 (当前运行: {len(self.running_tasks)}, 最大并发数: {max_concurrent})"
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
        self.task_events[task_id] = queue.Queue()
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
        self.running_tasks[task_id] = thread
        thread.start()
        
        task_logger.info("任务执行线程启动成功")
        logger.info(f"启动任务: {task_id}")
        return True

    @transaction_required
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = Task.query.get(task_id)
        if not task:
            return False
        
        if task.status in ['completed', 'cancelled', 'error']:
            return False
        
        # 使用safe_update更新任务状态
        safe_update(task, commit=False, status='cancelled', end_time=datetime.now())
        
        # 清理资源
        if task_id in self.running_tasks:
            del self.running_tasks[task_id]
        if task_id in self.task_events:
            del self.task_events[task_id]
        
        self._add_task_log(task_id, 'info', f'任务已取消')
        logger.info(f"取消任务: {task_id}")
        return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """???????"""
        # ??????????????? TaskManager ????????????
        return task_query_service.get_task_status(task_id)

    def get_all_tasks(self, task_type: Optional[str] = None) -> list:
        """???????"""
        # ????????????????????????????
        return task_query_service.get_all_tasks(task_type=task_type)

    def check_local_task_status(self, task_id: str) -> Dict[str, Any]:
        """???????????????????"""
        # ???? TaskManager ??????????????????????????????
        return task_query_service.check_local_task_status(
            task_id=task_id,
            running_tasks=self.running_tasks,
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
                    self.cancel_task(task_id)
                    logger.info(f"已停止原有任务线程: {task_id}")
                except Exception as e:
                    logger.warning(f"停止原有任务线程失败: {str(e)}")
            
            # 清理任务状态
            if task_id in self.task_events:
                del self.task_events[task_id]
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

                # 删除该任务历史结果，避免新一轮执行与旧结果混淆。
                task_repository.delete_task_results(task_id)

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
        """???????"""
        # ??????????? API ? RESTX ??????????
        return task_query_service.get_task_logs(task_id=task_id, limit=limit)

    def get_task_results(self, task_id: str, page: int | None = None, per_page: int | None = None):
        """???????"""
        # ???????????????????????????????
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
                if task_id in self.task_events:
                    del self.task_events[task_id]
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                
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
            if not task:
                return {"status": "error", "message": "任务不存在"}
            
            # 只允许修改非运行中的任务
            if task.status == 'running':
                return {"status": "error", "message": "正在运行的任务无法直接修改配置，请先停止任务"}
            
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
                service = GoogleSheetService(config, task_id, self.task_events.get(task_id), app)
                
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
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
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
                service = GoogleSheetServiceC4(config, task_id, self.task_events.get(task_id), app)
                
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
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
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
                service = GoogleSheetServiceC5(config, task_id, self.task_events.get(task_id), app)
                
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
            # 清理资源
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
                task_logger.info("清理任务线程资源")
            if task_id in self.task_events:
                del self.task_events[task_id]
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
    

# 全局任务管理器实例
task_manager = TaskManager()
