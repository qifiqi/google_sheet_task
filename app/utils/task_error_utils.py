from __future__ import annotations

from http.client import RemoteDisconnected
from typing import Iterator

from requests.exceptions import ConnectionError, RequestException, Timeout
from tenacity import RetryError
from urllib3.exceptions import ProtocolError

NETWORK_ERROR_PREFIX = "[NETWORK_RETRYABLE]"


class RetryableNetworkTaskError(Exception):
    """A network-layer error that is safe for the watchdog to auto-restart."""


def iter_exception_chain(exc: BaseException | None) -> Iterator[BaseException]:
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
    last = None
    for last in iter_exception_chain(exc):
        pass
    return last or exc


def is_retryable_network_error(exc: BaseException | None) -> bool:
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


def build_task_error_message(exc: BaseException | None) -> str:
    root = unwrap_exception(exc)
    if root is None:
        return "未知错误"
    message = f"{root.__class__.__name__}: {root}"
    if is_retryable_network_error(exc):
        return f"{NETWORK_ERROR_PREFIX} {message}"
    return message
