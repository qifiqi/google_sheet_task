"""冒烟测试专用启动入口：仅 create_app + 开发服务器，跳过 bootstrap_app。

ponytail 审计 P11/P15/P11/P12 页面冒烟用；不播种导航、不启动调度器。
临时文件，冒烟结束后删除。
"""
import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001)
