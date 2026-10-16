"""任务运行期中间态存储（db-to-http 方案 B，2026-10-16）。

数据库在任务执行期只保留三个瞬时里程碑：创建 pending、启动 running、结束
终态快照；持续中间态——每组合进度（current_step/total_steps）、业务日志、
取消标志、心跳——全部落本存储，任务结束时由 ``sync_snapshot`` 一次性回灌
数据库（进度字段合并进终态更新 + 日志批量回灌 TaskLog）并清理键。

键布局（命名空间沿用 REDIS_NAMESPACE，默认 ``arb:gstask``）：

- ``{ns}:rt:{task_id}:state``  Hash：status / current_step / total_steps /
  error_message / start_time / heartbeat_at
- ``{ns}:rt:{task_id}:logs``   List：JSON 日志行，LPUSH 最新在前、LTRIM 截断
  上限（环境变量 ``TASK_RUNTIME_LOG_MAX``，默认 1000 条）

生命周期：任务线程启动（runtime._mark_task_running）创建 state；结束
（收尾快照 / 异常收尾）回灌并 drop；进程异常退出的残留由启动期
``reconcile_all_runtime_states`` 对账回灌（startup 在裁决层 namespace_reset
之前调用，死任务清理随后把 running 行复位）。每次写入续期 TTL（默认 7 天）
作硬崩溃兜底。

降级：REDIS_URL 未配置 / redis 依赖缺失 / 连接异常 → 进程内存 dict（单
worker 部署语义完整；多副本部署跨进程视图失效，与 app/adjudication 降级
口径一致）。零 Flask 依赖。

例外登记：model_summary 索引重建任务保持 DB 进度写（批量粒度、自带终态
收尾、不走任务运行时），不接入本存储。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from app.repositories import task_log_repository, task_repository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 写入续期 TTL：远大于最长任务时长，仅作崩溃残留兜底（正常结束立即 drop）。
_RUNTIME_STATE_TTL_SECONDS = 7 * 24 * 3600

# 日志流截断上限：结束时批量回灌数据库的行数量级上限。
_LOG_LIST_DEFAULT_MAX = 1000

_STATE_FIELD_STATUS = "status"
_STATE_FIELD_CURRENT_STEP = "current_step"
_STATE_FIELD_TOTAL_STEPS = "total_steps"
_STATE_FIELD_ERROR_MESSAGE = "error_message"
_STATE_FIELD_START_TIME = "start_time"
_STATE_FIELD_HEARTBEAT = "heartbeat_at"

_INT_STATE_FIELDS = (_STATE_FIELD_CURRENT_STEP, _STATE_FIELD_TOTAL_STEPS)


def _now_iso() -> str:
    return datetime.now().isoformat()


class TaskRuntimeStateStore:
    """任务运行态存储：Redis 主存，降级进程内存。"""

    def __init__(
        self,
        client=None,
        url="",
        namespace="arb:gstask",
        log_max=None,
        ttl_seconds=_RUNTIME_STATE_TTL_SECONDS,
    ):
        self._client = client
        self._url = (url or "").strip()
        self.namespace = (namespace or "arb:gstask").strip()
        self._ttl = max(60, int(ttl_seconds))
        self._log_max = int(log_max) if log_max else _LOG_LIST_DEFAULT_MAX
        self._warned = False
        self._mem_lock = threading.Lock()
        self._mem_states: dict[str, dict] = {}
        self._mem_logs: dict[str, list] = {}

    @classmethod
    def from_env(cls):
        return cls(
            url=os.environ.get("REDIS_URL", ""),
            namespace=os.environ.get("REDIS_NAMESPACE", "arb:gstask"),
            log_max=int(os.environ.get("TASK_RUNTIME_LOG_MAX", "") or _LOG_LIST_DEFAULT_MAX),
        )

    # ---- 基础设施 ----

    def _degrade_once(self, reason):
        if not self._warned:
            self._warned = True
            logger.warning("任务运行态存储降级为进程内存（多副本部署跨进程视图失效）：%s", reason)

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._url:
            self._degrade_once("REDIS_URL 未配置")
            return None
        try:
            import redis  # 延迟导入：依赖缺失时降级而非崩掉业务路径
        except ImportError:
            self._degrade_once("redis 依赖未安装（pip install redis）")
            return None
        try:
            self._client = redis.Redis.from_url(
                self._url,
                socket_timeout=2,
                socket_connect_timeout=2,
                decode_responses=True,
            )
        except Exception as exc:
            self._degrade_once(f"Redis 客户端构造失败: {exc}")
            return None
        return self._client

    def _key_state(self, task_id):
        return f"{self.namespace}:rt:{task_id}:state"

    def _key_logs(self, task_id):
        return f"{self.namespace}:rt:{task_id}:logs"

    # ---- 写 ----

    def mark_running(self, task_id, start_time=None, current_step=0, total_steps=0):
        """任务线程开跑：创建运行态（status=running，进度以 DB 快照播种，心跳就绪）。

        进度用任务行当前值播种而非归零：断点恢复的"跳过已完成组合"阶段若崩溃，
        启动对账回灌的进度不得小于上一进程已确认的断点。
        """
        started = start_time or datetime.now()
        state = {
            _STATE_FIELD_STATUS: "running",
            _STATE_FIELD_CURRENT_STEP: int(current_step or 0),
            _STATE_FIELD_TOTAL_STEPS: int(total_steps or 0),
            _STATE_FIELD_START_TIME: started.isoformat()
            if hasattr(started, "isoformat")
            else str(started),
            _STATE_FIELD_HEARTBEAT: _now_iso(),
        }
        self._write_state(task_id, state)

    def update_progress(self, task_id, current_step=None, total_steps=None):
        """进度写（执行链每组合热路径）；state 不存在时隐式补建。"""
        fields = {}
        if current_step is not None:
            fields[_STATE_FIELD_CURRENT_STEP] = int(current_step)
        if total_steps is not None:
            fields[_STATE_FIELD_TOTAL_STEPS] = int(total_steps)
        if not fields:
            return
        fields[_STATE_FIELD_HEARTBEAT] = _now_iso()
        self._merge_state(task_id, fields, default_status="running")

    def append_log(self, task_id, level, message):
        """追加一条运行期业务日志（须已有运行态；无态调用方走 DB 直写）。"""
        entry = {
            "level": level,
            "message": message,
            "timestamp": _now_iso(),
        }
        client = self._ensure_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.lpush(self._key_logs(task_id), json.dumps(entry, ensure_ascii=False))
                pipe.ltrim(self._key_logs(task_id), 0, self._log_max - 1)
                pipe.expire(self._key_logs(task_id), self._ttl)
                pipe.execute()
                return
            except Exception as exc:
                self._degrade_once(f"追加运行态日志异常（{task_id}）: {exc}")
        with self._mem_lock:
            self._mem_logs.setdefault(task_id, []).append(entry)
            overflow = len(self._mem_logs[task_id]) - self._log_max
            if overflow > 0:
                del self._mem_logs[task_id][:overflow]

    def request_cancel(self, task_id) -> bool:
        """取消标志（仅已有运行态生效；pending 任务取消走 DB 终态写）。"""
        if not self.has_state(task_id):
            return False
        self._merge_state(
            task_id,
            {_STATE_FIELD_STATUS: "cancelled", _STATE_FIELD_HEARTBEAT: _now_iso()},
            default_status=None,
        )
        return True

    # ---- 读 ----

    def has_state(self, task_id) -> bool:
        client = self._ensure_client()
        if client is not None:
            try:
                return bool(client.exists(self._key_state(task_id)))
            except Exception as exc:
                self._degrade_once(f"运行态存在性检查异常（{task_id}）: {exc}")
        with self._mem_lock:
            return task_id in self._mem_states

    def get_state(self, task_id):
        """运行态快照 dict（字段已解析）；无运行态返回 None。"""
        client = self._ensure_client()
        if client is not None:
            try:
                raw = client.hgetall(self._key_state(task_id))
            except Exception as exc:
                self._degrade_once(f"读取运行态异常（{task_id}）: {exc}")
            else:
                return self._parse_state(raw) if raw else None
        with self._mem_lock:
            state = self._mem_states.get(task_id)
            return dict(state) if state else None

    def get_states(self, task_ids):
        """批量运行态快照：{task_id: state}；仅返回有态任务。"""
        ids = [str(task_id) for task_id in dict.fromkeys(task_ids or []) if task_id]
        if not ids:
            return {}
        client = self._ensure_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                for task_id in ids:
                    pipe.hgetall(self._key_state(task_id))
                raws = pipe.execute()
            except Exception as exc:
                self._degrade_once(f"批量读取运行态异常: {exc}")
            else:
                return {
                    task_id: parsed
                    for task_id, raw in zip(ids, raws)
                    if raw and (parsed := self._parse_state(raw))
                }
        with self._mem_lock:
            return {
                task_id: dict(self._mem_states[task_id])
                for task_id in ids
                if task_id in self._mem_states
            }

    def get_status_value(self, task_id):
        """仅取运行态状态值（执行链取消检查热路径）。

        None 表示无运行态（等价旧行为里任务行不存在 → 停止执行）；
        "cancelled" 表示取消请求；其余（"running"）继续。
        """
        state = self.get_state(task_id)
        return state.get(_STATE_FIELD_STATUS) if state else None

    def get_logs(self, task_id, limit=500):
        """按时间正序返回最新 limit 条运行期日志（与仓储 list_by_task 同形）。"""
        limit = max(1, int(limit or 500))
        client = self._ensure_client()
        if client is not None:
            try:
                raw_items = client.lrange(self._key_logs(task_id), 0, limit - 1)
            except Exception as exc:
                self._degrade_once(f"读取运行态日志异常（{task_id}）: {exc}")
            else:
                entries = []
                for raw in raw_items:
                    try:
                        entries.append(json.loads(raw))
                    except (TypeError, ValueError):
                        continue
                return list(reversed(entries))
        with self._mem_lock:
            logs = self._mem_logs.get(task_id, [])
            return [dict(entry) for entry in logs[-limit:]]

    def list_active_ids(self):
        """当前持有运行态的全部任务 id（启动对账、查询叠加用）。"""
        client = self._ensure_client()
        if client is not None:
            ids = []
            try:
                pattern = f"{self.namespace}:rt:*:state"
                prefix_len = len(f"{self.namespace}:rt:")
                suffix_len = len(":state")
                for key in client.scan_iter(match=pattern, count=200):
                    ids.append(key[prefix_len:-suffix_len])
                return ids
            except Exception as exc:
                self._degrade_once(f"枚举运行态异常: {exc}")
        with self._mem_lock:
            return list(self._mem_states.keys())

    # ---- 回灌 / 清理 ----

    def progress_fields(self, task_id):
        """从运行态提取进度字段（终态更新合并用）；无态返回 {}。"""
        state = self.get_state(task_id)
        if not state:
            return {}
        fields = {}
        if state.get(_STATE_FIELD_CURRENT_STEP) is not None:
            fields["current_step"] = state[_STATE_FIELD_CURRENT_STEP]
        if state.get(_STATE_FIELD_TOTAL_STEPS) is not None:
            fields["total_steps"] = state[_STATE_FIELD_TOTAL_STEPS]
        return fields

    def flush_logs_to_db(self, task_id):
        """运行期日志批量回灌 TaskLog（保序）；返回回灌条数。"""
        logs = self.get_logs(task_id, limit=self._log_max)
        if not logs:
            return 0
        rows = []
        for entry in logs:
            timestamp = entry.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp = datetime.now()
            rows.append(
                {
                    "level": entry.get("level") or "info",
                    "message": entry.get("message") or "",
                    "timestamp": timestamp or datetime.now(),
                }
            )
        task_log_repository.create_logs(task_id, rows)
        return len(rows)

    def sync_snapshot(self, task_id, status=None, end_time=None):
        """任务结束快照：进度字段 + 运行期日志回灌数据库后清理运行态。

        status/end_time 提供时一并合并进任务行更新（终态收尾语义）；提供
        status 而未提供 end_time 时 end_time 取当前时间。无任何运行态时为
        no-op（返回 None），供重启对账与异常收尾幂等调用；无运行态但需要
        落终态的调用方（收尾路径）自行直写任务行。
        """
        fields = self.progress_fields(task_id)
        has_logs = self._has_logs(task_id)
        if not fields and not has_logs:
            return None
        if status is not None:
            fields["status"] = status
            if end_time is None:
                end_time = datetime.now()
        if end_time is not None:
            fields["end_time"] = end_time
        if fields:
            task_repository.update_fields(task_id, **fields)
        flushed = self.flush_logs_to_db(task_id)
        self.drop(task_id)
        return {"synced_fields": fields, "flushed_logs": flushed}

    def drop(self, task_id):
        """清理任务运行态（state + 日志流）。"""
        client = self._ensure_client()
        if client is not None:
            try:
                client.delete(self._key_state(task_id), self._key_logs(task_id))
            except Exception as exc:
                self._degrade_once(f"清理运行态异常（{task_id}）: {exc}")
        with self._mem_lock:
            self._mem_states.pop(task_id, None)
            self._mem_logs.pop(task_id, None)

    # ---- 内部工具 ----

    def _has_logs(self, task_id) -> bool:
        client = self._ensure_client()
        if client is not None:
            try:
                return bool(client.exists(self._key_logs(task_id)))
            except Exception as exc:
                self._degrade_once(f"运行态日志存在性检查异常（{task_id}）: {exc}")
        with self._mem_lock:
            return bool(self._mem_logs.get(task_id))

    def _write_state(self, task_id, state):
        """整键覆盖写（mark_running）。"""
        client = self._ensure_client()
        if client is not None:
            try:
                mapping = {key: str(value) for key, value in state.items()}
                pipe = client.pipeline()
                pipe.delete(self._key_state(task_id))
                pipe.hset(self._key_state(task_id), mapping=mapping)
                pipe.expire(self._key_state(task_id), self._ttl)
                pipe.execute()
                return
            except Exception as exc:
                self._degrade_once(f"写入运行态异常（{task_id}）: {exc}")
        with self._mem_lock:
            self._mem_states[task_id] = dict(state)

    def _merge_state(self, task_id, fields, default_status=None):
        """字段合并写（进度/取消热路径）；降级内存时同样合并。"""
        client = self._ensure_client()
        if client is not None:
            try:
                mapping = {key: str(value) for key, value in fields.items()}
                if default_status is not None:
                    pipe = client.pipeline()
                    pipe.hsetnx(
                        self._key_state(task_id), _STATE_FIELD_STATUS, default_status
                    )
                    pipe.hset(self._key_state(task_id), mapping=mapping)
                    pipe.expire(self._key_state(task_id), self._ttl)
                    pipe.execute()
                else:
                    if not client.exists(self._key_state(task_id)):
                        return
                    pipe = client.pipeline()
                    pipe.hset(self._key_state(task_id), mapping=mapping)
                    pipe.expire(self._key_state(task_id), self._ttl)
                    pipe.execute()
                return
            except Exception as exc:
                self._degrade_once(f"合并运行态异常（{task_id}）: {exc}")
        with self._mem_lock:
            state = self._mem_states.setdefault(
                task_id,
                {
                    _STATE_FIELD_STATUS: default_status or "running",
                    _STATE_FIELD_CURRENT_STEP: 0,
                    _STATE_FIELD_TOTAL_STEPS: 0,
                    _STATE_FIELD_HEARTBEAT: _now_iso(),
                },
            )
            state.update(fields)

    @staticmethod
    def _parse_state(raw):
        state = dict(raw)
        for field in _INT_STATE_FIELDS:
            if field in state:
                try:
                    state[field] = int(state[field])
                except (TypeError, ValueError):
                    state[field] = None
        return state


# ---- 进程内单例与模块级便捷入口 ----

_store: TaskRuntimeStateStore | None = None


def get_runtime_state_store() -> TaskRuntimeStateStore:
    global _store
    if _store is None:
        _store = TaskRuntimeStateStore.from_env()
    return _store


def configure_runtime_state_store(store: TaskRuntimeStateStore) -> None:
    """测试注入替身/重置单例（传 None 恢复环境默认）。"""
    global _store
    _store = store


def read_task_logs(task_id, limit=500):
    """任务日志统一读取：运行态存在读 Redis 日志流，否则读数据库。"""
    store = get_runtime_state_store()
    if store.has_state(task_id):
        try:
            return store.get_logs(task_id, limit=limit)
        except Exception as exc:
            logger.error("读取任务运行态日志失败（%s）: %s", task_id, exc)
    return task_log_repository.list_by_task(task_id, limit=limit)


def reconcile_all_runtime_states() -> int:
    """启动对账：回灌上一进程遗留的全部运行态（进度/日志），返回对账任务数。

    只回灌进度与日志，不改任务状态列——遗留的 running 里程碑行由既有的
    check_and_cleanup_dead_tasks 复位为待启动；断点重启据此读到最新进度。
    必须在裁决层 namespace_reset 之前调用（reset 会清空 rt:* 键）。
    """
    store = get_runtime_state_store()
    reconciled = 0
    for task_id in store.list_active_ids():
        try:
            if store.sync_snapshot(task_id) is not None:
                reconciled += 1
                logger.info("启动对账：任务 %s 运行态已回灌数据库", task_id)
        except Exception as exc:
            logger.error("启动对账失败（task_id=%s）: %s", task_id, exc)
    return reconciled
