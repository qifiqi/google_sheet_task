"""任务类型词汇单源（2026-10 常量收敛 P3，自裸字面量改为枚举派生）。

两套词汇、一个来源（app.models.TaskType 枚举值 = DB 存量取值，含历史大写后缀疣）：
- DB/API 词汇：TaskType 成员值（``google_sheet_C4``），Task.task_type 落库取值，
  SUPPORTED_TASK_TYPES、schemas 注册表等与 DB 对账的场景使用；
- 内部规范词汇：``TYPE_*``（枚举值统一小写，``google_sheet_c4``），registry 键、
  normalize_task_type 输出、运行期比较统一使用。

归一口只有一个：normalize_task_type()。新增任务类型时改 TaskType 枚举即可，
本模块词汇自动跟随；别名表与 C 系集合中无法从枚举派生的历史输入别名单独登记。
"""

from app.models import TaskType


# ---- 内部规范词汇（枚举值小写派生，禁止再写字面量）----

TYPE_GOOGLE_SHEET = TaskType.GOOGLE_SHEET.value.lower()
TYPE_GOOGLE_SHEET_C4 = TaskType.GOOGLE_SHEET_C4.value.lower()
TYPE_GOOGLE_SHEET_C5 = TaskType.GOOGLE_SHEET_C5.value.lower()
TYPE_GOOGLE_SHEET_C7 = TaskType.GOOGLE_SHEET_C7.value.lower()
TYPE_GOOGLE_SHEET_C1_1 = TaskType.GOOGLE_SHEET_C1_1.value.lower()
TYPE_BACKTEST_TRAINING = TaskType.BACKTEST_TRAINING.value.lower()
TYPE_BACKTEST_MULTI_PRODUCT = TaskType.BACKTEST_MULTI_PRODUCT.value.lower()
TYPE_MODEL_SUMMARY_REBUILD = TaskType.MODEL_SUMMARY_REBUILD.value.lower()


# 用户输入别名 → 规范键（历史口语/旧值，不在枚举内，无法派生）
_ALIASES = {
    "google_sheet_c3": TYPE_GOOGLE_SHEET,   # C3 与 google_sheet 同义
    "google_sheet_c31": TYPE_GOOGLE_SHEET,  # C31 批量入口，落库拆为 C3 子任务
    "backtest": TYPE_BACKTEST_TRAINING,
    "multi_product_backtest": TYPE_BACKTEST_MULTI_PRODUCT,
    "backtest_multi": TYPE_BACKTEST_MULTI_PRODUCT,
}

# 枚举成员小写集合（规范键全集，枚举新增成员自动进入）
_CANONICAL_LOWER = frozenset(member.value.lower() for member in TaskType)


def is_c_series_task_type(task_type: str | None) -> bool:
    return str(task_type or "").strip().lower() in C_SERIES_TASK_TYPES


def normalize_task_type(task_type: str | None) -> str:
    """唯一归一口：别名归并 + 小写透传（历史契约：输出恒为小写规范键）。"""
    raw = str(task_type or "").strip().lower()
    return _ALIASES.get(raw, raw)


# ---- 派生集合 ----

# C 系判定集合：枚举 C 系成员小写派生 + 历史输入别名（c3/c31 归一前形态）。
C_SERIES_TASK_TYPES = frozenset(
    {
        TYPE_GOOGLE_SHEET,
        "google_sheet_c3",
        "google_sheet_c31",
        TYPE_GOOGLE_SHEET_C4,
        TYPE_GOOGLE_SHEET_C5,
        TYPE_GOOGLE_SHEET_C7,
        TYPE_GOOGLE_SHEET_C1_1,
    }
)
