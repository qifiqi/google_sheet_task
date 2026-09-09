#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库优化一键应用脚本

自动执行所有数据库优化步骤：
1. 备份数据库
2. 应用迁移（添加索引）
3. 清理旧日志
4. 压缩数据库
5. 性能检查

使用方法：
    python apply_db_optimizations.py
    python apply_db_optimizations.py --skip-backup  # 跳过备份（不推荐）
    python apply_db_optimizations.py --no-cleanup   # 不清理旧日志
"""

import sys
import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def print_step(step_num: int, title: str):
    """打印步骤标题"""
    print("\n" + "=" * 60)
    print(f"  步骤 {step_num}: {title}")
    print("=" * 60)


def backup_database(db_path: str) -> tuple:
    """备份数据库"""
    try:
        if not os.path.exists(db_path):
            return False, f"数据库文件不存在: {db_path}"
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.backup_{timestamp}"
        
        # 复制文件
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"数据库大小: {size_mb:.2f} MB")
        print(f"备份到: {backup_path}")
        
        shutil.copy2(db_path, backup_path)
        
        if os.path.exists(backup_path):
            return True, backup_path
        else:
            return False, "备份文件创建失败"
            
    except Exception as e:
        return False, str(e)


def create_migration():
    """创建数据库迁移"""
    try:
        print("正在生成迁移文件...")
        result = os.system('flask db migrate -m "数据库性能优化：添加索引和优化配置"')
        
        if result == 0:
            return True, "迁移文件生成成功"
        else:
            return False, "迁移文件生成失败"
    except Exception as e:
        return False, str(e)


def apply_migration():
    """应用数据库迁移"""
    try:
        print("正在应用迁移...")
        result = os.system('flask db upgrade')
        
        if result == 0:
            return True, "迁移应用成功"
        else:
            return False, "迁移应用失败"
    except Exception as e:
        return False, str(e)


def cleanup_old_logs():
    """清理旧日志"""
    try:
        from app import create_app
        from app.utils.db_monitor import DatabaseMonitor
        from app.models import TaskLog
        
        app = create_app()
        
        with app.app_context():
            # 获取清理前的记录数
            count_before = TaskLog.query.count()
            
            if count_before == 0:
                return True, "TaskLog 表已经是空的，无需清理"
            
            print(f"发现 {count_before:,} 条历史日志记录")
            
            # 执行清理
            print("正在清理...")
            from app.extensions import db
            TaskLog.query.delete()
            db.session.commit()
            
            count_after = TaskLog.query.count()
            
            return True, f"已清理 {count_before:,} 条历史日志记录"
            
    except Exception as e:
        return False, str(e)


def vacuum_database():
    """压缩数据库"""
    try:
        from app import create_app
        from app.utils.db_monitor import DatabaseMonitor
        
        app = create_app()
        
        with app.app_context():
            print("正在压缩数据库...")
            result = DatabaseMonitor.vacuum_database()
            
            if result.get('success'):
                return True, result.get('message', '压缩完成')
            else:
                return False, result.get('error', result.get('message', '压缩失败'))
                
    except Exception as e:
        return False, str(e)


def performance_check():
    """性能检查"""
    try:
        from app import create_app
        from app.utils.db_monitor import DatabaseMonitor
        
        app = create_app()
        
        with app.app_context():
            report = DatabaseMonitor.get_full_report()
            
            # 打印关键信息
            db_info = report.get('database', {})
            tables = report.get('tables', {})
            
            print(f"\n数据库大小: {db_info.get('size_mb', 0):.2f} MB")
            print(f"任务数量: {tables.get('tasks', {}).get('count', 0):,}")
            print(f"结果数量: {tables.get('task_results', {}).get('count', 0):,}")
            print(f"日志数量: {tables.get('task_logs', {}).get('count', 0):,}")
            
            # 检查是否有高优先级建议
            suggestions = report.get('suggestions', [])
            high_priority = [s for s in suggestions if s.get('priority') == 'high']
            
            if high_priority:
                print(f"\n⚠️  发现 {len(high_priority)} 个高优先级问题")
                for suggestion in high_priority:
                    print(f"   - {suggestion.get('issue', 'N/A')}")
            else:
                print("\n✓ 无高优先级问题")
            
            return True, "性能检查完成"
            
    except Exception as e:
        return False, str(e)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库优化一键应用脚本')
    parser.add_argument('--skip-backup', action='store_true', help='跳过备份步骤（不推荐）')
    parser.add_argument('--no-cleanup', action='store_true', help='不清理旧日志')
    parser.add_argument('--no-vacuum', action='store_true', help='不压缩数据库')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("  数据库优化一键应用工具")
    print("=" * 60)
    print("\n本工具将执行以下优化：")
    print("  1. 备份数据库（可选）")
    print("  2. 创建并应用迁移（添加索引）")
    print("  3. 清理旧日志数据（可选）")
    print("  4. 压缩数据库（可选）")
    print("  5. 性能检查")
    print()
    
    if not args.skip_backup:
        response = input("⚠️  建议先备份数据库。是否继续？[y/N]: ").strip().lower()
        if response != 'y':
            print("操作已取消")
            return
    
    success_count = 0
    total_steps = 5
    
    # 步骤 1: 备份数据库
    if not args.skip_backup:
        print_step(1, "备份数据库")
        
        # 查找数据库文件
        db_path = 'instance/app.db'
        if not os.path.exists(db_path):
            print(f"⚠️  数据库文件不存在: {db_path}")
            print("   如果使用其他数据库，请手动备份")
        else:
            success, message = backup_database(db_path)
            if success:
                print(f"✓ {message}")
                success_count += 1
            else:
                print(f"✗ 备份失败: {message}")
                response = input("是否继续？[y/N]: ").strip().lower()
                if response != 'y':
                    print("操作已取消")
                    return
    else:
        print_step(1, "备份数据库（已跳过）")
        print("⚠️  已跳过备份步骤")
    
    # 步骤 2: 创建并应用迁移
    print_step(2, "应用数据库迁移（添加索引）")
    
    # 首先尝试创建迁移
    print("\n尝试生成迁移...")
    success, message = create_migration()
    if success:
        print(f"✓ {message}")
    else:
        print(f"⚠️  {message}")
        print("   可能已经创建过迁移，尝试直接应用...")
    
    # 应用迁移
    success, message = apply_migration()
    if success:
        print(f"✓ {message}")
        success_count += 1
    else:
        print(f"✗ {message}")
        print("   请检查迁移状态：flask db current")
        response = input("是否继续？[y/N]: ").strip().lower()
        if response != 'y':
            print("操作已终止")
            return
    
    # 步骤 3: 清理旧日志
    if not args.no_cleanup:
        print_step(3, "清理历史日志数据")
        
        response = input("是否清理 TaskLog 表中的历史数据？[y/N]: ").strip().lower()
        if response == 'y':
            success, message = cleanup_old_logs()
            if success:
                print(f"✓ {message}")
                success_count += 1
            else:
                print(f"✗ {message}")
        else:
            print("已跳过清理步骤")
    else:
        print_step(3, "清理历史日志（已跳过）")
        print("⚠️  已跳过清理步骤")
    
    # 步骤 4: 压缩数据库
    if not args.no_vacuum:
        print_step(4, "压缩数据库（VACUUM）")
        
        success, message = vacuum_database()
        if success:
            print(f"✓ {message}")
            success_count += 1
        else:
            print(f"⚠️  {message}")
            print("   VACUUM 仅支持 SQLite 数据库")
    else:
        print_step(4, "压缩数据库（已跳过）")
        print("⚠️  已跳过压缩步骤")
    
    # 步骤 5: 性能检查
    print_step(5, "性能检查")
    
    success, message = performance_check()
    if success:
        print(f"\n✓ {message}")
        success_count += 1
    else:
        print(f"\n✗ {message}")
    
    # 总结
    print("\n" + "=" * 60)
    print("  优化完成")
    print("=" * 60)
    print(f"\n成功执行: {success_count}/{total_steps} 个步骤")
    
    if success_count == total_steps:
        print("\n🎉 所有优化步骤执行成功！")
    elif success_count >= total_steps - 1:
        print("\n✓ 主要优化步骤已完成")
    else:
        print("\n⚠️  部分步骤执行失败，请查看上面的错误信息")
    
    print("\n建议：")
    print("  1. 运行性能检查: python db_performance_check.py")
    print("  2. 检查应用是否正常运行")
    print("  3. 查看优化文档: docs/数据库优化完整指南.md")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

