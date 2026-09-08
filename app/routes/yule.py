"""娱乐工具旧版 Jinja 页面路由（整文件停用）。

单 Token 子服务模式（2026-09 起）:

- 静态模板前端已整体下线：浏览器导航无法携带 ``Token`` 请求头，
  旧页面在新鉴权下不可达；恢复时取消下方注释并重新注册蓝图
  （见 ``app/routes/__init__.py``）。
"""

# from flask import Blueprint, render_template, request, jsonify, url_for, redirect, flash, current_app
# import json
# from app.services.config_manager import get_config_manager
# from app.utils.logger import get_logger
#
# logger = get_logger(__name__)
#
# yule_bp = Blueprint('yule', __name__)
#
# @yule_bp.route('/')
# def index():
#     """Excel数据分析工具首页"""
#     return render_template('yule/index.html')
#
# @yule_bp.route('/sjxz')
# def sjxz():
#     """数据选择"""
#     return render_template('yule/sjxz.html')
