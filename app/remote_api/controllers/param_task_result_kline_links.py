"""``/api/ParamTaskResultKlineLinks`` —— 随机K线结果关联表接口（E12 规格）。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamTaskResultKlineLinksApi(ControllerApi):
    """随机K线结果关联接口（远程控制器 ``/api/ParamTaskResultKlineLinks``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按关联记录 ID 删除（不删除任务结果/序列）

        契约同 ``ParamTaskResults/Delete``（2026-10-29 实测）：行不存在报
        ret_code=400。

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultKlineLinks/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        按任务结果 / 任务 / 随机序列筛选关联并分页返回
        （result_id / task_id / series_id 过滤；ret_count 即计数）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "t1", "series_id": 1, "page_index": 1, "page_size": 100}'

        返回 ``(ret_obj, ret_count)``。
        """
        return self._make_request_with_count('POST', '/api/ParamTaskResultKlineLinks/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按关联记录 ID 查询详情

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultKlineLinks/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 修改或按 result_id + series_id 幂等创建关联，返回整行

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"result_id": 123, "task_id": "t1", "series_id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultKlineLinks/ModifyOrAdd', payload)
