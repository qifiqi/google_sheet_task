"""任务类型/状态词汇单源守卫（常量收敛 P3，docs/design/constants-audit-2026-09/）。

枚举是唯一来源；本测试防止派生词汇与枚举漂移。
"""

from app.models import TaskStatus, TaskType
from app.seeds.system_config_seeds import build_default_configs
from app.utils.task_types import (
    TYPE_GOOGLE_SHEET,
    TYPE_GOOGLE_SHEET_C1_1,
    TYPE_GOOGLE_SHEET_C4,
    TYPE_GOOGLE_SHEET_C5,
    TYPE_GOOGLE_SHEET_C7,
    normalize_task_type,
)


def test_normalize_maps_every_enum_member_to_lowercase():
    for member in TaskType:
        assert normalize_task_type(member.value) == member.value.lower()
        # 大小写变体输入也归一到同一规范键
        assert normalize_task_type(member.value.upper()) == member.value.lower()


def test_type_constants_match_enum_derivation():
    assert TYPE_GOOGLE_SHEET == "google_sheet"
    assert TYPE_GOOGLE_SHEET_C4 == "google_sheet_c4"
    assert TYPE_GOOGLE_SHEET_C5 == "google_sheet_c5"
    assert TYPE_GOOGLE_SHEET_C7 == "google_sheet_c7"
    assert TYPE_GOOGLE_SHEET_C1_1 == "google_sheet_c1_1"


def test_supported_task_types_are_enum_values():
    from app.services.model_summary import extractor

    enum_values = {member.value for member in TaskType}
    assert set(extractor.SUPPORTED_TASK_TYPES) <= enum_values
    assert set(extractor.TASK_TYPE_LABELS) <= enum_values
    assert set(extractor.FINISHED_TASK_STATUSES) == {
        TaskStatus.COMPLETED.value,
        TaskStatus.CANCELLED.value,
        TaskStatus.ERROR.value,
    }
    assert set(extractor.ACTIVE_REBUILD_TASK_STATUSES) == {
        TaskStatus.PENDING.value,
        TaskStatus.RUNNING.value,
    }


def test_task_config_model_registry_keys_are_enum_values():
    from app.schemas.task_configs import TASK_CONFIG_MODELS

    enum_values = {member.value for member in TaskType}
    registered = set(TASK_CONFIG_MODELS)
    # google_sheet_C3 是 C3 同义别名键（历史请求词汇），其余键必须来自枚举
    assert registered - enum_values == {"google_sheet_C3"}
    assert registered & enum_values >= {
        TaskType.GOOGLE_SHEET.value,
        TaskType.BACKTEST_TRAINING.value,
        TaskType.BACKTEST_MULTI_PRODUCT.value,
    }


def test_concurrency_seeds_no_legacy_global_admission_key():
    seeds = build_default_configs()
    # P2 双轨废弃：max_concurrent_tasks 不再播种，也不再有代码消费方
    assert "max_concurrent_tasks" not in seeds
    assert "task_max_workers" in seeds
