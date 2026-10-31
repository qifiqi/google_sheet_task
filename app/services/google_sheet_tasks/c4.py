from app.services.google_sheet_tasks.c5 import C5Service


class C4Service(C5Service):
    """Google Sheet服务 - C4。

    C4 与 C5 模板布局逐项同值（``c4_*``/``c5_*`` SystemConfig 种子、
    ``C4_C5_METRIC_CELLS`` 共享常量、``SUMMARY_METRIC_CELL_MAP`` 别名），
    功能口径完全一致；本类仅保留任务身份差异（模型版本标记/去重标签），
    批量执行骨架、取价（price_mode）、随机价、自定义K线、断点/去重/网络
    重试全部继承 C5——C5 的改动自动惠及 C4。

    历史遗留的骨架化前实现（自带 get_bdl 逐表轮询、静态参数展开、固定按
    市场取价 A股开/美股收）已删除：取价统一由 ``config.price_mode`` 决定，
    与创建页（复用 C5 表单）下发的选项对齐。
    """

    _model_version = "c4"

    # 去重日志标签（公共去重器见基类）
    _dedupe_label = "C4"
