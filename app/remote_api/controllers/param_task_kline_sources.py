"""``/api/ParamTaskKlineSources`` —— 随机K线源快照表接口（E10 规格）。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamTaskKlineSourcesApi(ControllerApi):
    """随机K线源快照接口（远程控制器 ``/api/ParamTaskKlineSources``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 删除单条快照（不删除关联任务/序列/关联行）

        契约同 ``ParamTaskResults/Delete``（2026-10-29 实测）：行不存在报
        ret_code=400。

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskKlineSources/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询快照摘要（不返回六个 *_json 大字段；支持 task_id / stock_code /
        kline_key / data_source / adjust_type 过滤）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "t1", "stock_code": "600000", "kline_key": "2026-2025",
                   "data_source": "dfcf", "adjust_type": "forward",
                   "page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``。
        """
        return self._make_request_with_count('POST', '/api/ParamTaskKlineSources/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 获取完整快照（含六个 JSON 数组字符串）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskKlineSources/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 ID 修改或按五字段唯一键（task_id+stock_code+kline_key+data_source+
        adjust_type）新增/更新，返回整行（含 id，更新保留创建时间）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "t1", "stock_code": "600000", "kline_key": "2026-2025",
                   "data_source": "dfcf", "adjust_type": "forward", "row_count": 260,
                   "dates_json": "[...]", "open_json": "[...]", "high_json": "[...]",
                   "low_json": "[...]", "close_json": "[...]", "vwap_json": "[...]"}'
        """
        return self._make_request('POST', '/api/ParamTaskKlineSources/ModifyOrAdd', payload)
