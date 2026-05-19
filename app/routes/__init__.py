from flask import Blueprint

def register_blueprints(app):
    """注册所有蓝图"""
    from app.routes.auth_pages import auth_pages_bp
    from app.routes.admin import admin_bp
    from app.routes.task_api import task_api_bp
    from app.routes.config_api import config_api_bp
    from app.routes.template_api import template_api_bp
    from app.routes.google_sheet_api import google_sheet_api_bp
    from app.routes.database_api import database_api_bp
    from app.routes.stock_api import stock_api_bp
    from app.routes.google_sheet import google_sheet_bp
    from app.routes.scheduler_api import scheduler_api_bp
    from app.routes.xpl import xpl_bp
    from app.routes.yule import yule_bp
    from app.routes.backtest_training import bp as backtest_training_bp
    from app.routes.backtest_multi_product import bp as backtest_multi_product_bp
    from app.routes.meta_api import meta_api_bp
    from app.routes.auth_api import auth_api_bp

    app.register_blueprint(auth_pages_bp)
    app.register_blueprint(xpl_bp, url_prefix='/xpl')
    app.register_blueprint(yule_bp, url_prefix='/yule')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # 拆分后的 API 模块
    app.register_blueprint(task_api_bp, url_prefix='/api')
    app.register_blueprint(config_api_bp, url_prefix='/api')
    app.register_blueprint(template_api_bp, url_prefix='/api')
    app.register_blueprint(google_sheet_api_bp, url_prefix='/api')
    app.register_blueprint(database_api_bp, url_prefix='/api')
    app.register_blueprint(stock_api_bp, url_prefix='/api')

    app.register_blueprint(google_sheet_bp, url_prefix='/google-sheet')
    app.register_blueprint(scheduler_api_bp)
    app.register_blueprint(backtest_training_bp)
    app.register_blueprint(backtest_multi_product_bp)
    app.register_blueprint(meta_api_bp, url_prefix='/api')
    app.register_blueprint(auth_api_bp, url_prefix='/api')
