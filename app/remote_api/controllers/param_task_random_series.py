"""``/api/ParamTaskRandomSeries`` —— 随机价格序列表接口（E11 规格）。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamTaskRandomSeriesApi(ControllerApi):
    """随机价格序列接口（远程控制器 ``/api/ParamTaskRandomSeries``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 删除单条序列（不删除源快照/任务/关联行）

        契约同 ``ParamTaskResults/Delete``（2026-10-29 实测）：行不存在报
        ret_code=400。

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskRandomSeries/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询序列摘要（不含 values_json；支持 task_id / source_id /
        stock_code / kline_key 过滤）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "t1", "source_id": 1, "page_index": 1, "page_size": 50}'

        返回 ``(ret_obj, ret_count)``。
        """
        return self._make_request_with_count('POST', '/api/ParamTaskRandomSeries/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 获取完整序列（含 values_json 原始字符串）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskRandomSeries/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增或整条修改序列，返回整行（含 id，修改保留创建时间）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"source_id": 1, "task_id": "t1", "stock_code": "600000",
                   "kline_key": "2026-2025", "dataset_key": "600000|2026-2025|g1",
                   "random_group": 1, "price_mode": "random_price",
                   "random_price_range": "high_low", "seed": "<seed>",
                   "row_count": 260, "values_json": "[...]"}'
        """
        return self._make_request('POST', '/api/ParamTaskRandomSeries/ModifyOrAdd', payload)
