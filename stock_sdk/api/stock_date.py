"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import t_stock_date
from ..response import ResponseDto
from ._metadata import endpoint

class StockdateApi(ApiGroup):
    @endpoint('POST', '/api/StockDate/Add')
    def add(
        self,
        request: t_stock_date | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDate/Add', json_body=request)
