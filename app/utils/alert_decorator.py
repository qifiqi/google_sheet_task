from functools import wraps
from typing import Any, Callable, Optional

from flask import current_app, has_app_context

from app.utils.logger import get_logger


logger = get_logger(__name__)


AlertMessageBuilder = Callable[[Any, str, str, Optional[BaseException], Any], str]
AlertResultPredicate = Callable[[Any], bool]


def _resolve_app(target: Any):
    """从执行对象或当前上下文中解析 Flask 应用实例。"""
    app = getattr(target, "app", None)
    if app is not None:
        return app

    if has_app_context():
        try:
            return current_app._get_current_object()
        except Exception:
            return None

    return None


def _resolve_notifier(target: Any):
    """从应用对象中解析可发送通知的告警器。"""
    app = _resolve_app(target)
    return getattr(app, "notifier", None) if app else None


def _resolve_task_label(target: Any) -> str:
    """生成用于告警日志的任务标识文本。"""
    task_id = getattr(target, "task_id", "unknown-task")
    task_name = getattr(target, "task_name", "") or task_id
    return f"{task_id} -- {task_name}"


def _resolve_task_url(target: Any) -> str:
    """生成任务详情页链接，无法生成时返回空文本。"""
    app = _resolve_app(target)
    if not app:
        return ""

    base_url = app.config.get("BASE_URL", "").rstrip("/")
    task_id = getattr(target, "task_id", "")
    if not base_url or not task_id:
        return ""

    return f"{base_url}/google-sheet/detail?task_id={task_id}"


def _default_message_builder(
    target: Any,
    func_name: str,
    phase: str,
    exc: Optional[BaseException],
    result: Any,
) -> str:
    """为异常或失败结果生成默认告警摘要。"""
    if exc is not None:
        return f"{func_name} 执行异常: {type(exc).__name__}: {exc}"
    return f"{func_name} 执行结果触发告警，phase={phase}, result={result!r}"


def send_failure_alert(
    target: Any,
    message: str,
    *,
    source: str = "",
) -> bool:
    """在任务执行失败时向已配置的通知器发送告警。"""
    notifier = _resolve_notifier(target)
    if notifier is None:
        logger.warning(f"发送告警失败: 未找到 notifier, source={source}, message={message}")
        return False

    try:
        result = notifier.send_task_notification(
            getattr(target, "task_id", ""),
            notify_type="error",
            summary=message,
            detail_url=_resolve_task_url(target),
        )
        ok = isinstance(result, dict) and result.get("errcode") in (None, 0) and "error" not in result

        if ok:
            logger.info(f"告警发送成功: source={source}, task={_resolve_task_label(target)}")
        else:
            logger.error(f"告警发送失败: source={source}, task={_resolve_task_label(target)}, result={result}")

        return ok
    except Exception as exc:
        logger.error(f"发送告警异常: source={source}, message={message}, error={exc}", exc_info=True)
        return False


def alert_on_failure(
    *,
    result_predicate: Optional[AlertResultPredicate] = None,
    message_builder: Optional[AlertMessageBuilder] = None,
    source_name: Optional[str] = None,
) -> Callable:
    """
    通用失败告警装饰器。

    用法:
        @alert_on_failure()
        def execute_task(...):
            ...

        @alert_on_failure(
            result_predicate=lambda result: result == "error",
            message_builder=lambda self, func, phase, exc, result: f"{func} 返回失败状态: {result}"
        )
        def execute_task(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        """包装目标函数，在异常或失败结果时统一发送告警。"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            """执行目标函数并捕获需要通知的失败情况。"""
            target = args[0] if args else None
            alert_source = source_name or func.__name__
            build_message = message_builder or _default_message_builder

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                message = build_message(target, func.__name__, "exception", exc, None)
                send_failure_alert(target, message, source=alert_source)
                raise

            if result_predicate and result_predicate(result):
                message = build_message(target, func.__name__, "result", None, result)
                send_failure_alert(target, message, source=alert_source)

            return result

        return wrapper

    return decorator
