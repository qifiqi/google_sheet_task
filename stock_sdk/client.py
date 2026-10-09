"""Public synchronous SDK client."""

from __future__ import annotations

import requests

from .api import bind_api_groups
from .http_client import DEFAULT_BASE_URL, SyncHttpClient


class StockClient(SyncHttpClient):
    """Synchronous client for DY.Stock.Api.

    Controller groups are available as snake_case attributes, for example
    ``client.east_money_stock_quote.get_stock_quote(request)``.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__(
            token=token,
            base_url=base_url,
            timeout=timeout,
            session=session,
        )
        bind_api_groups(self)
