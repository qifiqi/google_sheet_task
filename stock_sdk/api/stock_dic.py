"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetDicListForSelectRequestDto
from ..response import ResponseDto
from ._metadata import endpoint

class StockdicApi(ApiGroup):
    @endpoint('POST', '/api/StockDic/GetListForSelect')
    def get_list_for_select(
        self,
        request: GetDicListForSelectRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDic/GetListForSelect', json_body=request)

    @endpoint('POST', '/api/StockDic/GetProxyListByOne')
    def get_proxy_list_by_one(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDic/GetProxyListByOne')
