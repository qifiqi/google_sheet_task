"""静态页面路由包（docs/design/routes-restructure-2026-09/）。

templates/ 目录就地静态化后，页面路由统一收在本包：每个页面模块一张蓝图，
全部经本文件助手返回纯静态 HTML；send_from_directory 自带路径穿越防护
（safe join）。JSON API 一律不进本包，留在 app/routes/ 平级 *_api.py。
"""
from pathlib import Path

from flask import redirect, url_for,send_from_directory

PAGES_DIR = Path(__file__).resolve().parents[3] / "templates"


def send_page(relpath: str):
    """返回静态页面文件；relpath 使用 '/' 分隔，如 'admin/tasks.html'"""
    return send_from_directory(PAGES_DIR, relpath)


def register_page_routes(bp, pages, guard=None):
    """按表批量注册同构页面路由（ponytail 审计 D1：34 个 send_page 视图收敛）。

    pages 每项为 ``(rule, template)`` 或 ``(rule, template, redirect_to)``；
    redirect_to 非空时该路由改为重定向（template 传 None 即可）。
    redirect_to 以 "." 开头走 url_for（蓝图相对 endpoint），否则当字面 URL 用。
    """
    if guard is None:
        def guard(fn):
            return fn

    for page in pages:
        # 兼容 2 元组 / 3 元组
        rule, template = page[0], page[1]
        redirect_to = page[2] if len(page) > 2 else None

        endpoint = rule.strip("/").replace("/", "_") or "index"

        if redirect_to is not None:
            def _redirect(_redirect_to=redirect_to, **_kwargs):
                if _redirect_to.startswith("."):
                    return redirect(url_for(f"{bp.name}{_redirect_to}"), code=302)
                return redirect(_redirect_to, code=302)

            _redirect.__name__ = f"{bp.name}_{endpoint}_redirect"
            bp.add_url_rule(rule, endpoint=endpoint, view_func=guard(_redirect))
            continue

        # 原有渲染分支
        def _view(*_args, _template=template, **_kwargs):
            return send_page(_template)

        _view.__name__ = f"{bp.name}_{endpoint}_page"
        bp.add_url_rule(rule, endpoint=endpoint, view_func=guard(_view))
