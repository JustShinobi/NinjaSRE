"""Confluence's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Confluence's authentication changed tomorrow, because the authentication is
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
from integrations.confluence.schema import INTEGRATION, base_url

PING_PATH: Final = "/wiki/rest/api/space"
SEARCH_ISSUES_PATH: Final = "/wiki/rest/api/content/search"
RECENT_ISSUES_PATH: Final = "/wiki/rest/api/content/search"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="search_issues",
        style=PaginationStyle.OFFSET,
        parameter="start",
        page_size_parameter="limit",
        page_size=100,
    ),
    EndpointPagination(
        endpoint="recent_issues",
        style=PaginationStyle.OFFSET,
        parameter="start",
        page_size_parameter="limit",
        page_size=20,
    ),
)


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class ConfluenceClient(IntegrationClient):
    """Confluence, reached through the credential proxy."""

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

    async def search_issues(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Confluence holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Confluence narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {"cql": query or "type=page order by lastmodified desc"}
            asked.update(parameters)
            answer = (await self.get(SEARCH_ISSUES_PATH, params=asked)).json()
            return Page(items=records(answer, "results"), cursor="" or None)

        return await walk(_pagination("search_issues"), fetch, max_pages=max_pages, max_items=limit)

    async def recent_issues(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Confluence holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Confluence narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {
                "cql": query or "type=page order by lastmodified desc",
                "expand": "version,space",
            }
            asked.update(parameters)
            answer = (await self.get(RECENT_ISSUES_PATH, params=asked)).json()
            return Page(items=records(answer, "results"), cursor="" or None)

        return await walk(_pagination("recent_issues"), fetch, max_pages=max_pages, max_items=limit)

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Confluence offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.get(PING_PATH, params={"limit": "1"})


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "SEARCH_ISSUES_PATH",
    "RECENT_ISSUES_PATH",
    "ConfluenceClient",
]
