"""``/api/StockParamResult`` —— 参数校验结果回推接口。

C 系任务的执行结果经本控制器写回主站 StockParamResult 表。
原 ``app/utils/db_stock_api.py`` 的独立 StockAPIClient 是本控制器
的唯一历史来源（2026-10 收口进 remote_api 统一出口后删除）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class StockParamResultApi(ControllerApi):
    """参数校验结果回推接口（远程控制器 ``/api/StockParamResult``）。"""

    def add_or_modify(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/修改参数校验结果（按 task_id + stock_code 等键定位同条记录）

            curl -X 'POST' \
              'https://stockapi.jaspil.cn/api/StockParamResult/AddOrModify' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "...", "stock_code": "600000", "multiplier": 0}'
        """
        return self._make_request('POST', '/api/StockParamResult/AddOrModify', payload)
