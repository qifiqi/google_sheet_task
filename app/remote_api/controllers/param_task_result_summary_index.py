"""``/api/ParamTaskResultSummaryIndex`` —— 任务结果汇总索引表接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamTaskResultSummaryIndexApi(ControllerApi):
    """任务结果汇总索引表接口（远程控制器 ``/api/ParamTaskResultSummaryIndex``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除汇总索引行

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamTaskResultSummaryIndex/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultSummaryIndex/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询汇总索引（支持 task_id/task_type/stock_keyword 等过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamTaskResultSummaryIndex/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "...", "page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/ParamTaskResultSummaryIndex/GetDataByPageList', payload)

    def get_data_summary(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        查询汇总统计数据

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamTaskResultSummaryIndex/GetDataSummary' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{}'
        """
        return self._make_request('POST', '/api/ParamTaskResultSummaryIndex/GetDataSummary', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询汇总索引详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamTaskResultSummaryIndex/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultSummaryIndex/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新汇总索引行

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamTaskResultSummaryIndex/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "...", "task_result_id": 1, "is_best": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResultSummaryIndex/ModifyOrAdd', payload)
