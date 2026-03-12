from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from app.models import Task, TaskLog, TaskResult, db
from app.utils.database import safe_create


class TaskRepository:
    """集中管理任务相关的数据库读写。

    这一层刻意保持轻量，只承接持久化细节，
    让 TaskManager 更专注于流程编排和状态控制。
    """

    def get_task(self, task_id: str) -> Optional[Task]:
        """按任务 ID 获取任务模型。"""
        return Task.query.get(task_id)

    def create_task(
        self,
        *,
        task_id: str,
        name: str,
        description: str,
        task_type: str,
        config_str: str,
        status: str = "pending",
    ) -> Task:
        """创建任务记录并返回模型对象。"""
        return safe_create(
            Task,
            id=task_id,
            name=name,
            description=description,
            task_type=task_type,
            config=config_str,
            status=status,
        )

    def create_restart_task(self, original_task: Task, new_task_id: str) -> Task:
        """基于原任务复制出一个待执行的重启任务。"""
        original_config = (
            json.loads(original_task.config)
            if isinstance(original_task.config, str)
            else original_task.config
        )
        new_task = Task(
            id=new_task_id,
            name=f"{original_task.name} (重启)",
            description=f"基于任务 {original_task.id} 重启",
            task_type=original_task.task_type,
            config=json.dumps(original_config),
            status="pending",
        )
        db.session.add(new_task)
        db.session.commit()
        return new_task

    def update_task_config(
        self,
        task: Task,
        config_str: str,
        *,
        update_name: str | None = None,
        update_description: str | None = None,
    ) -> Task:
        """保存任务配置以及可选的名称、描述变更。"""
        task.config = config_str
        if update_name:
            task.name = update_name
        if update_description:
            task.description = update_description
        db.session.commit()
        return task

    def delete_task_results(self, task_id: str) -> None:
        """在从头重启前清空任务历史结果。"""
        TaskResult.query.filter_by(task_id=task_id).delete()
        db.session.commit()

    def delete_task_with_relations(self, task: Task) -> None:
        """连同日志和结果一起删除任务。"""
        TaskResult.query.filter_by(task_id=task.id).delete()
        TaskLog.query.filter_by(task_id=task.id).delete()
        db.session.delete(task)
        db.session.commit()

    def mark_task_cancelled(self, task: Task) -> Task:
        """将任务状态持久化为已取消。"""
        task.status = "cancelled"
        task.end_time = datetime.now()
        db.session.commit()
        return task


task_repository = TaskRepository()
