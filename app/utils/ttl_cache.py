"""进程内统一 TTL 缓存。

服务于"重复请求代价高、结果在短窗口内稳定"的场景：内存侧提供通用
TTLCache 引擎；Word 报告导出为磁盘缓存（data/word_export_cache/），
跨进程重启仍然有效。

说明：get_or_set 不做并发单飞，TTL 过期瞬间的并发请求可能各自执行
一次 builder；生成型 builder 幂等且无副作用，可接受。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, BinaryIO

from pydantic import BaseModel

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Word 导出：任务重跑后同条件请求在 TTL 内会命中旧报告，取 10 分钟
# 平衡重复导出的等待成本与数据新鲜度；仅缓存成功生成的结果。
WORD_EXPORT_TTL_SECONDS = 10 * 60


class TTLCache:
    """带 TTL 与 LRU 容量上限的进程内键值缓存。"""

    def __init__(self, max_entries: int = 128) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # key → (取样时间, 值)；OrderedDict 维护访问序供 LRU 淘汰。
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get_or_set(self, key: str, builder: Callable[[], Any], ttl_seconds: int) -> Any:
        """命中且未过期直接返回；否则执行 builder 并缓存其结果。

        builder 抛异常时不缓存任何内容，异常原样上抛（只缓存成功结果）。
        """
        now = time.monotonic()
        with self._lock:
            stamped = self._entries.get(key)
            if stamped is not None:
                stored_at, value = stamped
                if now - stored_at <= ttl_seconds:
                    self._entries.move_to_end(key)
                    return value
                del self._entries[key]
        value = builder()
        with self._lock:
            self._entries[key] = (time.monotonic(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        """清空全部缓存；测试隔离与强制刷新用。"""
        with self._lock:
            self._entries.clear()


def word_export_cache_dir() -> Path:
    """Word 导出缓存目录；测试经 monkeypatch 本函数隔离到临时目录。"""
    return Config.DATA_DIR / "word_export_cache"


def clear_word_export_cache(
    *,
    task_id: str | None = None,
    only_expired: bool = False,
    ttl_seconds: int | None = None,
) -> int:
    """清理 Word 导出缓存，返回删除的条目数。

    默认清空全部；task_id 定向删除该任务的报告缓存（按 sidecar 元数据
    匹配，重新回测后可只失效该任务的报告）；only_expired 仅删除超过
    TTL 的过期条目。ttl_seconds 供定向清理时判定存活，缺省用默认 TTL。
    """
    directory = word_export_cache_dir()
    if task_id is None and not only_expired:
        removed = len(list(directory.glob("*.json"))) if directory.is_dir() else 0
        shutil.rmtree(directory, ignore_errors=True)
        return removed
    ttl = WORD_EXPORT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    removed = 0
    try:
        meta_paths = list(directory.glob("*.json"))
    except OSError:
        return 0
    for meta_path in meta_paths:
        if task_id is not None:
            if _load_entry_meta(meta_path).get("task_id") != task_id:
                continue
        else:
            if _is_fresh(directory / f"{meta_path.stem}.docx", ttl):
                continue
        removed += _remove_entry(directory, meta_path.stem)
    return removed


def list_word_export_cache(ttl_seconds: int | None = None) -> list[dict[str, Any]]:
    """列出缓存条目（哈希键、原始文件名、任务/标的信息、大小与存活状态）。"""
    ttl = WORD_EXPORT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    directory = word_export_cache_dir()
    entries: list[dict[str, Any]] = []
    try:
        meta_paths = sorted(directory.glob("*.json"))
    except OSError:
        return entries
    for meta_path in meta_paths:
        meta = _load_entry_meta(meta_path)
        try:
            stat = (directory / f"{meta_path.stem}.docx").stat()
        except OSError:
            continue
        age_minutes = round(max(0.0, time.time() - stat.st_mtime) / 60, 1)
        entries.append({
            "key": meta_path.stem,
            "filename": meta.get("filename"),
            "title": meta.get("title"),
            "task_id": meta.get("task_id"),
            "stock_codes": meta.get("stock_codes") or [],
            "created_at": meta.get("created_at"),
            "size_bytes": stat.st_size,
            "age_minutes": age_minutes,
            "expired": age_minutes * 60 > ttl,
        })
    return entries


def get_or_build_word_export(
    payload: BaseModel,
    builder: Callable[[], tuple[str, BytesIO]],
    ttl_seconds: int | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[str, BinaryIO, int]:
    """按报告请求载荷缓存 Word 生成结果；查询条件相同直接回放缓存文件。

    缓存键取展开后有效载荷的规范化 JSON 摘要（嵌套字典键序无关），因此
    RPT-M 按 task_id 展开后的相同内容与 RPT-S 的相同请求都能命中。
    磁盘布局：<sha256>.docx 为报告本体，<sha256>.json sidecar 记录首次
    生成的下载文件名与业务元数据（title/task_id/stock_codes，供定向清
    理与后台列表识别），sidecar 存在即视为条目完整。TTL 以 docx 的
    mtime 判活，每次调用前顺手清扫过期文件；命中时返回打开的文件句柄
    交由 send_file 流式下发。ttl_seconds <= 0 时跳过缓存直接生成。
    哈希输入含布局版本号：报告结构变更时递增版本可避免命中旧版式缓存。
    """
    directory = word_export_cache_dir()
    ttl = WORD_EXPORT_TTL_SECONDS if ttl_seconds is None else ttl_seconds

    def build() -> tuple[str, bytes]:
        filename, buffer = builder()
        return filename, buffer.getvalue()

    if ttl <= 0:
        filename, raw = build()
        return filename, BytesIO(raw), len(raw)

    _sweep_expired(directory, ttl)
    canonical = "word-export:v2:" + json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, default=str,
    )
    key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    cached = _read_cached_export(directory, key, ttl)
    if cached is not None:
        return cached

    filename, raw = build()
    _write_cached_export(directory, key, filename, raw, meta or {})
    return filename, BytesIO(raw), len(raw)


def _read_cached_export(directory: Path, key: str, ttl: int) -> tuple[str, BinaryIO, int] | None:
    """读取缓存条目；过期、不完整（缺 sidecar）或读被并发删除时视为未命中。"""
    docx_path = directory / f"{key}.docx"
    meta_path = directory / f"{key}.json"
    try:
        if not _is_fresh(docx_path, ttl) or not meta_path.is_file():
            return None
        filename = _load_entry_meta(meta_path)["filename"]
        return filename, open(docx_path, "rb"), docx_path.stat().st_size
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _load_entry_meta(meta_path: Path) -> dict[str, Any]:
    """读取 sidecar 元数据；缺失或损坏返回空字典（条目按不完整处理）。"""
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _remove_entry(directory: Path, key: str) -> int:
    """删除单个缓存条目（docx + sidecar），成功返回 1。"""
    removed = False
    for suffix in (".json", ".docx"):
        try:
            (directory / f"{key}{suffix}").unlink(missing_ok=True)
            removed = True
        except OSError:
            pass
    return 1 if removed else 0


def _write_cached_export(
    directory: Path, key: str, filename: str, raw: bytes, meta: dict[str, Any],
) -> None:
    """落盘缓存条目；写失败只记日志，不影响本次已在内存中的导出结果。"""
    payload_meta = dict(meta)
    payload_meta["filename"] = filename
    payload_meta.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # 先写 docx 后写 sidecar：sidecar 存在即条目完整，读者以它为准。
        _atomic_write(directory / f"{key}.docx", raw)
        _atomic_write(
            directory / f"{key}.json",
            json.dumps(payload_meta, ensure_ascii=False).encode("utf-8"),
        )
    except OSError:
        logger.warning("Word 导出缓存写盘失败，本次结果不做缓存: %s", key, exc_info=True)


def _atomic_write(path: Path, data: bytes) -> None:
    """临时文件 + 原子替换，避免并发读者看到半截文件（Windows 兼容）。"""
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, path)


def _sweep_expired(directory: Path, ttl: int) -> None:
    """清扫过期缓存文件；目录不存在或被并发清空都视为无可清扫。"""
    try:
        for path in directory.iterdir():
            if path.is_file() and not _is_fresh(path, ttl):
                path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_fresh(path: Path, ttl: int) -> bool:
    """按 mtime 判活；磁盘时间戳必须对 wall clock 而非 monotonic。"""
    try:
        return time.time() - path.stat().st_mtime <= ttl
    except OSError:
        return False
