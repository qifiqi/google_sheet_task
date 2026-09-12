#!/usr/bin/env python3
"""Direct script entry for the DingTalk stream microservice."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from ding_stream_service.main import main
except ImportError as exc:
    print(f"[ERROR] 缺少依赖: {exc}", file=sys.stderr)
    print(
        "请改用项目虚拟环境启动：run_ding.bat 或 .venv\\Scripts\\python.exe run_ding.py\n"
        "或在当前 Python 中执行：pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
