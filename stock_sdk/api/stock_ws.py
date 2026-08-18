"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup

from ..response import ResponseDto
from ._metadata import endpoint

class StockwsApi(ApiGroup):
    @endpoint('GET', '/api/StockWs/GetConnectionStats/stats')
    def get_connection_stats_stats(self) -> ResponseDto[Any]:
        return self._call('GET', '/api/StockWs/GetConnectionStats/stats')

    @endpoint('GET', '/api/StockWs/SendData/SendData')
    def send_data_send_data(self, *, id: int | None = None, type: int | None = None) -> ResponseDto[Any]:
        return self._call('GET', '/api/StockWs/SendData/SendData', params={'id': id, 'type': type})

    @endpoint('GET', '/api/StockWs/TypeTest')
    def type_test(self, *, req: str | None = None) -> ResponseDto[Any]:
        return self._call('GET', '/api/StockWs/TypeTest', params={'req': req})

    @endpoint('GET', '/ws')
    def ws(self) -> ResponseDto[Any]:
        return self._call('GET', '/ws')
