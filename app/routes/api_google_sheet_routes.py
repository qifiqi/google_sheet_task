import time

from flask import jsonify, request

from app.services.google_sheet_service import GoogleSheetService
from app.utils.logger import get_logger

logger = get_logger(__name__)

_worksheets_cache = {}
_WORKSHEETS_CACHE_TTL = 10 * 24 * 60 * 60


def _get_worksheets_with_cache(spreadsheet_id: str, token_file: str, proxy_url: str | None):
    """带缓存获取 worksheet 列表。"""
    try:
        cache_key = (spreadsheet_id, token_file, proxy_url or "")
        now = time.time()
        cached = _worksheets_cache.get(cache_key)
        if cached:
            timestamp, cached_data = cached
            if now - timestamp < _WORKSHEETS_CACHE_TTL:
                logger.debug(f"命中工作表列表缓存: spreadsheet_id={spreadsheet_id}")
                return (
                    {
                        "status": "success",
                        "title": cached_data.get("title", ""),
                        "worksheets": cached_data.get("worksheets", []),
                        "cached": True,
                    },
                    200,
                )

        data = GoogleSheetService.get_worksheets(spreadsheet_id, token_file, proxy_url)
        try:
            _worksheets_cache[cache_key] = (now, data)
        except Exception as exc:
            logger.warning(f"更新工作表缓存失败: {exc}")

        return (
            {
                "status": "success",
                "title": data.get("title", ""),
                "worksheets": data.get("worksheets", []),
            },
            200,
        )
    except Exception as exc:
        logger.error(f"获取工作表列表失败: {str(exc)}")
        return {"status": "error", "message": str(exc)}, 500


def register_google_sheet_routes(api_bp):
    """注册 Google Sheet 辅助路由。"""

    @api_bp.route("/google-sheet/worksheets", methods=["POST"])
    def get_worksheets():
        """获取 Google Sheet 中的所有工作表名称。"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "请求数据为空"}), 400

            spreadsheet_id = data.get("spreadsheet_id")
            token_file = data.get("token_file", "data/token.json")
            proxy_url = data.get("proxy_url")
            if not spreadsheet_id:
                return jsonify({"status": "error", "message": "缺少 spreadsheet_id 参数"}), 400

            result, status_code = _get_worksheets_with_cache(spreadsheet_id, token_file, proxy_url)
            return jsonify(result), status_code
        except Exception as exc:
            logger.error(f"获取工作表列表失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500
