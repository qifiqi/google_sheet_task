# model_access_service.py
"""
模型权限服务：
读取 JWT 中由主 Web 签发的 model_codes，作为当前用户可访问功能的权限依据。
用于限制页面/API 访问；sys_model 仅提供路由定义，不能直接作为用户权限来源。
主 Web 尚未下发 model_codes 时，应保持细粒度权限校验关闭。
"""

from __future__ import annotations

from functools import wraps

from flask import g, jsonify

from app.services.menu_service import MenuService


def set_current_model_codes(model_codes) -> None:
    """将 JWT 携带的模型权限代码写入当前请求上下文。"""
    g.current_model_codes = {str(code) for code in model_codes if code}


def require_model_access(model_code: str):
    """要求当前请求携带来自可信用户权限域的模型代码。"""
    def decorator(view):
        """包装页面视图，在执行前校验当前模型访问权限。"""
        @wraps(view)
        def wrapped(*args, **kwargs):
            """依据当前请求路径与模型代码决定是否允许访问。"""
            codes = getattr(g, "current_model_codes", None)
            if codes is None:
                return jsonify({
                    "code": 503,
                    "data": None,
                    "message": "主 Web 尚未提供当前用户的模型权限",
                }), 503
            if model_code not in codes:
                return jsonify({"code": 403, "data": None, "message": "无该模型访问权限"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def is_path_allowed(menu: list[dict], model_codes: set[str], path: str) -> bool:
    """依据可信 JWT 模型代码集合判断本地页面路径是否允许访问。"""
    def walk(items):
        """递归遍历菜单树，查找与当前路径匹配的节点。"""
        for item in items:
            link = item.get("model_link") or ""
            if item.get("available") and item.get("model_code") in model_codes:
                if link == path or ("?" not in link and link == path.split("?", 1)[0]):
                    return True
            if walk(item.get("children") or []):
                return True
        return False

    return walk(menu)
