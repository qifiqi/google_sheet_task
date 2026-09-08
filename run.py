#!/usr/bin/env python3
"""Flask 应用运行入口。

数据库直连迁移状态（stock_sdk / HTTP 数据访问改造）:

- ``bootstrap_app(app)`` 已注释停用：本地建表 / schema 修补 / RBAC 初始化
  / token 与 Sheet 占用复位 / 调度器与看门狗线程均不随进程启动；
  任务业务数据读写已切换到 stock_sdk HTTP 接口。
- 如需恢复完整启动流程（例如切回本地身份兜底调试），取消下方
  ``bootstrap_app(app)`` 注释即可；各子步骤的停用状态详见
  ``app/startup.py`` 模块顶部说明。
"""
import os

from app import create_app
from app.startup import bootstrap_app, register_cli, register_shell_context
from app.utils.logger import get_logger


app = create_app()
# 仅注册 Flask shell/CLI 扩展；此处不会创建表、写入初始数据或启动后台线程。
register_shell_context(app)
register_cli(app)


if __name__ == '__main__':
    logger = get_logger('app')
    try:
        # 直接以 Python 启动时在这里完成运行态恢复和后台组件初始化。
        # Gunicorn 路径由 dockers/gunicorn.conf.py::post_worker_init 调用同一函数。
        # bootstrap_app(app)
        debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')
        app.run(debug=debug_mode, host='0.0.0.0', port=os.getenv('PORT', 5000))
    except Exception as exc:
        logger.error(f'启动失败: {exc}', exc_info=True)



