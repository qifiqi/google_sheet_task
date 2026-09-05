"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockCnOrderListRequestDto, t_stock_cn_order
from ..response import ResponseDto
from ._metadata import endpoint

class StockcnorderApi(ApiGroup):
    @endpoint('POST', '/api/StockCnOrder/Add')
    def add(
        self,
        request: t_stock_cn_order | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockCnOrder/Add', json_body=request)

    @endpoint('POST', '/api/StockCnOrder/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockCnOrderListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockCnOrder/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockCnOrder/GetStockUserList')
    def get_stock_user_list(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockCnOrder/GetStockUserList')
