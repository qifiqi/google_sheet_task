from flask import Flask
from app.config import Config
from app.extensions import db, migrate
from app.routes import register_blueprints
from app.utils.ding_talk_notifier import DingTalkNotifier


def create_app():
    # 获取应用根目录
    import os
    from pathlib import Path
    
    # 获取当前文件所在目录的父目录（即项目根目录）
    current_dir = Path(__file__).parent.parent
    template_dir = current_dir / 'templates'
    static_dir = current_dir / 'static'
    
    app = Flask(__name__, 
                template_folder=str(template_dir), 
                static_folder=str(static_dir))
                
    app.config.from_object(Config)
    
    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)

    from app.services.config_manager import get_config_manager
    get_config_manager().init_app(app)

    # 仅注册原有蓝图路由，不再启用 Flask-RESTX Swagger 文档路由
    register_blueprints(app)
    
    notifier = DingTalkNotifier(
        access_token=Config.dd_access_token,
        secret=Config.dd_secret
    )

    app.notifier = notifier

    return app
