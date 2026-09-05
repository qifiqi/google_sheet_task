"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import IdRequestDto, RequsetPageDto, t_stock_smsmsg
from ..response import ResponseDto
from ._metadata import endpoint

class StocksmsmsgApi(ApiGroup):
    @endpoint('POST', '/api/StockSmsMsg/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockSmsMsg/Delete', json_body=request)

    @endpoint('POST', '/api/StockSmsMsg/GetById')
    def get_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockSmsMsg/GetById', json_body=request)

    @endpoint('POST', '/api/StockSmsMsg/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: RequsetPageDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockSmsMsg/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockSmsMsg/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_smsmsg | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockSmsMsg/ModifyOrAdd', json_body=request)
