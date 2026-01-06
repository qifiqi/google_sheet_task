import logging
import logging.handlers
import threading
from pathlib import Path
from app.config import Config

# 全局日志器锁，防止并发创建日志器
_logger_lock = threading.Lock()
_loggers_created = set()


class WindowsSafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """在 Windows 下忽略轮转时的文件占用错误，避免刷屏异常。

    不改变标准按天切割行为，只是在 rename 时捕获 PermissionError。
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except PermissionError as e:
            # 另一进程可能持有同一个日志文件；忽略本次轮转，继续写当前文件
            pass


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    with _logger_lock:
        logger = logging.getLogger(name)

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

    # 尝试创建文件处理器，如果失败则使用控制台处理器
    file_handler = None
    try:
        # 使用带简单容错的按天轮转处理器（Windows 下忽略文件占用导致的轮转错误）
        file_handler = WindowsSafeTimedRotatingFileHandler(
            filename=Config.LOG_FILE,
            when='midnight',  # 每天午夜切割
            interval=1,  # 间隔1天
            backupCount=30,  # 保留30天的日志
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
    except Exception as e:
        print(f"创建日志文件处理器失败: {e}")
        print("将仅使用控制台输出")

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 添加处理器
    if file_handler:
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


def initialize_logging():
    """初始化日志系统：创建主日志器并记录一条启动日志"""
    try:
        main_logger = get_logger('main')
        main_logger.info("日志系统初始化成功")
    except Exception as e:
        print(f"日志系统初始化失败: {e}")