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

from datetime import datetime, timedelta
from app.utils.json_utils import loads
import time
from app import create_app
from app.repositories import (
    scheduled_task_repository,
    task_log_repository,
    task_result_repository,
)
from app.services.task.data_cleanup import delete_task_result_dependencies
from app.utils.logger import get_logger

logger = get_logger(__name__)


def cleanup_old_logs(params):
    """清理旧日志"""
    try:
        days = params.get('days', 10)
        batch_size = params.get('batch_size', 200)
        delay = params.get('delay', 2)
        cutoff_date = datetime.now() - timedelta(days=days)

        total_deleted = 0
        while True:
            batch_rows = task_log_repository.list_rows_older_than(cutoff_date, batch_size)

            if not batch_rows:
                break

            deleted_count = task_log_repository.delete_rows(batch_rows)

            total_deleted += deleted_count
            logger.info(f"已清理 {deleted_count} 条日志，总计: {total_deleted}")

            if deleted_count < batch_size:
                break

            time.sleep(delay)

        logger.info(f"清理完成，共删除 {total_deleted} 条日志")
        return True
    except Exception as e:
        logger.error(f"清理日志失败: {e}")
        return False


def cleanup_old_results(params):
    """清理旧结果"""
    try:
        days = params.get('days', 10)
        batch_size = params.get('batch_size', 200)
        delay = params.get('delay', 2)
        cutoff_date = datetime.now() - timedelta(days=days)

        total_deleted = 0
        while True:
            batch_rows = task_result_repository.list_rows_older_than(cutoff_date, batch_size)

            if not batch_rows:
                break

            # 远端 Delete 为任务级整删：同任务未入批行会被一并删除，
            # 依赖清理须覆盖任务全量结果行，避免汇总索引/快照链接变孤儿。
            # 行可能是 dict（http）或 ORM 实体（db），按类型取 task_id。
            dependency_ids = []
            seen_tasks = set()
            for row in batch_rows:
                tid = row.get("task_id") if isinstance(row, dict) else row.task_id
                if tid and tid not in seen_tasks:
                    seen_tasks.add(tid)
                    dependency_ids.extend(task_result_repository.list_ids_by_task(tid))
            delete_task_result_dependencies(dependency_ids)
            deleted_count = task_result_repository.delete_rows(batch_rows)

            total_deleted += deleted_count
            logger.info(f"已清理 {deleted_count} 条结果，总计: {total_deleted}")

            if deleted_count < batch_size:
                break

            time.sleep(delay)

        logger.info(f"清理完成，共删除 {total_deleted} 条结果")
        return True
    except Exception as e:
        logger.error(f"清理结果失败: {e}")
        return False


def cleanup_old_data(params):
    """清理旧数据（日志和结果）"""
    log_success = cleanup_old_logs(params)
    return log_success


def execute_task(task_id, instance_id):
    """执行定时任务"""
    app = create_app()

    with app.app_context():
        try:
            task = scheduled_task_repository.get(task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            logger.info(f"[Worker] 开始执行任务: {task['name']}")

            function_name = task['task_function']
            params = loads(task['task_params']) if task['task_params'] else {}

            # 执行对应函数
            if function_name == 'cleanup_old_logs':
                success = cleanup_old_logs(params)
            elif function_name == 'cleanup_old_results':
                success = cleanup_old_results(params)
            elif function_name == 'cleanup_old_data':
                success = cleanup_old_data(params)
            else:
                logger.error(f"未知函数: {function_name}")
                success = False

            # 释放锁（仅本实例持有者可释放）
            scheduled_task_repository.release_run_lock(task_id, instance_id)

            logger.info(f"[Worker] 任务执行{'成功' if success else '失败'}: {task['name']}")
            return success

        except Exception as e:
            logger.error(f"[Worker] 执行任务异常: {e}")
            # 释放锁（按实例条件释放，非持锁实例无副作用）
            try:
                scheduled_task_repository.release_run_lock(task_id, instance_id)
            except Exception:
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
