"""``/api/ParamBacktestSheetRunLocks`` —— 回测 Sheet 运行锁表接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamBacktestSheetRunLocksApi(ControllerApi):
    """回测 Sheet 运行锁表接口（远程控制器 ``/api/ParamBacktestSheetRunLocks``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除运行锁

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestSheetRunLocks/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamBacktestSheetRunLocks/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询运行锁（支持 spreadsheet_id 过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestSheetRunLocks/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"spreadsheet_id": "...", "page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/ParamBacktestSheetRunLocks/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询运行锁详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestSheetRunLocks/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamBacktestSheetRunLocks/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新运行锁（spreadsheet_id 唯一约束兜底并发）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestSheetRunLocks/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"spreadsheet_id": "...", "task_id": "...", "task_type": "..."}'
        """
        return self._make_request('POST', '/api/ParamBacktestSheetRunLocks/ModifyOrAdd', payload)
