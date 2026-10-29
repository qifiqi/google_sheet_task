"""远端能力探测：E12 随机K线三表端点。

E12（ParamTaskKlineSources / ParamTaskRandomSeries / ParamTaskResultKlineLinks）
在 7070 已部署、生产 base（stockapi.jaspil.cn）尚未部署（2026-10-29 实测）。
调用方在写快照/关联前先经 ``require_e12`` 预检：缺失时快速失败并给出明确
消息，避免任务跑到一半才 404；探测结果进程内缓存，部署后需重启进程重探。
"""

from __future__ import annotations

import threading
from typing import Any

from app.remote_api.exceptions import RemoteApiError

_E12_PROBES = (
    ("param_task_kline_sources", "/api/ParamTaskKlineSources/GetDataByPageList"),
    ("param_task_random_series", "/api/ParamTaskRandomSeries/GetDataByPageList"),
    ("param_task_result_kline_links", "/api/ParamTaskResultKlineLinks/GetDataByPageList"),
)

_lock = threading.Lock()
_state: bool | None = None
_missing: tuple[str, ...] = ()


def reset_e12_capability() -> None:
    """清空探测缓存（测试与热修复场景）。"""
    global _state, _missing
    with _lock:
        _state = None
        _missing = ()


def _missing_error() -> RemoteApiError:
    return RemoteApiError(
        "远端未部署随机K线接口(E12)，无法持久化快照/结果关联；缺失端点: "
        f"{', '.join(_missing)}。请部署 ParamTaskKlineSources / "
        "ParamTaskRandomSeries / ParamTaskResultKlineLinks，或切换 STOCK_BASE_URL 后重启。"
    )


def require_e12(api: Any | None = None) -> None:
    """确认远端具备 E12 三表端点；缺失时抛 RemoteApiError（快速失败）。"""
    global _state, _missing
    if _state is True:
        return
    with _lock:
        if _state is True:
            return
        if _state is False:
            raise _missing_error()
        if api is None:
            from app.remote_api import stock_api

            api = stock_api
        missing: list[str] = []
        for controller_name, path in _E12_PROBES:
            controller = getattr(api, controller_name, None)
            if controller is None:
                missing.append(path)
                continue
            try:
                if hasattr(api, "request_with_count"):
                    api.request_with_count(
                        "POST", path, {"page_index": 1, "page_size": 1}, probe=True
                    )
                else:
                    controller.get_data_by_page_list({"page_index": 1, "page_size": 1})
            except RemoteApiError as exc:
                if "404" in str(exc):
                    missing.append(path)
                else:
                    raise
        if missing:
            _state = False
            _missing = tuple(missing)
            raise _missing_error()
        _state = True
