"""TaskLog HTTP 仓储（本地对应 app/repositories/task_log_repository.py）。

远端 GetParamTaskLogsListRequestDto 支持 task_id / level 过滤；timestamp 条件
删除（delete_older_than）远端无范围端点，走 timestamp 升序分页扫描、遇到窗口
外记录即停（老日志排前，可提前终止）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import TaskLog
from app.repositories.http_backend.base import HttpRepositoryBase, dump_row, orm_entity_payload
from app.remote_api import RemoteApiNotFoundError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskLogHttpRepository(HttpRepositoryBase):
    """task_logs 表远程访问；数值主键。"""

    group_name = "param_task_logs"

    _DT_FIELDS = ("timestamp",)

    # 日志回灌为低价值写入：单次请求 2 秒超时快速失败（2026-10-16 裁定，
    # 远端无批量端点 E9，逐行慢写 + 失败行单独抛弃，本地文件日志有全量留存）。
    LOG_WRITE_TIMEOUT_SECONDS = 2.0

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

    # ---- 读 ----

    def get_last(self, task_id):
        """最新一条日志（看门狗活性检查）。

        TODO(db-to-http): 远端单一 order_field 无法表达 timestamp desc, id desc
        双键排序；同一时间戳多条时取返回首条。
        """
        page = self.page(
            {"task_id": task_id}, page_size=1,
            order_field="timestamp", order_type="desc",
        )
        items = page["items"]
        return items[0] if items else None

    def list_by_task(self, task_id, limit=500):
        """按时间正序返回最新 limit 条日志。"""
        page = self.page(
            {"task_id": task_id}, page_size=max(1, int(limit)),
            order_field="timestamp", order_type="desc",
        )
        return list(reversed(page["items"]))

    def list_by_task_after(self, task_id, after_id, limit=500):
        """id > after_id 的增量日志（详情页轮询游标；id asc）。

        远端无 id 游标过滤：取最近窗口后本地过滤；窗口外（日志量超 limit）
        时返回空列表，前端以全量刷新兜底。
        """
        rows = self.list_by_task(task_id, limit=limit)
        return [
            row for row in rows
            if int(row.get("id") or 0) > int(after_id)
        ]

    def list_by_task_paginated(self, task_id, page, per_page, level=None):
        payload: dict[str, Any] = {"task_id": task_id}
        if level:
            payload["level"] = level
        current_page = max(page or 1, 1)
        size = max(min(per_page or 50, 200), 1)
        result = self.page(
            payload, page_index=current_page, page_size=size,
            order_field="timestamp", order_type="desc",
        )
        total = result["total"]
        return {
            "items": result["items"],
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
            "current_page": current_page,
            "per_page": size,
        }

    def count_by_task(self, task_id):
        return self.page({"task_id": task_id}, page_size=1)["total"]

    def last_write_time(self, task_id):
        """最新日志时间（datetime 或 None）。"""
        row = self.get_last(task_id)
        if not row or not row.get("timestamp"):
            return None
        value = row["timestamp"]
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    # ---- 写 ----

    def create_log(self, task_id, level, message, commit=True):
        """写入一条任务日志（执行链每步热路径：一次 ModifyOrAdd）。"""
        log = {
            "task_id": task_id,
            "level": level,
            "message": TaskLog.normalize_message(message),
            "timestamp": datetime.now(),
        }
        return self.save(dump_row(log, datetime_fields=self._DT_FIELDS))

    def add_entity(self, entity, flush=False):
        """挂起新建日志实体（model_summary 重建作业消费）：ORM 实体远端落库。

        日志主键由远端自增，不携带本地 id。
        """
        payload = orm_entity_payload(entity)
        payload.pop("id", None)
        payload["message"] = TaskLog.normalize_message(payload.get("message") or "")
        return self.save(dump_row(payload, datetime_fields=self._DT_FIELDS))

    def create_logs(self, task_id, logs, commit=True):
        """批量写入任务日志（任务结束快照回灌，保序）——best-effort 语义。

        远端无批量创建端点（E9 已裁定不提供，2026-10-16）：逐行 ModifyOrAdd
        慢写，单次 2 秒超时；失败仅抛弃当前一条并继续写剩余（不重试），
        收尾统一汇总成功/抛弃条数——本地文件日志有全量留存，Redis 侧日志
        流在回灌后随快照清理。
        """
        created = []
        dropped = 0
        last_error = None
        for item in logs or []:
            payload = {
                "task_id": task_id,
                "level": item.get("level") or "info",
                "message": TaskLog.normalize_message(item.get("message") or ""),
                "timestamp": item.get("timestamp") or datetime.now(),
            }
            try:
                created.append(self.save(
                    dump_row(payload, datetime_fields=self._DT_FIELDS),
                    timeout=self.LOG_WRITE_TIMEOUT_SECONDS,
                ))
            except Exception as exc:
                dropped += 1
                last_error = exc
        if dropped:
            logger.warning(
                "任务日志回灌完成：成功 %d 条，失败抛弃 %d 条（不重试，本地文件日志有留存）: "
                "task_id=%s last_error=%s",
                len(created),
                dropped,
                task_id,
                last_error,
            )
        return created

    def delete_by_task(self, task_id, commit=True):
        """按任务删除全部日志；远端 Delete 按 task_id 整任务删除（单调用原子）。

        task_id 须与行内存储形式一致；行不存在时不调用远端
        （远端 0 行匹配报"操作失败"）。
        """
        rows = list(self.iter_pages({"task_id": task_id}))
        if not rows:
            return 0
        self.api.param_task_logs.delete({"task_id": task_id})
        return len(rows)

    def delete_older_than(self, cutoff, commit=True):
        """清理窗口条件：timestamp 升序扫描（老日志排前），越界即停。

        远端无行级删除（Delete 按 task_id 整任务删除）：批内行按任务去重后
        逐任务整删，同任务较新日志会被一并删除（远端语义即任务级）。
        """
        task_ids: list[Any] = []
        seen: set[Any] = set()
        for row in self.iter_pages({}, order_field="timestamp", order_type="asc"):
            ts = self._parse_dt(row.get("timestamp"))
            if ts is None or ts >= cutoff:
                break
            tid = row.get("task_id")
            if tid and tid not in seen:
                seen.add(tid)
                task_ids.append(tid)
        deleted = 0
        for tid in task_ids:
            try:
                self.api.param_task_logs.delete({"task_id": tid})
                deleted += 1
            except RemoteApiNotFoundError:
                continue
        return deleted

    def list_rows_older_than(self, cutoff, limit):
        """到期日志行分批读取（调度清理的批量语义）。"""
        rows: list[dict[str, Any]] = []
        for row in self.iter_pages({}, order_field="timestamp", order_type="asc"):
            ts = self._parse_dt(row.get("timestamp"))
            if ts is None or ts >= cutoff:
                break
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def delete_rows(self, rows, commit=True):
        """按行集合删除；远端无行级端点，按行归属任务去重后整任务删除。

        同任务未入批的其余日志会被一并删除（远端 Delete 语义即任务级）；
        返回提交删除的批次行数。
        """
        if not rows:
            return 0
        task_ids: list[Any] = []
        seen: set[Any] = set()
        for row in rows:
            tid = row.get("task_id")
            if tid and tid not in seen:
                seen.add(tid)
                task_ids.append(tid)
        for tid in task_ids:
            self.api.param_task_logs.delete({"task_id": tid})
        return len(rows)

    @staticmethod
    def _parse_dt(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
