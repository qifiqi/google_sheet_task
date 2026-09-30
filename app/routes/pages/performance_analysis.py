"""绩效分析页面路由（API 已归位 performance_analysis_api.py，前缀 /performance-analysis）。"""

from flask import Blueprint

from app.routes.pages import register_page_routes
from app.utils.auth import page_login_required


performance_analysis_pages_bp = Blueprint(
    "performance_analysis_pages", __name__, url_prefix="/performance-analysis"
)

register_page_routes(
    performance_analysis_pages_bp,
    [
        ("/", "performance_analysis/index.html"),
        ("/v2", "performance_analysis/v2.html"),
        ("/v3", "performance_analysis/v3.html"),
        ("/weight-combination", "performance_analysis/weight_combination.html"),
    ],
    guard=page_login_required,
)
