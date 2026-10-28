"""Sheet 执行锁统一服务（唯一互斥权威，Redis 实现）。

语义（全任务类型通用，见 docs 内"统一 Sheet 执行锁"约定）：
- 唯一键为 spreadsheet_id（trim 后精确匹配），与任务类型无关、不依赖注册状态；
- 同一 spreadsheet 同时只能被一个执行中的任务持有；
- pending 排队任务不持锁；锁只在 start_task 成功路径获取、线程收尾/看门狗释放；
- registry 的 is_in_use 仅作展示镜像，不参与互斥判定。

存储（2026-10-28 起 Redis，替代本地锁表 t_param_backtest_sheet_run_locks）：
- 锁键 ``{ns}:sheetlock:{spreadsheet_id}`` → JSON ``{"task_id", "task_type"}``，
  ``SET NX PX`` 原子获取；TTL 兜底进程崩溃（执行期经 :meth:`renew_for_task` 续租）；
- 持锁索引 ``{ns}:sheetlocktask:{task_id}`` → JSON 列表（该任务全部锁键，同 TTL），
  支撑 release_all_by_task / list_held_spreadsheet_ids 免扫描；
- 释放用 Lua 比对删除（仅持锁任务可释放，原子）；
- REDIS_URL 未配置时降级进程内存实现（单 worker 等价语义，多副本部署必须配 Redis）。
"""

from __future__ import annotations

import json
import os
import threading
import time

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 锁 TTL（秒）：须大于单组合最长执行间隔；执行链每步 sleep 时续租。
# 崩溃后最迟 TTL 到期自动释放，startup 另有按任务判活的即时清理缩短该窗口。
_LOCK_TTL_SECONDS = int(os.environ.get("SHEET_LOCK_TTL_SECONDS", "") or 1800)

_RELEASE_LUA = """
local value = redis.call('GET', KEYS[1])
if not value then
    return 1
end
local ok, payload = pcall(cjson.decode, value)
if ok and payload and payload.task_id == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""


def normalize_spreadsheet_id(value) -> str:
    """锁键规范化：仅 trim；Google spreadsheet ID 区分大小写。"""
    return str(value or "").strip()


class _MemoryBackend:
    """进程内存后端（REDIS_URL 未配置时的单 worker 退化）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._locks: dict[str, dict] = {}
        self._indexes: dict[str, list[str]] = {}

    def acquire(self, key, payload, ttl_ms):
        with self._lock:
            current = self._locks.get(key)
            if current is not None and current != payload:
                return False
            self._locks[key] = payload
            return True

    def get(self, key):
        with self._lock:
            value = self._locks.get(key)
            return dict(value) if value else None

    def release(self, key, task_id):
        with self._lock:
            value = self._locks.get(key)
            if value is None:
                return True
            if value.get("task_id") != task_id:
                return False
            del self._locks[key]
            return True

    def renew(self, key, task_id, ttl_ms):
        with self._lock:
            value = self._locks.get(key)
            if value is None or value.get("task_id") != task_id:
                return False
            return True

    def set_index(self, task_id, spreadsheet_ids, ttl_ms):
        with self._lock:
            self._indexes[task_id] = list(spreadsheet_ids)

    def get_index(self, task_id):
        with self._lock:
            return list(self._indexes.get(task_id, []))

    def scan_lock_keys(self):
        with self._lock:
            return list(self._locks.keys())


class _RedisBackend:
    """Redis 后端（键空间见模块 docstring）。"""

    def __init__(self, client, namespace):
        self._client = client
        self._ns = (namespace or "arb:gstask").strip()
        self._release_script = None
        try:
            self._release_script = client.register_script(_RELEASE_LUA)
        except Exception:
            self._release_script = None

    def _lock_key(self, spreadsheet_id):
        return f"{self._ns}:sheetlock:{spreadsheet_id}"

    def _index_key(self, task_id):
        return f"{self._ns}:sheetlocktask:{task_id}"

    def _ttl_ms(self):
        return _LOCK_TTL_SECONDS * 1000

    def acquire(self, key, payload, ttl_ms):
        raw = json.dumps(payload, ensure_ascii=False)
        try:
            return bool(self._client.set(self._lock_key(key), raw, nx=True, px=ttl_ms))
        except Exception as exc:
            logger.warning("Sheet 执行锁获取失败（按未获取处理）: sheet=%s, err=%s", key, exc)
            return False

    def get(self, key):
        try:
            raw = self._client.get(self._lock_key(key))
        except Exception:
            return None
        try:
            return json.loads(raw) if raw else None
        except (TypeError, ValueError):
            return None

    def release(self, key, task_id):
        try:
            if self._release_script is not None:
                return bool(self._release_script(
                    keys=[self._lock_key(key)], args=[task_id],
                ))
            raw = self._client.get(self._lock_key(key))
            if not raw:
                return True
            payload = json.loads(raw)
            if payload.get("task_id") != task_id:
                return False
            self._client.delete(self._lock_key(key))
            return True
        except Exception as exc:
            logger.warning("Sheet 执行锁释放失败（等 TTL 兜底）: sheet=%s, err=%s", key, exc)
            return False

    def renew(self, key, task_id, ttl_ms):
        try:
            raw = self._client.get(self._lock_key(key))
            if not raw:
                return False
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                return False
            if payload.get("task_id") != task_id:
                return False
            self._client.pexpire(self._lock_key(key), ttl_ms)
            return True
        except Exception as exc:
            logger.warning("Sheet 执行锁续租失败: sheet=%s, err=%s", key, exc)
            return False

    def set_index(self, task_id, spreadsheet_ids, ttl_ms):
        try:
            self._client.set(
                self._index_key(task_id),
                json.dumps(spreadsheet_ids, ensure_ascii=False),
                px=ttl_ms,
            )
        except Exception as exc:
            logger.warning("Sheet 执行锁索引写入失败: task_id=%s, err=%s", task_id, exc)

    def get_index(self, task_id):
        try:
            raw = self._client.get(self._index_key(task_id))
        except Exception:
            return []
        try:
            return json.loads(raw) if raw else []
        except (TypeError, ValueError):
            return []

    def scan_lock_keys(self):
        prefix = f"{self._ns}:sheetlock:"
        try:
            return [
                key[len(prefix):]
                for key in self._client.scan_iter(match=f"{prefix}*", count=200)
            ]
        except Exception as exc:
            logger.warning("Sheet 执行锁扫描失败: %s", exc)
            return []


class SheetExecutionLockService:
    """acquire/release/conflict/续租 判定的唯一出口。"""

    def __init__(self):
        self._backend = None
        self._backend_lock = threading.Lock()

    # ---- 后端 ----

    def _get_backend(self):
        if self._backend is not None:
            return self._backend
        with self._backend_lock:
            if self._backend is not None:
                return self._backend
            url = (os.environ.get("REDIS_URL", "") or "").strip()
            backend = None
            if url:
                try:
                    import redis  # 延迟导入：依赖缺失时降级而非崩掉业务路径

                    client = redis.Redis.from_url(
                        url,
                        socket_timeout=2,
                        socket_connect_timeout=2,
                        decode_responses=True,
                    )
                    namespace = (os.environ.get("REDIS_NAMESPACE", "") or "arb:gstask").strip()
                    backend = _RedisBackend(client, namespace)
                except Exception as exc:
                    logger.warning("Sheet 执行锁 Redis 后端构造失败，降级进程内存: %s", exc)
            if backend is None:
                backend = _MemoryBackend()
            self._backend = backend
            return backend

    # ---- 锁语义 ----

    def acquire_for_task(
        self,
        task_id: str,
        task_type: str,
        spreadsheet_ids: list[str],
    ) -> tuple[bool, str | None, list[str]]:
        """获取任务的全部 sheet 锁（全拿全放）。

        返回 (acquired_all, holder_task_id, acquired_ids)；冲突时回滚本次
        已获取的锁并返回持锁任务 id。
        """
        normalized = self.normalize_ids(spreadsheet_ids)
        if not normalized:
            return True, None, []
        backend = self._get_backend()
        acquired: list[str] = []
        for spreadsheet_id in normalized:
            payload = {"task_id": task_id, "task_type": task_type}
            if backend.acquire(spreadsheet_id, payload, _LOCK_TTL_SECONDS * 1000):
                acquired.append(spreadsheet_id)
                continue
            holder = backend.get(spreadsheet_id) or {}
            holder_task_id = holder.get("task_id")
            if holder_task_id == task_id:
                # 同任务重入（幂等）：视为已持有。
                acquired.append(spreadsheet_id)
                continue
            for acquired_id in acquired:
                backend.release(acquired_id, task_id)
            logger.info(
                "Sheet 执行锁冲突: sheet=%s, holder=%s, requester=%s",
                spreadsheet_id,
                holder_task_id,
                task_id,
            )
            return False, holder_task_id, []
        backend.set_index(task_id, normalized, _LOCK_TTL_SECONDS * 1000)
        return True, None, normalized

    def renew_for_task(self, task_id: str) -> None:
        """续租任务持有的全部锁（执行链每步调用，防长任务锁过期被抢）。"""
        backend = self._get_backend()
        spreadsheet_ids = backend.get_index(task_id)
        if not spreadsheet_ids:
            return
        ttl_ms = _LOCK_TTL_SECONDS * 1000
        for spreadsheet_id in spreadsheet_ids:
            backend.renew(spreadsheet_id, task_id, ttl_ms)
        backend.set_index(task_id, spreadsheet_ids, ttl_ms)

    def release_for_task(self, task_id: str) -> int:
        """释放任务持有的全部锁；返回释放数量。"""
        backend = self._get_backend()
        spreadsheet_ids = backend.get_index(task_id)
        released = 0
        for spreadsheet_id in spreadsheet_ids:
            if backend.release(spreadsheet_id, task_id):
                released += 1
        backend.set_index(task_id, [], _LOCK_TTL_SECONDS * 1000)
        return released

    def list_held_spreadsheet_ids(self, task_id: str) -> list[str]:
        """任务当前持有的全部锁键（收尾接力集合依据，与释放动作同源）。"""
        return list(self._get_backend().get_index(task_id))

    def release_sheets(self, spreadsheet_ids: list[str], task_id: str) -> None:
        """逐把释放（仅清理指定 sheet；他人锁被拒绝并告警）。"""
        backend = self._get_backend()
        for spreadsheet_id in self.normalize_ids(spreadsheet_ids):
            released = backend.release(spreadsheet_id, task_id)
            if not released:
                lock = backend.get(spreadsheet_id) or {}
                logger.warning(
                    "跳过释放 Sheet 执行锁: sheet=%s, task_id=%s, holder=%s",
                    spreadsheet_id,
                    task_id,
                    lock.get("task_id"),
                )

    def find_conflict(
        self,
        spreadsheet_ids: list[str],
        exclude_task_id: str | None = None,
    ) -> str | None:
        """任一 sheet 被其他任务持锁时返回持锁任务 id，否则 None。"""
        backend = self._get_backend()
        for spreadsheet_id in self.normalize_ids(spreadsheet_ids):
            lock = backend.get(spreadsheet_id)
            holder_task_id = (lock or {}).get("task_id")
            if holder_task_id and holder_task_id != exclude_task_id:
                return holder_task_id
        return None

    def cleanup_stale_locks(self, is_task_running) -> int:
        """启动期清理陈旧锁（持有任务不存在或非 running）；返回清理数量。

        TTL 兜底之外缩短崩溃后的锁残留窗口：check_and_cleanup_dead_tasks 把
        崩溃任务置回 pending 后调用本方法，排队补跑即可立即抢锁。
        """
        backend = self._get_backend()
        cleaned = 0
        for spreadsheet_id in backend.scan_lock_keys():
            lock = backend.get(spreadsheet_id) or {}
            holder_task_id = lock.get("task_id")
            if holder_task_id and is_task_running(holder_task_id):
                continue
            if backend.release(spreadsheet_id, holder_task_id or ""):
                cleaned += 1
        return cleaned

    @staticmethod
    def normalize_ids(spreadsheet_ids) -> list[str]:
        return sorted(
            {
                normalized
                for normalized in (
                    normalize_spreadsheet_id(value) for value in (spreadsheet_ids or [])
                )
                if normalized
            }
        )


sheet_execution_lock_service = SheetExecutionLockService()


def get_sheet_execution_lock_service() -> SheetExecutionLockService:
    return sheet_execution_lock_service
