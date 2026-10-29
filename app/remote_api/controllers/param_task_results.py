"""``/api/ParamTaskResults`` —— 任务结果表接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamTaskResultsApi(ControllerApi):
    """任务结果表接口（远程控制器 ``/api/ParamTaskResults``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按 task_id 整任务删除结果行

        远端实际契约与 Swagger 文档不符（2026-10-28 线上实测）：Swagger 只标注
        ``ParamTaskIdRequestDto {task_id}``，实测为**删除该 task_id 的全部行**——
        载荷里的 id 字段被忽略；task_id 与行内存储形式精确匹配（本仓写入
        即应用原生形式，不做归一化）；0 行匹配报 ret_code=400"操作失败"。

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResults/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "<任务id（与行内存储一致）>"}'
        """
        return self._make_request('POST', '/api/ParamTaskResults/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询任务结果（仅支持 task_ids[] 数组/success 过滤）

        注意：单数字段 ``task_id`` 会被远端静默忽略（返回不过滤的全表），
        任务过滤必须用 ``task_ids`` 数组（2026-10-28 线上实测）。

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResults/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_ids": ["..."], "page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/ParamTaskResults/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询任务结果详情

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResults/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamTaskResults/GetInfoById', payload)

    def modify_or_add(
        self,
        payload: Mapping[str, Any] | None = None,
        *,
        with_count: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """
        新增/更新任务结果（插入时新 id 经 ``ret_count`` 回带）

            curl -X 'POST' \
              'http://stockapi.jaspil.cn/api/ParamTaskResults/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"task_id": "...", "step_index": 0, "success": 1}'
        """
        if with_count:
            return self._make_request_with_count(
                'POST', '/api/ParamTaskResults/ModifyOrAdd', payload, timeout=timeout
            )
        return self._make_request(
            'POST', '/api/ParamTaskResults/ModifyOrAdd', payload, timeout=timeout
        )
