"""统一 API 响应格式工具

新接口统一使用此模块返回响应，老接口逐步迁移。

标准格式:
  成功: {"code": 0, "data": ..., "message": ""}
  失败: {"code": 错误码, "data": null, "message": "错误信息"}
"""
from flask import jsonify


def success(data=None, message=""):
    return jsonify({"code": 0, "data": data, "message": message})


def error(message="操作失败", code=1, http_status=400):
    return jsonify({"code": code, "data": None, "message": message}), http_status


def paginated(items, total, page, per_page, message=""):
    return jsonify({
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        },
        "message": message,
    })
