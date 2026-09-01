"""SDK CRUD 第二阶段的 P0/P1 回归边界测试。"""

from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    """以 UTF-8 读取源码，避免 Windows 环境中的中文编码差异。"""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_no_forbidden_name_ascending_sort_is_reintroduced():
    """SDK 请求不得恢复历史 name/asc 排序组合。"""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "app").rglob("*.py")
    )
    assert not re.search(
        r"order_field\s*=\s*['\"]name['\"]\s*,\s*order_type\s*=\s*['\"]asc['\"]",
        source,
    )


def test_task_crud_repositories_keep_required_protocol_conversions():
    """任务资源的字符串主键、JSON 与兼容 DTO 不得在重构中丢失。"""
    task_source = _read("app/repositories/task_repository.py")
    result_source = _read("app/repositories/task_result_repository.py")
    return_source = _read("app/repositories/task_result_return_repository.py")

    assert "class RemoteTaskRecord" in task_source
    assert 'group_name = "param_tasks"' in task_source
    assert 'json.dumps(result["config"]' in task_source
    assert 'group_name = "param_task_results"' in result_source
    assert 'group_name = "param_task_results_return"' in return_source


def test_query_only_boundaries_are_explicitly_documented():
    """复杂条件读取必须等待 Query，不能被 SDK 全表分页替代。"""
    paths = [
        "app/services/task/query.py",
        "app/services/task/logs.py",
        "app/services/task/results.py",
        "app/services/task/runtime_view.py",
        "app/services/task/data_cleanup.py",
        "app/routes/auth_api.py",
    ]
    source = "\n".join(_read(path) for path in paths)
    for required_marker in (
        "ParamTasks/Query",
        "ParamTaskLogs/Query",
        "ParamTaskResults/Query",
        "Identity/AccessControl",
    ):
        assert required_marker in source


def test_c31_remote_failure_has_compensation_cleanup():
    """C31 子任务远端创建失败时，必须补偿删除已成功创建的任务。"""
    source = _read("app/services/task/creation.py")
    assert "for created_task_id in reversed(created_task_ids):" in source
    assert "self.delete_task(created_task_id)" in source
