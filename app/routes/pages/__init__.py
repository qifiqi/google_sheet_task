"""静态页面路由包（docs/design/routes-restructure-2026-09/）。

templates/ 目录就地静态化后，页面路由统一收在本包：每个页面模块一张蓝图，
全部经本文件助手返回纯静态 HTML；send_from_directory 自带路径穿越防护
（safe join）。JSON API 一律不进本包，留在 app/routes/ 平级 *_api.py。
"""
from pathlib import Path

from flask import send_from_directory

PAGES_DIR = Path(__file__).resolve().parents[3] / "templates"


def send_page(relpath: str):
    """返回静态页面文件；relpath 使用 '/' 分隔，如 'admin/tasks.html'"""
    return send_from_directory(PAGES_DIR, relpath)


def register_page_routes(bp, pages, guard=None):
    """按表批量注册同构页面路由（ponytail 审计 D1：34 个 send_page 视图收敛）。

    pages 每项为 ``(rule, template)``；同一组页面需挂在多个蓝图（旧书签
    兼容 legacy_bp）时，对各蓝图分别调用本 helper 即可。guard 为登录守卫
    装饰器（页面统一 page_login_required），None 表示不守卫。
    """
    if guard is None:
        def guard(fn):
            return fn

    for rule, template in pages:
        endpoint = rule.strip("/").replace("/", "_") or "index"

        # _template 走定义期默认参数，避免循环内闭包晚绑定；URL 转换器参数经 kwargs 透传
        def _view(*_args, _template=template, **_kwargs):
            return send_page(_template)

        _view.__name__ = f"{bp.name}_{endpoint}_page"
        bp.add_url_rule(rule, endpoint=endpoint, view_func=guard(_view))
