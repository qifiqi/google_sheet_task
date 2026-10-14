"""``/api/StockDic`` —— 字典与辅助数据接口。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class StockDicApi(ControllerApi):
    """字典与辅助数据接口（远程控制器 ``/api/StockDic``）。"""

    def get_proxy_list_by_one(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        获取一条可用代理 IP（供东方财富行情拉取的短时代理池消费）

            curl -X 'POST' \
              'https://stockapi.jaspil.cn/api/StockDic/GetProxyListByOne' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{}'
        """
        return self._make_request('POST', '/api/StockDic/GetProxyListByOne', payload)
