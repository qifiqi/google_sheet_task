#!/usr/bin/env python3
"""
测试定时任务功能
"""
import os
import sys
from datetime import datetime
from app import create_app
from app.extensions import db
from app.models import ScheduledTask
from app.services.scheduler_service import scheduler_service

def test_scheduler():
    """测试定时任务功能"""
    app = create_app()
    
    with app.app_context():
        # 创建数据库表
        db.create_all()
        
        print("=== 定时任务功能测试 ===")
        
        # 测试创建定时任务
        print("\n1. 测试创建定时任务...")
        task = ScheduledTask(
            name='测试清理任务',
            description='测试用的清理任务',
            cron_expression='0 2 * * *',  # 每天凌晨2点
            task_type='cleanup',
            task_function='cleanup_old_data',
            task_params='{"days": 7}',
            is_active=True
        )
        
        db.session.add(task)
        db.session.commit()
        print(f"✓ 创建定时任务成功: {task.name} (ID: {task.id})")
        
        # 测试查询定时任务
        print("\n2. 测试查询定时任务...")
        tasks = ScheduledTask.query.all()
        print(f"✓ 查询到 {len(tasks)} 个定时任务")
        for t in tasks:
            print(f"  - {t.name}: {t.cron_expression} ({'启用' if t.is_active else '禁用'})")
        
        # 测试调度器服务
        print("\n3. 测试调度器服务...")
        try:
            # 启动调度器（不延时）
            scheduler_service._start_scheduler()
            print(f"✓ 调度器启动成功，运行状态: {scheduler_service.is_running}")
            
            # 添加任务到调度器
            if scheduler_service.add_job(task):
                print(f"✓ 任务添加到调度器成功: {task.name}")
            
            # 获取任务状态
            status = scheduler_service.get_job_status(task.id)
            if status:
                print(f"✓ 任务状态: {status}")
            
            # 停止调度器
            scheduler_service.stop()
            print(f"✓ 调度器停止成功")
            
        except Exception as e:
            print(f"✗ 调度器测试失败: {e}")
        
        # 测试默认任务创建
        print("\n4. 测试默认任务创建...")
        try:
            default_task = scheduler_service.create_default_tasks()
            if default_task:
                print(f"✓ 默认任务创建成功: {default_task.name}")
            else:
                print("✓ 默认任务已存在，跳过创建")
        except Exception as e:
            print(f"✗ 默认任务创建失败: {e}")
        
        print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_scheduler()
