"""统一 API 响应信封（全库唯一响应出口，见 docs/design/data-layer-refactor/04 §2）。

标准格式:
  成功: {"status": "success", "code": 0, "message": "", "data": ...}
  失败: {"status": "error", "code": <http_status 或业务码>, "message": "...", "data": null}

规则:
- routes 层只允许经由本模块产出 JSON 响应，禁止手写 {"status": "error", ...} 字典；
- 所有业务数据一律放 data（键名不变），无顶层平铺机制、无迁移双轨；
- code 与 http_status 分离：error 未显式传 code 时自动等于 http_status，业务码可显式覆盖。
"""
from flask import jsonify


def success(data=None, message="", http_status=200):
    return jsonify({
        "status": "success",
        "code": 0,
        "message": message,
        "data": data,
    }), http_status


def error(message="操作失败", code=None, http_status=400, data=None):
    return jsonify({
        "status": "error",
        "code": http_status if code is None else code,
        "message": message,
        "data": data,
    }), http_status


def paginated(items, total, page, per_page, message=""):
    per_page = per_page or 20
    return success(
        data={
            "items": items,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
            "per_page": per_page,
        },
        message=message,
    )
