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
import json
import time
from app import create_app
from app.extensions import db
from app.models import ScheduledTask, TaskLog, TaskResult
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
            batch_query = TaskLog.query.filter(TaskLog.timestamp < cutoff_date).limit(batch_size)
            batch_ids = [log.id for log in batch_query.all()]

            if not batch_ids:
                break

            deleted_count = TaskLog.query.filter(TaskLog.id.in_(batch_ids)).delete(synchronize_session=False)
            db.session.commit()

            total_deleted += deleted_count
            logger.info(f"已清理 {deleted_count} 条日志，总计: {total_deleted}")

            if deleted_count < batch_size:
                break

            time.sleep(delay)

        logger.info(f"清理完成，共删除 {total_deleted} 条日志")
        return True
    except Exception as e:
        logger.error(f"清理日志失败: {e}")
        db.session.rollback()
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
            batch_query = TaskResult.query.filter(TaskResult.timestamp < cutoff_date).limit(batch_size)
            batch_ids = [result.id for result in batch_query.all()]

            if not batch_ids:
                break

            deleted_count = TaskResult.query.filter(TaskResult.id.in_(batch_ids)).delete(synchronize_session=False)
            db.session.commit()

            total_deleted += deleted_count
            logger.info(f"已清理 {deleted_count} 条结果，总计: {total_deleted}")

            if deleted_count < batch_size:
                break

            time.sleep(delay)

        logger.info(f"清理完成，共删除 {total_deleted} 条结果")
        return True
    except Exception as e:
        logger.error(f"清理结果失败: {e}")
        db.session.rollback()
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
            task = ScheduledTask.query.get(task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            logger.info(f"[Worker] 开始执行任务: {task.name}")

            function_name = task.task_function
            params = json.loads(task.task_params) if task.task_params else {}

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

            # 释放锁
            task.is_running = False
            task.running_instance_id = None
            db.session.commit()

            logger.info(f"[Worker] 任务执行{'成功' if success else '失败'}: {task.name}")
            return success

        except Exception as e:
            logger.error(f"[Worker] 执行任务异常: {e}")
            # 释放锁
            try:
                task = ScheduledTask.query.get(task_id)
                if task and task.running_instance_id == instance_id:
                    task.is_running = False
                    task.running_instance_id = None
                    db.session.commit()
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

