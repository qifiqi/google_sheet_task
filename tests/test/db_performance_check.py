#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库性能检查工具

快速检查数据库性能状态，提供优化建议

使用方法：
    python db_performance_check.py
    python db_performance_check.py --vacuum  # 压缩数据库
    python db_performance_check.py --full    # 完整报告
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.utils.db_monitor import DatabaseMonitor


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_database_info(report: dict):
    """打印数据库信息"""
    print_section("数据库信息")
    db_info = report.get('database', {})
    if 'error' in db_info:
        print(f"错误: {db_info['error']}")
    else:
        print(f"类型: {db_info.get('type', 'N/A')}")
        if 'path' in db_info:
            print(f"路径: {db_info['path']}")
        print(f"大小: {db_info.get('size_human', 'N/A')} ({db_info.get('size_mb', 0):.2f} MB)")


def print_table_stats(report: dict):
    """打印表统计信息"""
    print_section("数据表统计")
    tables = report.get('tables', {})
    
    if 'error' in tables:
        print(f"错误: {tables['error']}")
        return
    
    # 任务统计
    if 'tasks' in tables:
        tasks = tables['tasks']
        print(f"\n📋 Tasks表: {tasks['count']:,} 条记录")
        if 'by_status' in tasks:
            for status, count in tasks['by_status'].items():
                print(f"   - {status}: {count:,}")
    
    # 结果统计
    if 'task_results' in tables:
        results = tables['task_results']
        print(f"\n📊 TaskResults表: {results['count']:,} 条记录")
        print(f"   - 成功: {results.get('success', 0):,}")
        print(f"   - 失败: {results.get('failed', 0):,}")
    
    # 日志统计
    if 'task_logs' in tables:
        logs = tables['task_logs']
        print(f"\n📝 TaskLogs表: {logs['count']:,} 条记录")
        if logs.get('note'):
            print(f"   注意: {logs['note']}")
    
    # 模板统计
    if 'task_templates' in tables:
        templates = tables['task_templates']
        print(f"\n📑 Templates表: {templates['count']:,} 条记录")
    
    # 配置统计
    if 'system_configs' in tables:
        configs = tables['system_configs']
        print(f"\n⚙️  SystemConfigs表: {configs['count']:,} 条记录")


def print_connection_pool(report: dict):
    """打印连接池状态"""
    print_section("连接池状态")
    pool = report.get('connection_pool', {})
    
    if 'error' in pool:
        print(f"错误: {pool['error']}")
    else:
        print(f"连接池大小: {pool.get('pool_size', 0)}")
        print(f"已签入连接: {pool.get('checked_in', 0)}")
        print(f"已签出连接: {pool.get('checked_out', 0)}")
        print(f"溢出连接: {pool.get('overflow', 0)}")
        print(f"总连接数: {pool.get('total_connections', 0)}")
        
        status = pool.get('status', 'unknown')
        status_icon = "✓" if status == 'healthy' else "⚠"
        print(f"状态: {status_icon} {status}")


def print_recent_activity(report: dict):
    """打印最近活动"""
    print_section("最近活动（24小时）")
    activity = report.get('recent_activity', {})
    
    if 'error' in activity:
        print(f"错误: {activity['error']}")
    else:
        print(f"创建任务: {activity.get('tasks_created', 0):,}")
        print(f"完成任务: {activity.get('tasks_completed', 0):,}")
        print(f"生成结果: {activity.get('results_generated', 0):,}")


def print_suggestions(report: dict):
    """打印优化建议"""
    print_section("优化建议")
    suggestions = report.get('suggestions', [])
    
    if not suggestions:
        print("✓ 暂无优化建议")
        return
    
    priority_order = {'high': 1, 'medium': 2, 'low': 3, 'info': 4, 'error': 0}
    sorted_suggestions = sorted(suggestions, key=lambda x: priority_order.get(x.get('priority', 'low'), 3))
    
    for i, suggestion in enumerate(sorted_suggestions, 1):
        priority = suggestion.get('priority', 'info')
        priority_icon = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢',
            'info': 'ℹ️',
            'error': '❌'
        }.get(priority, '•')
        
        print(f"\n{priority_icon} 建议 {i} [{priority.upper()}]")
        print(f"   类别: {suggestion.get('category', 'N/A')}")
        print(f"   问题: {suggestion.get('issue', 'N/A')}")
        print(f"   建议: {suggestion.get('suggestion', 'N/A')}")
        if suggestion.get('benefit'):
            print(f"   效果: {suggestion['benefit']}")


def perform_vacuum():
    """执行数据库压缩"""
    print_section("数据库压缩")
    
    print("⚠️  警告：此操作可能需要一些时间...")
    response = input("确认执行压缩？[y/N]: ").strip().lower()
    
    if response != 'y':
        print("操作已取消")
        return
    
    print("\n正在压缩数据库...")
    result = DatabaseMonitor.vacuum_database()
    
    if result.get('success'):
        print(f"\n✓ {result.get('message', '压缩完成')}")
        print(f"   压缩前: {result.get('size_before_mb', 0):.2f} MB")
        print(f"   压缩后: {result.get('size_after_mb', 0):.2f} MB")
        print(f"   释放空间: {result.get('freed_mb', 0):.2f} MB")
    else:
        print(f"\n✗ 压缩失败: {result.get('error', result.get('message', '未知错误'))}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库性能检查工具')
    parser.add_argument('--vacuum', action='store_true', help='执行数据库压缩（VACUUM）')
    parser.add_argument('--full', action='store_true', help='显示完整报告')
    parser.add_argument('--json', action='store_true', help='以JSON格式输出')
    
    args = parser.parse_args()
    
    try:
        # 创建Flask应用
        app = create_app()
        
        with app.app_context():
            if args.vacuum:
                perform_vacuum()
            else:
                # 获取报告
                report = DatabaseMonitor.get_full_report()
                
                if args.json:
                    import json
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    # 打印报告
                    print("\n" + "=" * 60)
                    print("  数据库性能检查报告")
                    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    print("=" * 60)
                    
                    print_database_info(report)
                    print_table_stats(report)
                    print_connection_pool(report)
                    print_recent_activity(report)
                    print_suggestions(report)
                    
                    if args.full:
                        # 显示索引信息
                        print_section("索引信息")
                        indexes = report.get('indexes', {})
                        if 'error' in indexes:
                            print(f"错误: {indexes['error']}")
                        elif 'message' in indexes:
                            print(indexes['message'])
                        else:
                            for table, idx_list in indexes.items():
                                print(f"\n{table}:")
                                for idx in idx_list:
                                    print(f"   - {idx}")
                    
                    print("\n" + "=" * 60)
                    print("检查完成！")
                    print("=" * 60)
                    
                    # 提示
                    high_priority = [s for s in report.get('suggestions', []) if s.get('priority') == 'high']
                    if high_priority:
                        print(f"\n⚠️  发现 {len(high_priority)} 个高优先级问题需要处理！")
    
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

