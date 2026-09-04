#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
定时任务独立进程执行器
在独立进程中执行定时任务，避免影响Flask主进程
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)
_scheduled_task_repository = ScheduledTaskRepository()


def execute_task(task_id, instance_id):
    """执行定时任务"""
    app = create_app()

    with app.app_context():
        try:
            task = _scheduled_task_repository.get(task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            logger.info("[Worker] 开始执行任务: %s", task.get("name"))

            function_name = task.get("task_function")
            if function_name in {
                "cleanup_old_logs",
                "cleanup_old_results",
                "cleanup_old_data",
            }:
                logger.warning(
                    "[Worker] 跳过已移除的数据清理定时任务: %s (%s)",
                    task.get("name"),
                    function_name,
                )
                success = False
            else:
                logger.error("未知函数: %s", function_name)
                success = False

            # 释放锁
            _scheduled_task_repository.save({
                **task,
                "is_running": False,
                "running_instance_id": None,
            })

            logger.info("[Worker] 任务执行%s: %s", "成功" if success else "失败", task.get("name"))
            return success

        except Exception as e:
            logger.error(f"[Worker] 执行任务异常: {e}")
            # 释放锁
            try:
                task = _scheduled_task_repository.get(task_id)
                if task and task.get("running_instance_id") == instance_id:
                    _scheduled_task_repository.save({
                        **task,
                        "is_running": False,
                        "running_instance_id": None,
                    })
            except:
                pass
            return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python scheduled_task_worker.py <task_id> <instance_id>")
        sys.exit(1)

    task_id = int(sys.argv[1])
    instance_id = sys.argv[2]

    success = execute_task(task_id, instance_id)
    sys.exit(0 if success else 1)
