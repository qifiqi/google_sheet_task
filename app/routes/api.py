from flask import Blueprint

from app.routes.api_config_routes import register_config_routes
from app.routes.api_database_routes import register_database_routes
from app.routes.api_google_sheet_routes import register_google_sheet_routes
from app.routes.api_log_routes import register_log_routes
from app.routes.api_result_routes import register_result_routes
from app.routes.api_task_routes import register_task_routes
from app.routes.api_template_routes import register_template_routes

api_bp = Blueprint("api", __name__)

# 按职责拆分路由模块，避免 api.py 继续膨胀成单文件巨型入口。
register_task_routes(api_bp)
register_config_routes(api_bp)
register_google_sheet_routes(api_bp)
register_template_routes(api_bp)
register_result_routes(api_bp)
register_log_routes(api_bp)
register_database_routes(api_bp)
