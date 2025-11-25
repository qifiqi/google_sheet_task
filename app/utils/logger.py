import logging
import logging.handlers
import os
import time
import threading
from pathlib import Path
from app.config import Config
from typing import Optional

# 全局日志器锁，防止并发创建日志器
_logger_lock = threading.Lock()
_loggers_created = set()

# 尝试导入concurrent-log-handler，如果没有安装则使用标准库
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    HAS_CONCURRENT_LOG_HANDLER = True
except ImportError:
    HAS_CONCURRENT_LOG_HANDLER = False
    print("建议安装 concurrent-log-handler 以获得更好的日志轮转支持: pip install concurrent-log-handler")


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    with _logger_lock:
        logger = logging.getLogger(name)

        # 如果logger已经有处理器，直接返回
        if logger.handlers:
            return logger
        
        # 防止重复创建相同名称的日志器
        if name in _loggers_created:
            return logger
        
        _loggers_created.add(name)

        # 设置日志级别
        logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))

        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 确保日志目录存在
        log_path = Path(Config.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 尝试创建文件处理器
        file_handler = None
        try:
            if HAS_CONCURRENT_LOG_HANDLER:
                # 使用concurrent-log-handler，专门处理多进程日志轮转
                file_handler = ConcurrentRotatingFileHandler(
                    filename=Config.LOG_FILE,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=30,  # 保留30个备份文件
                    encoding='utf-8'
                )
            else:
                # 回退到标准库的RotatingFileHandler
                file_handler = logging.handlers.RotatingFileHandler(
                    filename=Config.LOG_FILE,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=30,  # 保留30个备份文件
                    encoding='utf-8'
                )
            
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            
        except Exception as e:
            print(f"创建日志文件处理器失败: {e}")
            print("将仅使用控制台输出")
            file_handler = None  # 确保file_handler为None

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # 添加处理器
        if file_handler is not None:
            logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # 关键修复：阻止向父级logger传播，避免重复日志
        logger.propagate = False

        return logger


class TaskLogger:
    """任务专用日志记录器，自动添加任务ID前缀"""
    
    def __init__(self, task_id: str, logger_name: str = None):
        self.task_id = task_id
        self.logger = get_logger(logger_name or __name__)
        self.prefix = f"[Task-{task_id[:8]}]"  # 使用任务ID前8位作为前缀
    
    def _format_message(self, message: str) -> str:
        """格式化消息，添加任务ID前缀"""
        return f"{self.prefix} {message}"
    
    def debug(self, message: str):
        """记录debug级别日志"""
        self.logger.debug(self._format_message(message))
    
    def info(self, message: str):
        """记录info级别日志"""
        self.logger.info(self._format_message(message))
    
    def warning(self, message: str):
        """记录warning级别日志"""
        self.logger.warning(self._format_message(message))
    
    def error(self, message: str):
        """记录error级别日志"""
        self.logger.error(self._format_message(message))
    
    def exception(self, message: str):
        """记录异常信息"""
        self.logger.exception(self._format_message(message))
    
    def step_info(self, step: int, total: int, message: str):
        """记录执行步骤信息"""
        step_msg = f"[Step {step}/{total}] {message}"
        self.info(step_msg)
    
    def progress_info(self, percentage: float, message: str):
        """记录进度信息"""
        progress_msg = f"[Progress {percentage:.1f}%] {message}"
        self.info(progress_msg)
    
    def api_info(self, action: str, details: str = ""):
        """记录API调用信息"""
        api_msg = f"[API] {action}"
        if details:
            api_msg += f" - {details}"
        self.info(api_msg)
    
    def api_error(self, action: str, error: str):
        """记录API错误信息"""
        api_msg = f"[API_ERROR] {action} - {error}"
        self.error(api_msg)


def get_task_logger(task_id: str, logger_name: str = None) -> TaskLogger:
    """获取任务专用日志记录器"""
    return TaskLogger(task_id, logger_name)


def cleanup_log_files():
    """清理可能被锁定的日志文件"""
    try:
        log_path = Path(Config.LOG_FILE)
        if log_path.exists():
            # 尝试重命名当前日志文件，如果失败说明被锁定
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_name = log_path.parent / f"{log_path.stem}_backup_{timestamp}{log_path.suffix}"
            
            try:
                log_path.rename(backup_name)
                print(f"已备份日志文件到: {backup_name}")
            except (PermissionError, OSError):
                print("日志文件正在被使用，跳过备份")
    except Exception as e:
        print(f"清理日志文件时出错: {e}")


def initialize_logging():
    """初始化日志系统，处理启动时的日志问题"""
    try:
        # 清理可能被锁定的日志文件
        cleanup_log_files()
        
        # 创建主日志器
        main_logger = get_logger('main')
        main_logger.info("日志系统初始化成功")
        
    except Exception as e:
        print(f"日志系统初始化失败: {e}")
        print("将使用控制台输出作为备选方案")