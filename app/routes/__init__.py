from flask import Blueprint

def register_blueprints(app):
    """注册所有蓝图"""
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.google_sheet import google_sheet_bp
    from app.routes.scheduler_api import scheduler_api_bp
    from app.routes.xpl import xpl_bp
    from app.routes.yule import yule_bp

    app.register_blueprint(xpl_bp, url_prefix='/xpl')
    app.register_blueprint(yule_bp, url_prefix='/yule')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    # 核心 API：统一挂载到 /api 前缀
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(google_sheet_bp, url_prefix='/google-sheet')
    app.register_blueprint(scheduler_api_bp)
