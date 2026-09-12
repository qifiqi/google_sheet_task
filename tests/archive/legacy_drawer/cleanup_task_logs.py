#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库清理脚本 - 清理旧的 TaskLog 数据

由于日志系统已改为文件存储，数据库中的 TaskLog 表数据已不再使用。
此脚本用于清理这些历史数据，释放数据库空间。

使用方法：
    python cleanup_task_logs.py

注意：运行前请先备份数据库！
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.extensions import db
from app.models import TaskLog
from sqlalchemy import text


def get_db_size(db_path):
    """获取数据库文件大小（MB）"""
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_mb = size_bytes / (1024 * 1024)
        return size_mb
    return 0


def get_tasklog_count():
    """获取 TaskLog 表中的记录数"""
    try:
        count = TaskLog.query.count()
        return count
    except Exception as e:
        print(f"警告：无法查询 TaskLog 表：{e}")
        return 0


def cleanup_task_logs(app):
    """清理 TaskLog 表数据"""
    with app.app_context():
        db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
        
        print("=" * 60)
        print("数据库清理脚本 - 清理 TaskLog 表")
        print("=" * 60)
        print()
        
        # 显示清理前信息
        print("【清理前状态】")
        db_size_before = get_db_size(db_path)
        tasklog_count = get_tasklog_count()
        print(f"数据库路径: {db_path}")
        print(f"数据库大小: {db_size_before:.2f} MB")
        print(f"TaskLog 记录数: {tasklog_count:,} 条")
        print()
        
        if tasklog_count == 0:
            print("✓ TaskLog 表已经是空的，无需清理。")
            return
        
        # 确认操作
        print("⚠️  警告：此操作将删除 TaskLog 表中的所有数据！")
        print("   （日志数据不会丢失，已保存在日志文件中）")
        print()
        response = input("是否继续？[y/N]: ").strip().lower()
        
        if response != 'y':
            print("操作已取消。")
            return
        
        print()
        print("开始清理...")
        
        try:
            # 删除所有 TaskLog 数据
            print("正在删除 TaskLog 表数据...")
            deleted_count = TaskLog.query.delete()
            db.session.commit()
            print(f"✓ 已删除 {deleted_count:,} 条 TaskLog 记录")
            
            # 执行 VACUUM 压缩数据库（仅对 SQLite 有效）
            if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
                print("正在压缩数据库（VACUUM）...")
                db.session.execute(text('VACUUM'))
                db.session.commit()
                print("✓ 数据库压缩完成")
            
            # 显示清理后信息
            print()
            print("【清理后状态】")
            db_size_after = get_db_size(db_path)
            tasklog_count_after = get_tasklog_count()
            freed_space = db_size_before - db_size_after
            
            print(f"数据库大小: {db_size_after:.2f} MB")
            print(f"TaskLog 记录数: {tasklog_count_after:,} 条")
            print(f"释放空间: {freed_space:.2f} MB ({(freed_space/db_size_before*100):.1f}%)")
            print()
            print("=" * 60)
            print("✓ 清理完成！")
            print("=" * 60)
            
        except Exception as e:
            db.session.rollback()
            print()
            print(f"✗ 清理失败：{e}")
            print("数据库已回滚，没有数据被删除。")
            import traceback
            traceback.print_exc()


def main():
    """主函数"""
    try:
        # 创建 Flask 应用
        app = create_app()
        
        # 执行清理
        cleanup_task_logs(app)
        
    except Exception as e:
        print(f"错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

