"""进程内存归还工具。

任务线程做大块分配后 free，glibc 仍把空闲页留在各 arena 里：并发跑几个任务，
进程内就残留几份峰值（线上实测单任务 ≈185 MB × 8 并发 ≈1.5 GB 常驻）。
收尾显式调用 malloc_trim(0) 才能把各 arena 的空闲页还给 OS；非 Linux 平台 no-op。
"""

from __future__ import annotations

import ctypes
import sys

from app.utils.logger import get_logger

logger = get_logger(__name__)

_PROC_STATUS_PATH = "/proc/self/status"


def _load_libc():
    if not sys.platform.startswith("linux"):
        return None
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim.argtypes = [ctypes.c_size_t]
        libc.malloc_trim.restype = ctypes.c_int
        return libc
    except (OSError, AttributeError):
        return None


_LIBC = _load_libc()


def trim_process_memory() -> bool:
    """归还 glibc 各 arena 的空闲页；非 Linux 或调用失败返回 False。"""
    if _LIBC is None:
        return False
    try:
        _LIBC.malloc_trim(0)
        return True
    except Exception as exc:
        logger.warning("malloc_trim 调用失败: %s", exc)
        return False


def current_rss_mb() -> float | None:
    """当前进程 RSS（MB）；读取失败返回 None。"""
    try:
        with open(_PROC_STATUS_PATH, encoding="ascii") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError):
        return None
    return None
