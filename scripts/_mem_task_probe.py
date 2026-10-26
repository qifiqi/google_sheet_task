"""任务执行内存实测探针（一次性诊断脚本，非正式测试）。

对指定任务走真实执行链（task_manager.start_task -> C 系骨架 -> 线程池），
采样进程工作集与峰值，到时限后取消任务并输出内存报告。

用法：
    python scripts/_mem_task_probe.py <task_id> [max_minutes=15]

环境（缺省时脚本内置测试环境值，显式 env 优先）：
    DATABASE_URL    测试 PostgreSQL
    STOCK_BASE_URL  测试主站（stock_sdk 内部K线库/远端出口）
"""
import os
import sys
import time
import threading
import ctypes
import ctypes.wintypes as wt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:Hello12345*@172.18.20.17:5432/googlesheet_validator",
)
os.environ.setdefault("STOCK_BASE_URL", "http://172.18.20.20:7070")
try:
    from dotenv import load_dotenv

    load_dotenv(override=False)  # 补 JWT_SECRET_KEY 等杂项；上面的显式值不被覆盖
except ImportError:
    pass


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


def mem_mb():
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb
    )
    if not ok:
        return {"rss": -1.0, "peak_rss": -1.0, "pagefile": -1.0, "peak_pagefile": -1.0}
    return {
        "rss": round(pmc.WorkingSetSize / 1048576, 1),
        "peak_rss": round(pmc.PeakWorkingSetSize / 1048576, 1),
        "pagefile": round(pmc.PagefileUsage / 1048576, 1),
        "peak_pagefile": round(pmc.PeakPagefileUsage / 1048576, 1),
    }


def main():
    task_id = sys.argv[1]
    max_minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

    from app import create_app
    from app.extensions import db
    from app.repositories import task_repository
    from app.services.task import task_manager

    application = create_app()
    base = mem_mb()
    print(f"[probe] create_app 基线: {base}", flush=True)

    samples = []
    stop_sampling = threading.Event()

    def sampler():
        while not stop_sampling.is_set():
            m = mem_mb()
            samples.append((time.monotonic(), m))
            stop_sampling.wait(1.0)

    with application.app_context():
        db.session.expire_all()
        task = task_repository.get_entity(task_id)
        if not task:
            print(f"[probe] 任务不存在: {task_id}")
            return 2
        print(
            f"[probe] 任务 {task.name} type={task.task_type} status={task.status}",
            flush=True,
        )

        result = task_manager.start_task(task_id)
        print(f"[probe] start_task -> started={result.started} queued={result.queued} "
              f"rejected={getattr(result, 'rejected', None)} reason={getattr(result, 'reason', '')}",
              flush=True)
        if not result.started:
            return 2

        sampler_thread = threading.Thread(target=sampler, daemon=True)
        sampler_thread.start()

        start_monotonic = time.monotonic()
        last_step = -1
        terminal = None
        try:
            while True:
                time.sleep(5)
                db.session.expire_all()
                fresh = task_repository.get_entity(task_id)
                elapsed = time.monotonic() - start_monotonic
                if fresh.current_step != last_step:
                    m = mem_mb()
                    print(f"[probe] t+{elapsed:6.0f}s step={fresh.current_step} "
                          f"status={fresh.status} rss={m['rss']}MB peak={m['peak_rss']}MB "
                          f"pagefile={m['pagefile']}MB", flush=True)
                    last_step = fresh.current_step
                if fresh.status in ("completed", "cancelled", "error"):
                    terminal = fresh.status
                    print(f"[probe] 任务终态: {terminal} @ t+{elapsed:.0f}s", flush=True)
                    break
                if elapsed >= max_minutes * 60:
                    print(f"[probe] 达到采样时限 {max_minutes} 分钟，发起取消", flush=True)
                    task_manager.cancel_task(task_id)
        except KeyboardInterrupt:
            print("[probe] 手动中断，发起取消", flush=True)
            task_manager.cancel_task(task_id)

        handle = task_manager.running_tasks.get(task_id)
        if handle is not None:
            print("[probe] 等待执行线程收尾（锁释放/日志 flush）...", flush=True)
            handle.join(timeout=600)
        print(f"[probe] 线程已结束，终态={terminal}", flush=True)

    stop_sampling.set()
    sampler_thread.join(timeout=5)

    end = mem_mb()
    rss_values = [m["rss"] for _, m in samples if m["rss"] > 0]
    pagefile_values = [m["pagefile"] for _, m in samples if m["pagefile"] > 0]
    print("\n===== 内存报告 =====")
    print(f"create_app 基线 RSS      : {base['rss']} MB")
    if rss_values:
        print(f"任务期采样 RSS 峰值      : {max(rss_values)} MB")
        print(f"任务期采样 RSS 稳态(末值): {rss_values[-1]} MB")
        print(f"任务期采样 pagefile 峰值 : {max(pagefile_values)} MB")
    print(f"进程生命周期 peak_rss    : {end['peak_rss']} MB")
    print(f"进程生命周期 peak_pagefile: {end['peak_pagefile']} MB")
    print(f"结束时 RSS               : {end['rss']} MB")
    if rss_values:
        print(f"任务净增(峰值-基线)      : {round(max(rss_values) - base['rss'], 1)} MB")
    print("====================")
    return 0


if __name__ == "__main__":
    code = main()
    # 任务线程挂死时的硬退出兜底（报告已输出）
    sys.stdout.flush()
    sys.exit(code)
