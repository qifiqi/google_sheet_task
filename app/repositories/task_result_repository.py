"""TaskResult / TaskResultReturn 仓储（契约见 docs/design/data-layer-refactor/02 §2.2）。"""
from sqlalchemy.orm import load_only

from app.extensions import db
from app.exceptions import NotFoundError
from app.models import Task, TaskResult, TaskResultReturn
from app.repositories.base import BaseRepository

# /api/results 列表的历史精简投影键（template_api load_only 语义），保持不变。
_RESULT_SUMMARY_FIELDS = (
    TaskResult.id,
    TaskResult.task_id,
    TaskResult.step_index,
    TaskResult.success,
    TaskResult.timestamp,
)


class TaskResultRepository(BaseRepository):
    model = TaskResult

    # ---- 读 ----

    def get(self, result_id):
        result = db.session.get(TaskResult, result_id)
        return result.to_dict() if result else None

    def get_with_task_type(self, result_id):
        """返回结果 dict 并附带 task_type 键；不存在返回 None。"""
        row = (
            db.session.query(TaskResult, Task.task_type)
            .join(Task, Task.id == TaskResult.task_id)
            .filter(TaskResult.id == result_id)
            .first()
        )
        if row is None:
            return None
        result, task_type = row
        data = result.to_dict()
        data["task_type"] = task_type
        return data

    def list_by_task(self, task_id):
        return [
            r.to_dict()
            for r in TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc(), TaskResult.id.asc())
            .all()
        ]

    def list_by_task_paginated(self, task_id, page, per_page):
        """任务详情结果分页 + 成功/失败计数（task_api results 分页语义）。"""
        pagination = (
            TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc(), TaskResult.id.asc())
            .paginate(page=max(page or 1, 1), per_page=max(min(per_page or 20, 100), 1), error_out=False)
        )
        data = {
            "items": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page,
            "per_page": pagination.per_page,
        }
        data.update(self.count_by_task_success(task_id))
        return data

    def list_paginated(self, page, per_page, task_id=None):
        """/api/results 列表：保持现有 load_only 精简键与 join Task 语义。

        指定 task_id 且任务不存在时返回空页（与现状一致）；
        未指定 task_id 时按现有 distinct task_type 过滤（等价于存在结果的任务类型）。
        """
        current_page = max(page or 1, 1)
        size = max(min(per_page or 20, 100), 1)

        if task_id:
            task_exists = (
                db.session.query(Task.id).filter(Task.id == task_id).first()
            )
            if not task_exists:
                return {"results": [], "total": 0, "pages": 0, "current_page": current_page}

        query = (
            db.session.query(*_RESULT_SUMMARY_FIELDS)
            .join(Task, Task.id == TaskResult.task_id)
        )
        if task_id:
            query = query.filter(TaskResult.task_id == task_id)
        else:
            distinct_types = [row[0] for row in db.session.query(Task.task_type).distinct().all()]
            if not distinct_types:
                return {"results": [], "total": 0, "pages": 0, "current_page": current_page}
            query = query.filter(Task.task_type.in_(distinct_types))

        pagination = query.order_by(TaskResult.timestamp.desc()).paginate(
            page=current_page, per_page=size, error_out=False
        )
        results = [
            {
                "id": row.id,
                "task_id": row.task_id,
                "step_index": row.step_index,
                "success": row.success,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in pagination.items
        ]
        return {
            "results": results,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": current_page,
        }

    def count_by_task_success(self, task_id):
        """{success, failed}：任务成功/失败结果计数。"""
        success = (
            TaskResult.query.filter_by(task_id=task_id, success=True).count()
        )
        failed = (
            TaskResult.query.filter_by(task_id=task_id, success=False).count()
        )
        return {"total_success": success, "total_failed": failed}

    def latest_time_by_task(self, task_id):
        """任务最新结果时间（ISO 字符串或 None），用于本地状态检查。"""
        row = (
            TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.timestamp.desc())
            .first()
        )
        return row.timestamp.isoformat() if row else None

    def get_return_entity(self, pk):
        """TaskResultReturn 实体访问（return_series 解析工具消费实体属性）。"""
        return db.session.get(TaskResultReturn, pk)

    def list_return_entities(self, ids):
        """按主键批量取收益序列实体（预览补全 V1 指标用）。"""
        ids = {item for item in ids if item}
        if not ids:
            return []
        return TaskResultReturn.query.filter(TaskResultReturn.id.in_(ids)).all()

    def list_preview_entities(self, task_id, result_ids=None):
        """全局预览结果实体（load_only 精简列，主键精确读取避免扫描大 JSON）。"""
        query = (
            TaskResult.query
            .options(
                load_only(
                    TaskResult.id,
                    TaskResult.task_id,
                    TaskResult.step_index,
                    TaskResult.parameters,
                    TaskResult.result,
                    TaskResult.return_series_id,
                    TaskResult.success,
                    TaskResult.error_message,
                    TaskResult.timestamp,
                )
            )
            .filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        )
        if result_ids is not None:
            query = query.filter(TaskResult.id.in_(result_ids))
        return query.all()

    def list_preview_index_rows(self, task_id):
        """全局预览轻量参数索引：{id, parameters 原始串, success, step_index}。"""
        rows = (
            db.session.query(
                TaskResult.id, TaskResult.parameters, TaskResult.success, TaskResult.step_index
            )
            .filter(TaskResult.task_id == task_id)
            .order_by(TaskResult.step_index.asc(), TaskResult.id.asc())
            .all()
        )
        return [
            {"id": row.id, "parameters": row.parameters, "success": row.success, "step_index": row.step_index}
            for row in rows
        ]

    def list_by_task_paginated_raw_parameters(self, task_id, page, per_page):
        """回测详情页结果分页：parameters 保持原始 JSON 串由调用方解析，
        其余字段与 to_dict 投影一致。"""
        pagination = (
            TaskResult.query
            .options(load_only(
                TaskResult.id,
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.parameters,
                TaskResult.success,
                TaskResult.error_message,
                TaskResult.timestamp,
            ))
            .filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
            .paginate(page=max(page or 1, 1), per_page=max(min(per_page or 10, 100), 1), error_out=False)
        )
        return {
            "items": [
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "step_index": item.step_index,
                    "parameters": item.parameters,
                    "success": item.success,
                    "error_message": item.error_message,
                    "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                }
                for item in pagination.items
            ],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page,
            "per_page": pagination.per_page,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
        }

    def list_export_rows(self, task_ids):
        """批量导出投影：仅取导出所需的 (task_id, step_index, result 原始 JSON 串)。

        保持原批量导出的性能语义：跳过 parameters（单行 ~10KB 的 kline JSON）
        等大字段，仅投影导出三列。
        """
        if not task_ids:
            return []
        rows = (
            db.session.query(
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.result,
            )
            .filter(TaskResult.task_id.in_(task_ids))
            .order_by(TaskResult.task_id, TaskResult.step_index.asc())
            .all()
        )
        return [
            {"task_id": task_id, "step_index": step_index, "result": result_json}
            for task_id, step_index, result_json in rows
        ]

    # ---- TaskResult 写 ----

    def create(self, fields):
        result = TaskResult(**fields)
        db.session.add(result)
        self._commit()
        return result.to_dict()

    def bulk_create(self, rows):
        for fields in rows or []:
            db.session.add(TaskResult(**fields))
        self._commit()
        return len(rows or [])

    def delete(self, result_id, commit=True):
        result = db.session.get(TaskResult, result_id)
        if result is None:
            return False
        db.session.delete(result)
        if commit:
            self._commit()
        return True

    def delete_by_task(self, task_id, commit=True):
        deleted = (
            TaskResult.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def delete_older_than(self, cutoff, commit=True):
        """清理窗口条件压 SQL 层；返回删除行数。"""
        deleted = (
            TaskResult.query.filter(TaskResult.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def list_ids_older_than(self, cutoff, limit):
        """到期结果 id 分批读取（调度清理的批量语义）。"""
        rows = (
            TaskResult.query.filter(TaskResult.timestamp < cutoff)
            .limit(limit)
            .all()
        )
        return [row.id for row in rows]

    def delete_by_ids(self, ids, commit=True):
        """按 id 集合删除；返回删除行数。"""
        if not ids:
            return 0
        deleted = (
            TaskResult.query.filter(TaskResult.id.in_(ids))
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    # ---- TaskResultReturn 读 ----

    def get_returns(self, result_id):
        """按结果 id 取其收益序列（return_series_id 关联）。"""
        result = db.session.get(TaskResult, result_id)
        if result is None or not result.return_series_id:
            return []
        returns = (
            TaskResultReturn.query.filter_by(id=result.return_series_id)
            .all()
        )
        return [r.to_dict() for r in returns]

    def get_returns_by_task(self, task_id):
        return [
            r.to_dict()
            for r in TaskResultReturn.query.filter_by(task_id=task_id)
            .order_by(TaskResultReturn.id.asc())
            .all()
        ]

    # ---- TaskResultReturn 写 ----

    def create_return(self, fields):
        record = TaskResultReturn(**fields)
        db.session.add(record)
        self._commit()
        return record.to_dict()

    def bulk_create_returns(self, rows):
        for fields in rows or []:
            db.session.add(TaskResultReturn(**fields))
        self._commit()
        return len(rows or [])

    def delete_returns_by_task(self, task_id, commit=True):
        deleted = (
            TaskResultReturn.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted
