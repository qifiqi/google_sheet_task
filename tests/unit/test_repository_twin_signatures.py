"""db/http 孪生仓储签名一致性守卫（数据层切换契约）。

DATA_ACCESS_MODE 的 db/http 切换只发生在数据层（``app/repositories/__init__.py``
启动期绑定单例），业务层零感知的前提是孪生仓储同签名。本地仓储新增/扩展方法
而 http 孪生未同步时（历史漂移：list_by_task_fields / add_entity /
list_paginated 的 success/keyword / 任务列表的 stock_code 筛选等，http 模式
一律 AttributeError），本测试直接失败。

规则：
- 本地仓储类自身定义的公开方法，http 孪生必须存在同名可调用成员；
- 本地签名中带默认值或仅关键字的形参（业务层按名传参的筛选扩展），http 签名
  必须包含同名形参或提供 ``**kwargs``；
- BaseRepository 的 ORM 基方法在 http 基座是异构/兼容实现，默认不比对；但
  凡业务层在用且语义真实的（get_entity：调度器/执行链属性访问），http 孪生
  必须自行覆盖（_REQUIRED_HTTP_OVERRIDES）；
- navigation/auth 固定本地、无 http 孪生（远端无对应表，迁移文档《无法接入
  清单》设计性保留），不入比对对。
"""

import inspect
from inspect import Parameter

from app.repositories.backtest_repository import BacktestRepository
from app.repositories.base import BaseRepository
from app.repositories.google_sheet_repository import GoogleSheetRepository
from app.repositories.google_sheet_token_repository import GoogleSheetTokenRepository
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.repositories.system_config_repository import SystemConfigRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_template_repository import TaskTemplateRepository
from app.repositories.http_backend.backtest_repository import BacktestHttpRepository
from app.repositories.http_backend.google_sheet_repository import GoogleSheetHttpRepository
from app.repositories.http_backend.google_sheet_token_repository import (
    GoogleSheetTokenHttpRepository,
)
from app.repositories.http_backend.scheduled_task_repository import (
    ScheduledTaskHttpRepository,
)
from app.repositories.http_backend.stock_metadata_repository import (
    StockMetadataHttpRepository,
)
from app.repositories.http_backend.system_config_repository import (
    SystemConfigHttpRepository,
)
from app.repositories.http_backend.task_log_repository import TaskLogHttpRepository
from app.repositories.http_backend.task_repository import TaskHttpRepository
from app.repositories.http_backend.task_result_repository import TaskResultHttpRepository
from app.repositories.http_backend.task_template_repository import (
    TaskTemplateHttpRepository,
)

PAIRS = [
    (BacktestRepository, BacktestHttpRepository),
    (GoogleSheetRepository, GoogleSheetHttpRepository),
    (GoogleSheetTokenRepository, GoogleSheetTokenHttpRepository),
    (ScheduledTaskRepository, ScheduledTaskHttpRepository),
    (StockMetadataRepository, StockMetadataHttpRepository),
    (SystemConfigRepository, SystemConfigHttpRepository),
    (TaskLogRepository, TaskLogHttpRepository),
    (TaskRepository, TaskHttpRepository),
    (TaskResultRepository, TaskResultHttpRepository),
    (TaskTemplateRepository, TaskTemplateHttpRepository),
]

# BaseRepository 的 ORM 基方法在 http 基座是异构/兼容实现，默认不比对；但凡
# 业务层真实在用的（get_entity：执行链/调度器/占用链属性访问，按 grep 消费面
# 登记），http 孪生必须自行覆盖。
_REQUIRED_HTTP_OVERRIDES = {
    TaskRepository: {"get_entity"},
    TaskResultRepository: {"get_entity"},
    GoogleSheetRepository: {"get_entity"},
    GoogleSheetTokenRepository: {"get_entity"},
    ScheduledTaskRepository: {"get_entity"},
}


def _http_accepts(http_member, local_params):
    try:
        http_params = inspect.signature(http_member).parameters
    except (TypeError, ValueError):
        return False
    has_var_kw = any(p.kind is Parameter.VAR_KEYWORD for p in http_params.values())
    for p in local_params:
        if p.kind in (Parameter.VAR_KEYWORD, Parameter.VAR_POSITIONAL):
            continue
        needs_name = p.default is not Parameter.empty or p.kind is Parameter.KEYWORD_ONLY
        if needs_name and not has_var_kw and p.name not in http_params:
            return False
    return True


def test_http_twin_covers_local_repository_surface():
    drift = []
    for local_cls, http_cls in PAIRS:
        names = {name for name, member in vars(local_cls).items()
                 if not name.startswith("_") and callable(member)
                 and not isinstance(member, type)}
        names |= _REQUIRED_HTTP_OVERRIDES.get(local_cls, set())
        for name in sorted(names):
            local_member = getattr(local_cls, name)
            http_member = getattr(http_cls, name, None)
            if not callable(http_member):
                drift.append(f"{http_cls.__name__}.{name} 缺失（本地 {local_cls.__name__}.{name}）")
                continue
            local_params = [
                p for p in inspect.signature(local_member).parameters.values()
                if p.name not in ("self", "cls") and p.kind is not Parameter.VAR_POSITIONAL
            ]
            if not _http_accepts(http_member, local_params):
                http_params = inspect.signature(http_member).parameters
                missing = [
                    p.name for p in local_params
                    if (p.default is not Parameter.empty or p.kind is Parameter.KEYWORD_ONLY)
                    and p.name not in http_params
                    and p.kind is not Parameter.VAR_KEYWORD
                ]
                drift.append(
                    f"{http_cls.__name__}.{name} 未接受本地按名传参的参数 {missing} "
                    f"（本地签名 {inspect.signature(local_member)}，"
                    f"http 签名 {inspect.signature(http_member)}）"
                )
                continue
            # 实体形态方法（get_entity）必须返回 RemoteRecord 包装而非裸 dict：
            # 占用/调度链按属性访问，裸 dict 会 AttributeError（2026-10-17 E2E 实测）。
            if name == "get_entity":
                source = inspect.getsource(http_member)
                assert "RemoteRecord" in source, (
                    f"{http_cls.__name__}.get_entity 未返回 RemoteRecord 包装"
                    "（属性访问链会 AttributeError）"
                )
    assert not drift, "http 孪生仓储与本地仓储签名漂移（业务层会被波及）：\n" + "\n".join(drift)
