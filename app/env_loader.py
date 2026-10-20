"""环境文件加载；必须在仓储绑定与 routes/services 导入之前执行。"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import dotenv_values
except ImportError:
    def dotenv_values(*_args, **_kwargs):
        return {}


def load_app_environment(project_root=None):
    """加载环境文件，优先级为：真实环境变量 > 环境专属文件 > 基础 .env。

    先保存启动进程已有的环境变量，避免环境文件覆盖 VSCode launch.json、
    Docker environment 或系统环境中的显式配置。
    """
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parent.parent
    process_env = dict(os.environ)

    base_env = root / '.env'
    base_values = dotenv_values(base_env) if base_env.exists() else {}

    # APP_ENV 需要先确定，才能选择 .env.development 等环境专属文件。
    app_env = (
        process_env.get('APP_ENV')
        or base_values.get('APP_ENV')
        or 'development'
    ).strip().lower() or 'development'
    scoped_env = root / f'.env.{app_env}'
    scoped_values = dotenv_values(scoped_env) if scoped_env.exists() else {}

    # 先写环境专属文件，再写基础文件；后者只补充尚未设置的键。
    # process_env 中的键永远不改，因此真实环境变量优先级最高。
    for values in (scoped_values, base_values):
        for key, value in values.items():
            if value is not None and key not in process_env and key not in os.environ:
                os.environ[key] = value

    os.environ.setdefault('APP_ENV', app_env)
    return app_env
