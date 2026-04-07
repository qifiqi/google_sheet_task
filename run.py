#!/usr/bin/env python3
"""
应用启动文件
"""
import os
import time
from datetime import datetime
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db
from app.models import Task, TaskLog, TaskResult, SystemConfig, ScheduledTask, GoogleSheetToken, User, Role, Permission
from app.config import init_config as init_config2, PERMISSIONS, NAV_MENU
from app.utils.logger import initialize_logging
app = create_app()


def ensure_google_sheet_token_schema():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'google_sheet_tokens' not in tables:
        return

    columns = {column['name'] for column in inspector.get_columns('google_sheet_tokens')}
    if 'current_in_use_count' not in columns:
        # 轻量补字段，避免线上已有库因为没有迁移脚本而启动失败。
        db.session.execute(
            text("ALTER TABLE google_sheet_tokens ADD COLUMN current_in_use_count INTEGER NOT NULL DEFAULT 0")
        )
        db.session.commit()


def reset_google_sheet_token_occupancy():
    # current_in_use_count 表示进程内”正在占用”的资源。
    # 应用重启后原线程已经不存在，因此启动时统一清零,避免脏占用残留。
    if GoogleSheetToken.query.filter(GoogleSheetToken.current_in_use_count != 0).count() > 0:
        GoogleSheetToken.query.update({'current_in_use_count': 0}, synchronize_session=False)
        db.session.commit()


def reset_google_sheet_occupancy():
    # 应用重启后原线程已经不存在，清理所有 Google Sheet 的占用状态
    from app.models import GoogleSheet
    if GoogleSheet.query.filter(GoogleSheet.is_in_use == True).count() > 0:
        GoogleSheet.query.update({'is_in_use': False, 'current_task_id': None}, synchronize_session=False)
        db.session.commit()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'Task': Task,
        'TaskLog': TaskLog,
        'TaskResult': TaskResult,
        'SystemConfig': SystemConfig,
        'ScheduledTask': ScheduledTask,
        'GoogleSheetToken': GoogleSheetToken
    }

@app.cli.command()
def init_db():
    """初始化数据库"""
    db.create_all()
    ensure_google_sheet_token_schema()
    print("数据库初始化完成")

@app.cli.command()
def init_config():
    """初始化默认配置"""
    init_config2()
    print("默认配置初始化完成")

def check_and_cleanup_dead_tasks():
    """启动时检查并清理挂死的任务"""
    from app.services.task_manager import task_manager
    from app.utils.logger import get_logger
    
    logger = get_logger('startup')
    
    with app.app_context():
        try:
            # 获取所有运行状态的任务
            running_tasks = Task.query.filter_by(status='running').all()
            
            if not running_tasks:
                logger.info("没有发现运行中的任务")
                return
            
            logger.info(f"发现 {len(running_tasks)} 个运行中的任务，开始检查状态")
             
            for task in running_tasks:
                status_check = task_manager.check_local_task_status(task.id)
                
                if status_check.get("can_restart", False):
                    logger.info(f"发现中断的任务: {task.id} - {status_check.get('restart_reason')}")
                    
                    # 重置任务状态为pending，允许用户重新启动
                    task.status = 'pending'
                    task.error_message = None  # 清除之前的错误信息
                    task.end_time = None  # 清除结束时间
                    
                    # 添加日志
                    task_manager._add_task_log(
                        task.id, 
                        'info', 
                        f"应用重启时检测到任务中断，已重置为待启动状态: {status_check.get('restart_reason')}"
                    )
                    
                    logger.info(f"已将任务 {task.id} 重置为pending状态，用户可选择重新启动")

                else:
                    logger.info(f"任务 {task.id} 状态正常")
            
            db.session.commit()
            logger.info("任务状态检查完成")
            
        except Exception as e:
            logger.error(f"检查任务状态时出错: {str(e)}")

def init_scheduler():
    """初始化定时任务调度器"""
    from app.services.scheduler_service import scheduler_service
    from app.utils.logger import get_logger
    
    logger = get_logger('scheduler')
    
    with app.app_context():
        try:
            # 启动调度器（延时30秒），传递应用实例
            scheduler_service.start(delay_seconds=30, app=app)
            
            # 创建默认定时任务
            scheduler_service.create_default_tasks()
            
            logger.info("定时任务调度器初始化完成")
            
        except Exception as e:
            logger.error(f"初始化定时任务调度器失败: {e}")


def init_task_watchdog():
    """初始化任务看门狗线程"""
    from app.services.task_watchdog import task_watchdog
    from app.utils.logger import get_logger

    logger = get_logger('watchdog')

    try:
        task_watchdog.start(app)
        logger.info("任务看门狗线程已启动")
    except Exception as e:
        logger.error(f"启动任务看门狗线程失败: {e}")


def init_rbac():
    """幂等初始化权限、默认角色和管理员用户"""
    import json
    from werkzeug.security import generate_password_hash
    from app.utils.logger import get_logger
    logger = get_logger('rbac')

    # 1. 幂等插入/更新所有权限（含 route_path）
    for group, code, name, route_path in PERMISSIONS:
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            db.session.add(Permission(group=group, code=code, name=name, route_path=route_path))
        else:
            # 补充 route_path（老记录可能没有）
            if perm.route_path != route_path:
                perm.route_path = route_path
    db.session.commit()

    # 2. 确保 admin 角色存在并拥有全部权限
    admin_role = Role.query.filter_by(code='admin').first()
    if not admin_role:
        admin_role = Role(name='管理员', code='admin', description='系统管理员，拥有全部权限', is_system=True)
        db.session.add(admin_role)
        db.session.commit()
    admin_role.permissions = Permission.query.all()
    db.session.commit()

    # 3. 确保默认 admin 用户存在
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            is_active=True,
        )
        admin_user.roles = [admin_role]
        db.session.add(admin_user)
        db.session.commit()
        logger.info("已创建默认管理员用户 admin / admin123")

    # 4. 幂等写入导航菜单到 system_configs
    from app.models import SystemConfig
    nav_config = SystemConfig.query.filter_by(key='nav_menu').first()
    if not nav_config:
        db.session.add(SystemConfig(
            key='nav_menu',
            value=json.dumps(NAV_MENU, ensure_ascii=False),
            description='前端导航菜单结构（JSON），支持 permission 字段按角色过滤',
        ))
        db.session.commit()
        logger.info("已初始化导航菜单配置 nav_menu")

if __name__ == '__main__':
    from app.utils.logger import get_logger

    logger = get_logger('app')

    try:
        # 确保必要的目录存在
        os.makedirs('data', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

        # 初始化日志系统（在应用上下文之前）
        initialize_logging()

        # 初始化数据库
        with app.app_context():
            db.create_all()
            ensure_google_sheet_token_schema()
            reset_google_sheet_token_occupancy()
            reset_google_sheet_occupancy()
            init_config2()
            init_rbac()

        # 检查并清理挂死的任务
        check_and_cleanup_dead_tasks()

        # 初始化定时任务调度器
        init_scheduler()

        # 初始化任务看门狗线程
        init_task_watchdog()

        # 运行应用
        debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
        if debug_mode:
            app.run(debug=True, host='0.0.0.0', port=5000)
        else:
            app.run(debug=False, host='0.0.0.0', port=5000)
        # app.run(debug=True, host='127.0.0.1', port=5000)
        # app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"启动失败: {e}",exc_info=True)
