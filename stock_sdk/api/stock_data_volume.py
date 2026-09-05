"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockDataVolumeHisListRequestDto, GetStockDataVolumeListRequestDto, GetStockDataVolumeRequestDto, IdRequestDto, t_stock_data_volume, t_stock_data_volume_his
from ..response import ResponseDto
from ._metadata import endpoint

class StockdatavolumeApi(ApiGroup):
    @endpoint('POST', '/api/StockDataVolume/DeleteById')
    def delete_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/DeleteById', json_body=request)

    @endpoint('POST', '/api/StockDataVolume/GetList')
    def get_list(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/GetList')

    @endpoint('POST', '/api/StockDataVolume/GetListHisPage')
    def get_list_his_page(
        self,
        request: GetStockDataVolumeHisListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/GetListHisPage', json_body=request)

    @endpoint('POST', '/api/StockDataVolume/GetListPage')
    def get_list_page(
        self,
        request: GetStockDataVolumeListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/GetListPage', json_body=request)

    @endpoint('POST', '/api/StockDataVolume/GetListVolume')
    def get_list_volume(
        self,
        request: GetStockDataVolumeRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/GetListVolume', json_body=request)

    @endpoint('POST', '/api/StockDataVolume/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_data_volume | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/ModifyOrAdd', json_body=request)

    @endpoint('POST', '/api/StockDataVolume/ModifyOrAddHis')
    def modify_or_add_his(
        self,
        request: t_stock_data_volume_his | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataVolume/ModifyOrAddHis', json_body=request)
