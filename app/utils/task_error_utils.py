from __future__ import annotations

from http.client import RemoteDisconnected
from typing import Iterator

from requests.exceptions import ConnectionError, RequestException, Timeout
from tenacity import RetryError
from urllib3.exceptions import ProtocolError

NETWORK_ERROR_PREFIX = "[NETWORK_RETRYABLE]"
WATCHDOG_RESTART_PREFIX = "[WATCHDOG_FORCE_RESTART]"
GOOGLE_SHEET_EXECUTION_ERROR_PREFIX = "[GOOGLE_SHEET_RETRYABLE]"
C3_EXECUTION_ERROR_PREFIX = GOOGLE_SHEET_EXECUTION_ERROR_PREFIX


class RetryableNetworkTaskError(Exception):
    """A network-layer error that is safe for the watchdog to auto-restart."""


def iter_exception_chain(exc: BaseException | None) -> Iterator[BaseException]:
    """按异常因果链依次遍历原始异常及其包装异常。"""
    seen: set[int] = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current

        if isinstance(current, RetryError):
            last_attempt = getattr(current, "last_attempt", None)
            inner = None
            if last_attempt is not None:
                try:
                    inner = last_attempt.exception()
                except Exception:
                    inner = None
            current = inner or getattr(current, "__cause__", None) or getattr(current, "__context__", None)
            continue

        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)


def unwrap_exception(exc: BaseException | None) -> BaseException | None:
    """返回异常链中最底层、最接近真实故障原因的异常。"""
    last = None
    for last in iter_exception_chain(exc):
        pass
    return last or exc


def is_retryable_network_error(exc: BaseException | None) -> bool:
    """判断异常链是否包含可重试的网络类失败。"""
    if exc is None:
        return False

    try:
        from gspread.exceptions import APIError as GSpreadAPIError
    except Exception:
        GSpreadAPIError = None

    network_types = (ConnectionError, RequestException, Timeout, ProtocolError, RemoteDisconnected)
    network_keywords = (
        "connection",
        "disconnected",
        "aborted",
        "remote end",
        "protocol error",
        "network",
        "timeout",
        "timed out",
        "broken pipe",
        "connection reset",
        "temporarily unavailable",
        "service unavailable",
    )

    for item in iter_exception_chain(exc):
        if isinstance(item, RetryableNetworkTaskError):
            return True
        if isinstance(item, network_types):
            return True
        if GSpreadAPIError is not None and isinstance(item, GSpreadAPIError):
            resp = getattr(item, "response", None)
            status = getattr(resp, "status_code", None)
            if isinstance(status, int) and (status == 429 or status >= 500):
                return True
        error_text = str(item).lower()
        if any(keyword in error_text for keyword in network_keywords):
            return True

    return False


def _retry_error_finished_with_failed_result(error: RetryError) -> bool:
    """判断 tenacity 重试耗尽是否由无效结果而非异常触发。"""
    last_attempt = getattr(error, "last_attempt", None)
    if last_attempt is None:
        return False

    try:
        result = last_attempt.result()
    except Exception:
        return False

    if result is False:
        return True
    if isinstance(result, (tuple, list)) and result:
        return result[0] is False
    return False


def is_retryable_google_sheet_execution_error(exc: BaseException | None) -> bool:
    """判断 Google Sheet 参数执行多次重试后仍未取得有效结果的异常。"""
    if exc is None:
        return False

    timeout_keywords = (
        "执行超时",
        "未在规定时间内完成",
        "结果验证失败",
        "无效值",
    )
    for item in iter_exception_chain(exc):
        if isinstance(item, RetryError) and _retry_error_finished_with_failed_result(item):
            return True
        error_text = str(item)
        if any(keyword in error_text for keyword in timeout_keywords):
            return True
    return False


def is_retryable_c3_execution_error(exc: BaseException | None) -> bool:
    """判断 C3 执行异常是否满足自动重启的可恢复条件。"""
    return is_retryable_google_sheet_execution_error(exc)
