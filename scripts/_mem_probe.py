"""平台内存基线探针：只读 RSS，不启动调度器/看门狗、不连数据库。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctypes
import ctypes.wintypes as wt


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_PMC),
    wt.DWORD,
]
ctypes.windll.psapi.GetProcessMemoryInfo.restype = wt.BOOL


def rss_mb():
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb
    )
    if not ok:
        return -1.0
    return round(pmc.WorkingSetSize / 1048576, 1)


print("bare:", rss_mb())

import flask  # noqa: E402,F401
import sqlalchemy  # noqa: E402,F401
import pydantic  # noqa: E402,F401

print("flask+sqlalchemy+pydantic:", rss_mb())

import pandas  # noqa: E402,F401

print("+pandas:", rss_mb())

import orjson  # noqa: E402,F401
import gspread  # noqa: E402,F401

print("+orjson/gspread:", rss_mb())

import app  # noqa: E402  全量业务导入链（routes->services->utils）

print("import app(full chain):", rss_mb())

try:
    application = app.create_app()
    print("create_app():", rss_mb())
except Exception as exc:  # 环境缺 DB 等不阻断测量
    print("create_app() failed:", type(exc).__name__, str(exc)[:120], "rss:", rss_mb())

import akshare  # noqa: E402  任务期惰性导入的行情库

print("+akshare(lazy in task):", rss_mb())
