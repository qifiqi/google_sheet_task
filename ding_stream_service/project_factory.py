"""Create standalone projects from DingTalk message keywords."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


class ProjectAlreadyExistsError(Exception):
    """Raised when a target path exists but is not owned by this factory."""


@dataclass(frozen=True)
class CreatedProject:
    keyword: str
    name: str
    path: Path
    created: bool


def normalize_project_name(keyword: str) -> str:
    """Convert user input into a safe single-level Windows directory name."""
    name = INVALID_PATH_CHARS.sub("_", keyword.strip())
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip(" ._")

    if not name:
        raise ValueError("项目关键字不能为空")
    if name.lower() in RESERVED_WINDOWS_NAMES:
        raise ValueError(f"项目名不能使用 Windows 保留名称: {name}")

    return name[:80]


def create_independent_project(root_dir: Path, keyword: str) -> CreatedProject:
    """Create a standalone project directory in the repository root."""
    name = normalize_project_name(keyword)
    project_dir = root_dir / name
    marker_file = project_dir / ".ding_stream_project"

    if project_dir.exists() and not marker_file.exists():
        raise ProjectAlreadyExistsError(f"目录已存在且不是微服务创建的项目: {project_dir}")

    created = not project_dir.exists()
    project_dir.mkdir(parents=False, exist_ok=True)

    _write_once(marker_file, "created_by=ding_stream_service\n")
    _write_once(project_dir / "README.md", _render_readme(keyword, name))
    _write_once(project_dir / "main.py", _render_main_py())
    _write_once(project_dir / "agent_entry.py", _render_agent_entry_py())
    _write_once(project_dir / "requirements.txt", "# Add project dependencies here.\n")
    _write_once(
        project_dir / "project.json",
        json.dumps(
            {
                "keyword": keyword,
                "name": name,
                "entry": "main.py",
                "agent_entry": "agent_entry.py",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    return CreatedProject(keyword=keyword, name=name, path=project_dir, created=created)


def _write_once(path: Path, content: str) -> None:
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def _render_readme(keyword: str, name: str) -> str:
    return f"""# {name}

由钉钉 Stream 微服务根据关键字 `{keyword}` 创建。

## 启动

```powershell
python main.py
```

## AI agent 接入口

`agent_entry.py` 中的 `handle_agent_input()` 是预留入口，可在这里接入实际 agent。
"""


def _render_main_py() -> str:
    return '''#!/usr/bin/env python3
"""Standalone project entry."""

from agent_entry import handle_agent_input


def main() -> None:
    print("独立项目已启动，输入 exit 退出。")
    while True:
        user_input = input("> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        print(handle_agent_input(user_input))


if __name__ == "__main__":
    main()
'''


def _render_agent_entry_py() -> str:
    return '''"""AI agent integration entry."""


def handle_agent_input(user_input: str) -> str:
    """Handle user input before wiring a real AI agent."""
    return f"AI agent 接入口收到: {user_input}"
'''
