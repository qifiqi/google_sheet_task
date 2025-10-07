from flask import Blueprint

def register_blueprints(app):
    """注册所有蓝图"""
    from app.routes.api import api_bp
    
    # 只注册API蓝图，前端路由由Vue Router处理
    app.register_blueprint(api_bp, url_prefix='/api')
