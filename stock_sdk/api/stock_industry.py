"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup

from ..response import ResponseDto
from ._metadata import endpoint

class StockindustryApi(ApiGroup):
    @endpoint('POST', '/api/StockIndustry/GetListForSelect')
    def get_list_for_select(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockIndustry/GetListForSelect')
