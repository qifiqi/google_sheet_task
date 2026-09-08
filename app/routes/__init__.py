from flask import Blueprint

def register_blueprints(app):
    """注册所有蓝图"""
    from app.routes.auth_pages import auth_pages_bp
    # 旧版 Jinja 登录页已随本地登录一并停用（Vue 前端自行处理 /login）；
    # 恢复本地登录时取消下行注释。
    # app.register_blueprint(auth_pages_bp)
    from app.routes.admin import admin_bp, legacy_admin_pages_bp
    from app.routes.task_api import task_api_bp
    # 本地路由表管理已停用，legacy_navigation 蓝图随之一并注释。
    # from app.routes.config_api import config_api_bp, legacy_navigation_bp
    from app.routes.config_api import config_api_bp
    from app.routes.template_api import template_api_bp
    from app.routes.google_sheet_api import google_sheet_api_bp
    from app.routes.database_api import database_api_bp
    # 旧版 Jinja 页面蓝图已随静态模板前端一并停用（页面由 Vue 前端提供）。
    # from app.routes.eastmoney_kline import eastmoney_kline_bp
    from app.routes.stock_api import stock_api_bp
    # from app.routes.google_sheet import google_sheet_bp
    # from app.routes.yule import yule_bp
    from app.routes.scheduler_api import scheduler_api_bp
    # xpl 蓝图仍承载 Vue 页面调用的 /analyze 等接口，仅页面路由已注释。
    from app.routes.xpl import xpl_bp
    from app.routes.backtest_training import bp as backtest_training_bp
    # from app.routes.backtest_training import legacy_bp as backtest_training_legacy_bp
    from app.routes.backtest_multi_product import bp as backtest_multi_product_bp
    # from app.routes.backtest_multi_product import legacy_bp as backtest_multi_product_legacy_bp
    from app.routes.global_preview import bp as global_preview_bp
    from app.routes.meta_api import meta_api_bp
    from app.routes.auth_api import auth_api_bp, legacy_identity_bp

    # 旧版登录页蓝图注册已停用，见 auth_pages.py 顶部说明。
    # app.register_blueprint(auth_pages_bp)
    # xpl 蓝图仅保留 API（页面路由已注释）。
    app.register_blueprint(xpl_bp, url_prefix='/xpl')
    # 旧版 Jinja 页面蓝图注册已停用，恢复静态模板前端时一并取消注释。
    # app.register_blueprint(yule_bp, url_prefix='/yule')
    # app.register_blueprint(eastmoney_kline_bp)
    # app.register_blueprint(google_sheet_bp, url_prefix='/google-sheet')
    # app.register_blueprint(backtest_training_legacy_bp)
    # app.register_blueprint(backtest_multi_product_legacy_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(legacy_admin_pages_bp, url_prefix='/admin')

    # 拆分后的 API 模块
    app.register_blueprint(task_api_bp, url_prefix='/api')
    app.register_blueprint(config_api_bp, url_prefix='/api')
    # app.register_blueprint(legacy_navigation_bp, url_prefix='/api')
    app.register_blueprint(template_api_bp, url_prefix='/api')
    app.register_blueprint(google_sheet_api_bp, url_prefix='/api')
    app.register_blueprint(database_api_bp, url_prefix='/api')
    app.register_blueprint(stock_api_bp, url_prefix='/api')

    app.register_blueprint(scheduler_api_bp)
    app.register_blueprint(backtest_training_bp)
    app.register_blueprint(backtest_multi_product_bp)
    app.register_blueprint(global_preview_bp)
    app.register_blueprint(meta_api_bp, url_prefix='/api')
    app.register_blueprint(auth_api_bp, url_prefix='/api')
    app.register_blueprint(legacy_identity_bp, url_prefix='/api')
