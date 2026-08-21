"""Loki's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Loki's authentication changed tomorrow, because the authentication is
not in it. There is no constructor parameter for a credential and no attribute
to hold one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.pagination import (
    MAX_PAGES_PER_CALL,
    EndpointPagination,
    Page,
    Pages,
    PaginationStyle,
    walk,
)
from integrations._base.payload import records
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.loki.schema import INTEGRATION, base_url

PING_PATH: Final = "/loki/api/v1/labels"
SEARCH_LOGS_PATH: Final = "/loki/api/v1/query_range"
RECENT_LOGS_PATH: Final = "/loki/api/v1/query_range"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="search_logs",
        style=PaginationStyle.CURSOR,
        parameter="start",
        page_size_parameter="limit",
        page_size=1000,
    ),
    EndpointPagination(
        endpoint="recent_logs",
        style=PaginationStyle.CURSOR,
        parameter="start",
        page_size_parameter="limit",
        page_size=100,
    ),
)


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class LokiClient(IntegrationClient):
    """Loki, reached through the credential proxy."""

    integration = INTEGRATION

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        region: str = "",
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url(region),
            retry=retry,
        )

    async def search_logs(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Loki holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {
                "query": query,
                "start": start,
                "end": end,
                "direction": "backward",
            }
            asked.update(parameters)
            answer = (await self.get(SEARCH_LOGS_PATH, params=asked)).json()
            return Page(items=records(answer, "data", "result"), cursor="" or None)

        return await walk(_pagination("search_logs"), fetch, max_pages=max_pages, max_items=limit)

    async def recent_logs(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Loki holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {
                "query": query,
                "start": start,
                "end": end,
                "direction": "backward",
            }
            asked.update(parameters)
            answer = (await self.get(RECENT_LOGS_PATH, params=asked)).json()
            return Page(items=records(answer, "data", "result"), cursor="" or None)

        return await walk(_pagination("recent_logs"), fetch, max_pages=max_pages, max_items=limit)

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Loki offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.get(PING_PATH)


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "SEARCH_LOGS_PATH",
    "RECENT_LOGS_PATH",
    "LokiClient",
]
