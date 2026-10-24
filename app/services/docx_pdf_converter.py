"""DOCX → PDF 转换封装（LibreOffice headless）。

PDF 报告复用 Word 报告的 DOCX 结果（含磁盘缓存），经本模块转出 PDF；
内容以 DOCX 为唯一事实源，报告改版对 Word/PDF 同时生效。

soffice 可执行路径经系统配置 ``libreoffice_soffice_path`` 指定，缺省按
PATH 与 Windows 常见安装位置探测；解析不到时抛 ServiceError。

并发与稳定性约束：soffice 单进程内存开销大，且同一 UserInstallation
profile 的实例互斥——本模块用信号量限制同时运行的转换数，每次调用使用
独立临时 profile（file URI），超时未结束的进程树整树终止。
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from threading import BoundedSemaphore

from app.exceptions import ServiceError
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger


logger = get_logger(__name__)

# soffice 可执行路径的系统配置键；空值/路径无效时按内置探测顺序解析。
SOFFICE_PATH_CONFIG_KEY = "libreoffice_soffice_path"

# 单次转换超时（秒）：正常 10~20 秒，留足 soffice 冷启动余量。
CONVERT_TIMEOUT_SECONDS = 180

# 同时运行的 soffice 进程上限：gunicorn 单 worker 下请求线程并发仍存在。
_MAX_CONCURRENT_CONVERTS = 2
_convert_slots = BoundedSemaphore(_MAX_CONCURRENT_CONVERTS)

# 等待转换槽位上限（秒）：超时快速失败，避免请求线程无限挂在信号量上。
_SLOT_WAIT_SECONDS = 60

# Windows 常见安装位置（PATH 找不到 soffice 时逐个探测）。
_WINDOWS_SOFFICE_CANDIDATES = (
    Path("C:/Program Files/LibreOffice/program/soffice.exe"),
    Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
)


def resolve_soffice_path() -> str:
    """解析 soffice 可执行路径：系统配置 → PATH → Windows 常见安装位置。"""
    configured = str(get_config_manager().get_config(SOFFICE_PATH_CONFIG_KEY, "") or "").strip()
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in _WINDOWS_SOFFICE_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    raise ServiceError(
        "未找到 LibreOffice（soffice），请安装后重试，或配置系统配置 "
        f"{SOFFICE_PATH_CONFIG_KEY} 指定可执行文件路径"
    )


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """超时后终止 soffice 进程树并回收。

    Windows 下只 kill soffice.exe 会留下 soffice.bin 孤儿进程继续占着
    profile，taskkill /T 连树清除；POSIX 侧 soffice 以独立进程组启动，
    整组 SIGKILL。
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError, ValueError):
        pass
    finally:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _run_soffice(command: list[str]) -> tuple[int, str, bool]:
    """运行 soffice 并等待结束，返回 (returncode, stderr 尾部, 是否超时)。

    输出重定向到临时文件而非管道：Windows 下 soffice.exe 拉起的 soffice.bin
    子进程若继承管道写端，超时 kill 后 communicate() 的读线程会永久阻塞
    （请求线程挂死且信号量槽位泄漏）；文件重定向无此问题。
    """
    with TemporaryFile() as stdout_file, TemporaryFile() as stderr_file:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=os.name != "nt",
        )
        timed_out = False
        try:
            proc.wait(timeout=CONVERT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(proc)
        stderr_file.seek(0)
        stderr_tail = stderr_file.read()[-2000:].decode("utf-8", errors="replace")
    return proc.returncode, stderr_tail, timed_out


def convert_docx_to_pdf(docx_bytes: bytes) -> tuple[BytesIO, int]:
    """将 DOCX 字节转换为 PDF 字节，返回 (PDF 字节流, 字节长度)。

    输入输出均为内存字节：临时目录内固定以 ASCII 文件名落盘，规避
    soffice 对含中文路径参数的兼容性问题；UserInstallation 指向同目录
    独立 profile，并发调用互不干扰。转换失败抛 ServiceError。
    """
    soffice = resolve_soffice_path()
    with TemporaryDirectory(prefix="docx_pdf_convert_") as workdir:
        work_path = Path(workdir)
        docx_path = work_path / "report.docx"
        docx_path.write_bytes(docx_bytes)
        profile_uri = (work_path / "lo_profile").as_uri()
        command = [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_path),
            str(docx_path),
        ]
        logger.info("DOCX 转 PDF 开始: soffice=%s", soffice)
        if not _convert_slots.acquire(timeout=_SLOT_WAIT_SECONDS):
            raise ServiceError("PDF 转换排队超时，请稍后重试")
        try:
            returncode, stderr_tail, timed_out = _run_soffice(command)
        finally:
            _convert_slots.release()
        if timed_out:
            logger.error(
                "DOCX 转 PDF 超时（%ss），进程树已终止: soffice=%s",
                CONVERT_TIMEOUT_SECONDS,
                soffice,
            )
            raise ServiceError("DOCX 转 PDF 超时，请稍后重试")
        pdf_path = work_path / "report.pdf"
        if returncode != 0 or not pdf_path.is_file():
            logger.error(
                "DOCX 转 PDF 失败: returncode=%s stderr=%s",
                returncode,
                stderr_tail,
            )
            raise ServiceError("DOCX 转 PDF 失败，请查看服务日志")
        raw = pdf_path.read_bytes()
        logger.info("DOCX 转 PDF 完成: %s bytes", len(raw))
        return BytesIO(raw), len(raw)
