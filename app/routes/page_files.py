"""静态页面文件助手（docs/design/frontend-refactor/05 §2.1）。

templates/ 目录就地静态化后，页面路由经此返回纯静态 HTML；
send_from_directory 自带路径穿越防护（safe join）。
"""
from pathlib import Path

from flask import send_from_directory

PAGES_DIR = Path(__file__).resolve().parents[2] / "templates"


def send_page(relpath: str):
    """返回静态页面文件；relpath 使用 '/' 分隔，如 'admin/tasks.html'"""
    return send_from_directory(PAGES_DIR, relpath)
