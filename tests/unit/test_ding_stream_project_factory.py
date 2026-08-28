from pathlib import Path

import pytest

from ding_stream_service.project_factory import (
    ProjectAlreadyExistsError,
    create_independent_project,
    normalize_project_name,
)


def test_normalize_project_name_keeps_chinese_keyword():
    assert normalize_project_name(" 股票 复盘 助手 ") == "股票_复盘_助手"


def test_create_independent_project_creates_entry_and_agent_files(tmp_path: Path):
    project = create_independent_project(tmp_path, "股票 复盘 助手")

    assert project.created is True
    assert project.name == "股票_复盘_助手"
    assert (project.path / "main.py").exists()
    assert (project.path / "agent_entry.py").exists()
    assert (project.path / ".ding_stream_project").exists()


def test_create_independent_project_rejects_existing_foreign_directory(tmp_path: Path):
    existing = tmp_path / "已有目录"
    existing.mkdir()

    with pytest.raises(ProjectAlreadyExistsError):
        create_independent_project(tmp_path, "已有目录")
