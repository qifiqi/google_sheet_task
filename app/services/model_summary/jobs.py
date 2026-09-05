"""单模型历史结果汇总索引 · 重建作业与差分更新（facade 的作业 mixin）。

作业注册表（_jobs/_jobs_lock）与索引重建互斥锁（_index_lock）是门面实例状态，
由 facade.__init__ 初始化；本 mixin 只定义行为。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any

from app.models import Task, TaskLog, TaskResult, TaskResultSummaryIndex
from app.repositories import backtest_repository, task_log_repository, task_repository, task_result_repository
from app.services.model_summary import extractor
from app.utils.logger import get_logger


logger = get_logger(__name__)


class SummaryJobMixin:
    """汇总索引差分 upsert、全量 rebuild 与后台重建作业管理。"""

    def upsert_task_result(self, task_result_id: int, *, commit: bool = True) -> int:
        """处理upsert_task_result相关逻辑。"""
        with self._index_lock:
            return self._upsert_task_result_locked(task_result_id, commit=commit)

    def upsert_task(self, task_id: str, *, commit: bool = True) -> dict[str, int]:
        """Rebuild summary index rows for one task from all successful results."""
        if not task_id:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}
        with self._index_lock:
            summary = self._upsert_task_batch([task_id])
            if commit:
                task_result_repository.commit()
            return summary

    def _upsert_task_result_locked(self, task_result_id: int, *, commit: bool = True) -> int:
        """处理_upsert_task_result_locked相关逻辑。"""
        record = backtest_repository.get_task_result_pair(task_result_id)
        if not record:
            return 0
        task, result = record
        rows = extractor._extract_candidate_records(task, result)
        existing = {
            item.model_key: item
            for item in backtest_repository.find_summary_index_entities_by_result(result.id)
        }
        changed_task_ids = set()
        for row in rows:
            item = existing.get(row.model_key)
            if item is None:
                item = TaskResultSummaryIndex(task_result_id=row.task_result_id, model_key=row.model_key)
                backtest_repository.add_entity(item)
            self._apply_record(item, row)
            changed_task_ids.add(row.task_id)

        stale_keys = set(existing) - {row.model_key for row in rows}
        for key in stale_keys:
            changed_task_ids.add(existing[key].task_id)
            backtest_repository.delete_entity(existing[key])
        task_result_repository.flush()

        for changed_task_id in changed_task_ids:
            self._keep_only_best_for_task(changed_task_id)
        if commit:
            task_result_repository.commit()
        return len(rows)

    def rebuild(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        progress_task_id: str | None = None,
    ) -> dict[str, int]:
        """处理rebuild相关逻辑。"""
        with self._index_lock:
            return self._rebuild_locked(
                task_type=task_type,
                task_id=task_id,
                batch_size=batch_size,
                reset=reset,
                progress_task_id=progress_task_id,
            )

    def _rebuild_locked(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        progress_task_id: str | None = None,
    ) -> dict[str, int]:
        """处理_rebuild_locked相关逻辑。"""
        if reset:
            deleted = backtest_repository.delete_summary_index_by_scope(
                task_type=task_type, task_id=task_id
            )
        else:
            deleted = 0

        processed = 0
        processed_tasks = 0
        candidate_records = 0
        batch_size = max(1, min(int(batch_size or 20), 20))
        task_ids = self._load_rebuild_task_ids(task_type=task_type, task_id=task_id)
        total = len(task_ids)
        if progress_task_id:
            self._update_rebuild_task(
                progress_task_id,
                total_steps=total,
                current_step=0,
                message=f"准备重建索引，预计扫描 {total} 个任务，每批 {batch_size} 个任务",
            )

        for start in range(0, len(task_ids), batch_size):
            batch_task_ids = task_ids[start:start + batch_size]
            batch_result = self._upsert_task_batch(batch_task_ids)
            processed += batch_result["processed"]
            processed_tasks += batch_result["processed_tasks"]
            candidate_records += batch_result["candidate_records"]
            if progress_task_id:
                self._update_rebuild_task(
                    progress_task_id,
                    current_step=processed_tasks,
                    message=(
                        f"已处理 {processed_tasks}/{total} 个任务，"
                        f"扫描 {processed} 条结果，解析候选 {candidate_records} 条"
                    ),
                )
            task_result_repository.commit()

        deduped = self._dedupe_best_per_task(task_type=task_type, task_id=task_id)
        indexed = self._count_index_rows(task_type=task_type, task_id=task_id)
        if progress_task_id:
            self._update_rebuild_task(
                progress_task_id,
                current_step=processed_tasks,
                total_steps=total,
                message=f"索引表当前保留 {indexed} 条任务/时间分组最优记录，去重删除 {deduped} 条",
            )
        return {
            "processed": processed,
            "processed_tasks": processed_tasks,
            "indexed": indexed,
            "candidate_records": candidate_records,
            "deleted": deleted,
            "deduped": deduped,
        }

    def start_rebuild_job(
        self,
        app,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        created_by_user_id: int | None = None,
    ) -> dict[str, Any]:
        """处理start_rebuild_job相关逻辑。"""
        with self._jobs_lock:
            active_job = self._active_rebuild_job()
            if active_job:
                return active_job

            job_id = str(uuid.uuid4())
            rebuild_task = Task(
                id=job_id,
                name="单模型汇总索引重建",
                description="后台扫描历史 task_results，重建任务/股票汇总查询索引",
                task_type=extractor.MODEL_SUMMARY_REBUILD_TASK_TYPE,
                status="pending",
                config=json.dumps(
                    {
                        "task_type": task_type,
                        "task_id": task_id,
                        "batch_size": batch_size,
                        "reset": reset,
                    },
                    ensure_ascii=False,
                ),
                total_steps=0,
                current_step=0,
                created_by_user_id=created_by_user_id,
            )
            task_repository.add_entity(rebuild_task)
            task_log_repository.add_entity(
                TaskLog(task_id=job_id, level="info", message="索引重建任务已创建")
            )
            task_result_repository.commit()

            job = {
                "job_id": job_id,
                "task_id": job_id,
                "status": "pending",
                "message": "索引重建任务已创建",
                "params": {
                    "task_type": task_type,
                    "task_id": task_id,
                    "batch_size": batch_size,
                    "reset": reset,
                },
                "result": None,
                "error": None,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
            }
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_rebuild_job,
            args=(app, job_id),
            daemon=True,
            name=f"model-summary-rebuild-{job_id[:8]}",
        )
        thread.start()
        return job.copy()

    def _active_rebuild_job(self) -> dict[str, Any] | None:
        """处理_active_rebuild_job相关逻辑。"""
        latest_task_id = task_repository.get_latest_task_id_by_type(
            extractor.MODEL_SUMMARY_REBUILD_TASK_TYPE,
            statuses=extractor.ACTIVE_REBUILD_TASK_STATUSES,
        )
        if not latest_task_id:
            return None

        job = self._job_from_task(latest_task_id)
        if job:
            job["message"] = f"已有索引重建任务正在执行: {latest_task_id}"
        return job

    def get_rebuild_job(self, job_id: str) -> dict[str, Any] | None:
        """处理get_rebuild_job相关逻辑。"""
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                return self._job_with_task_status(dict(job))
        return self._job_from_task(job_id)

    def latest_rebuild_job(self) -> dict[str, Any] | None:
        """处理latest_rebuild_job相关逻辑。"""
        with self._jobs_lock:
            if not self._jobs:
                latest_task_id = task_repository.get_latest_task_id_by_type(
                    extractor.MODEL_SUMMARY_REBUILD_TASK_TYPE
                )
                return self._job_from_task(latest_task_id) if latest_task_id else None
            job = max(self._jobs.values(), key=lambda item: item.get("started_at") or "")
            return self._job_with_task_status(dict(job))

    def _run_rebuild_job(self, app, job_id: str) -> None:
        """处理_run_rebuild_job相关逻辑。"""
        with self._jobs_lock:
            job = self._jobs[job_id]
            params = dict(job["params"])
        try:
            with app.app_context():
                self._update_rebuild_task(
                    job_id,
                    status="running",
                    start_time=datetime.now(),
                    message="索引重建开始执行",
                )
                with self._jobs_lock:
                    self._jobs[job_id].update({
                        "status": "running",
                        "message": "索引重建开始执行",
                    })
                result = self.rebuild(**params, progress_task_id=job_id)
                with self._jobs_lock:
                    self._jobs[job_id].update({
                        "result": result,
                    })
                self._update_rebuild_task(
                    job_id,
                    status="completed",
                    end_time=datetime.now(),
                    current_step=result.get("processed_tasks", 0),
                    message=(
                        f"扫描 {result.get('processed', 0)} 条结果，"
                        f"保留 {result.get('indexed', 0)} 条任务/时间分组最优索引，"
                        f"删除 {result.get('deleted', 0)} 条旧索引，"
                        f"去重 {result.get('deduped', 0)} 条"
                    ),
                )
            with self._jobs_lock:
                self._jobs[job_id].update({
                    "status": "completed",
                    "message": "索引重建完成",
                    "finished_at": datetime.now().isoformat(),
                })
        except Exception as exc:
            logger.error("后台重建单模型汇总索引失败: %s", exc, exc_info=True)
            with app.app_context():
                self._update_rebuild_task(
                    job_id,
                    status="error",
                    end_time=datetime.now(),
                    error_message=str(exc),
                    message=f"索引重建失败: {exc}",
                    level="error",
                )
            with self._jobs_lock:
                self._jobs[job_id].update({
                    "status": "error",
                    "message": "索引重建失败",
                    "error": str(exc),
                    "finished_at": datetime.now().isoformat(),
                })

    def _apply_record(self, item: TaskResultSummaryIndex, row: extractor.SummaryRecord) -> None:
        """处理_apply_record相关逻辑。"""
        item.task_id = row.task_id
        item.task_result_id = row.task_result_id
        item.task_type = row.task_type
        item.task_name = row.task_name
        item.stock_code = row.stock_code
        item.stock_name = row.stock_name
        item.model_key = row.model_key
        item.model_name = row.model_name
        item.year_label = row.year_label
        item.period_key = row.period_key
        item.kline_range = row.kline_range
        item.parameter_summary = extractor._json_text(row.parameter_summary)
        item.best_metric_name = row.best_metric_name
        item.best_metric_value = row.best_metric_value
        item.metrics_json = extractor._json_text(row.metrics)
        item.result_timestamp = row.result_timestamp

    def _upsert_batch(self, batch: list[tuple[Task, TaskResult]]) -> int:
        """处理_upsert_batch相关逻辑。"""
        result_ids = [result.id for _task, result in batch]
        existing_items = (
            backtest_repository.find_summary_index_entities_by_result_ids(result_ids)
        )
        existing = {
            (item.task_result_id, item.model_key): item
            for item in existing_items
        }
        seen_keys = set()
        changed_task_ids = set()
        indexed = 0

        for task, result in batch:
            rows = extractor._extract_candidate_records(task, result)
            indexed += len(rows)
            for row in rows:
                key = (row.task_result_id, row.model_key)
                seen_keys.add(key)
                item = existing.get(key)
                if item is None:
                    item = TaskResultSummaryIndex(
                        task_result_id=row.task_result_id,
                        model_key=row.model_key,
                    )
                    backtest_repository.add_entity(item)
                self._apply_record(item, row)
                changed_task_ids.add(row.task_id)

        for key, item in existing.items():
            if key not in seen_keys:
                changed_task_ids.add(item.task_id)
                backtest_repository.delete_entity(item)

        task_result_repository.flush()
        for changed_task_id in changed_task_ids:
            self._keep_only_best_for_task(changed_task_id)
        return indexed

    def _load_rebuild_task_ids(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
    ) -> list[str]:
        """处理_load_rebuild_task_ids相关逻辑。"""
        return backtest_repository.list_finished_task_ids(
            extractor.FINISHED_TASK_STATUSES,
            extractor.SUPPORTED_TASK_TYPES,
            task_type=task_type,
            task_id=task_id,
        )

    def _upsert_task_batch(self, task_ids: list[str]) -> dict[str, int]:
        """处理_upsert_task_batch相关逻辑。"""
        if not task_ids:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}

        batch = backtest_repository.list_task_result_pairs_for_rebuild(task_ids)
        best_by_group: dict[tuple[str, str], extractor.SummaryRecord] = {}
        candidate_records = 0

        for task, result in batch:
            for row in extractor._extract_candidate_records(task, result):
                candidate_records += 1
                key = (row.task_id, extractor._summary_record_group_key(row))
                current = best_by_group.get(key)
                if current is None or self._is_better_record(row, current):
                    best_by_group[key] = row

        backtest_repository.delete_summary_index_by_task_ids(task_ids, commit=False)
        task_result_repository.flush()

        for row in best_by_group.values():
            item = TaskResultSummaryIndex(
                task_result_id=row.task_result_id,
                model_key=row.model_key,
                is_best=True,
            )
            self._apply_record(item, row)
            backtest_repository.add_entity(item)

        task_result_repository.flush()
        return {
            "processed": len(batch),
            "processed_tasks": len(task_ids),
            "candidate_records": candidate_records,
        }

    def _is_better_record(self, candidate: extractor.SummaryRecord, current: extractor.SummaryRecord) -> bool:
        """处理_is_better_record相关逻辑。"""
        candidate_value = candidate.best_metric_value
        current_value = current.best_metric_value
        if candidate_value is None:
            return False
        if current_value is None:
            return True
        if candidate_value != current_value:
            return candidate_value > current_value
        candidate_timestamp = candidate.result_timestamp or datetime.min
        current_timestamp = current.result_timestamp or datetime.min
        if candidate_timestamp != current_timestamp:
            return candidate_timestamp > current_timestamp
        return candidate.task_result_id > current.task_result_id

    def _count_index_rows(self, task_type: str | None = None, task_id: str | None = None) -> int:
        """处理_count_index_rows相关逻辑。"""
        return backtest_repository.count_index_rows(task_type=task_type, task_id=task_id)

    def _dedupe_best_per_task(self, task_type: str | None = None, task_id: str | None = None) -> int:
        """处理_dedupe_best_per_task相关逻辑。"""
        return backtest_repository.dedupe_best_per_task(
            task_type=task_type,
            task_id=task_id,
        )

    def _keep_only_best_for_task(self, task_id: str) -> None:
        """处理_keep_only_best_for_task相关逻辑。"""
        rows = backtest_repository.find_summary_index_entities_by_task_ordered(task_id)
        seen_groups: set[str] = set()
        for row in rows:
            group_key = row.period_key or row.year_label or row.kline_range or ""
            if group_key not in seen_groups and row.best_metric_value is not None:
                seen_groups.add(group_key)
                row.is_best = True
                continue
            backtest_repository.delete_entity(row)

    def _update_rebuild_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        current_step: int | None = None,
        total_steps: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        error_message: str | None = None,
        message: str | None = None,
        level: str = "info",
    ) -> None:
        """处理_update_rebuild_task相关逻辑。"""
        task = task_repository.get_entity(task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if current_step is not None:
            task.current_step = current_step
        if total_steps is not None:
            task.total_steps = total_steps
        if start_time is not None:
            task.start_time = start_time
        if end_time is not None:
            task.end_time = end_time
        if error_message is not None:
            task.error_message = error_message
        if message:
            task_log_repository.add_entity(
                TaskLog(task_id=task_id, level=level, message=message)
            )
        task_result_repository.commit()

    def _job_with_task_status(self, job: dict[str, Any]) -> dict[str, Any]:
        """处理_job_with_task_status相关逻辑。"""
        task_id = job.get("task_id") or job.get("job_id")
        task = task_repository.get_entity(task_id) if task_id else None
        if task:
            job["task"] = task.to_dict()
            job["status"] = task.status
            if task.status == "completed":
                job["message"] = "索引重建完成"
            elif task.status == "error":
                job["message"] = task.error_message or "索引重建失败"
        return job

    def _job_from_task(self, task_id: str | None) -> dict[str, Any] | None:
        """处理_job_from_task相关逻辑。"""
        if not task_id:
            return None
        task = task_repository.get_entity(task_id)
        if not task or task.task_type != extractor.MODEL_SUMMARY_REBUILD_TASK_TYPE:
            return None
        config = extractor._parse_json(task.config, {})
        return {
            "job_id": task.id,
            "task_id": task.id,
            "status": task.status,
            "message": task.error_message or task.status,
            "params": config if isinstance(config, dict) else {},
            "result": None,
            "error": task.error_message,
            "started_at": task.start_time.isoformat() if task.start_time else None,
            "finished_at": task.end_time.isoformat() if task.end_time else None,
            "task": task.to_dict(),
        }
