"""Prometheus's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Prometheus's authentication changed tomorrow, because the authentication is
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
from integrations.prometheus.schema import INTEGRATION
from integrations.prometheus.schema import base_url as _region_url

PING_PATH: Final = "/api/v1/status/buildinfo"
QUERY_METRIC_PATH: Final = "/api/v1/query_range"
#: The instant query. A signal is one number at one moment, and asking the range
#: endpoint for it means inventing a window — which is a different question with
#: a different answer, and a 400 when the window is left out.
INSTANT_QUERY_PATH: Final = "/api/v1/query"
LIST_ALERTS_PATH: Final = "/api/v1/alerts"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="query_metric",
        style=PaginationStyle.CURSOR,
        parameter="start",
        page_size_parameter="",
        page_size=0,
    ),
    EndpointPagination(
        endpoint="list_alerts",
        style=PaginationStyle.CURSOR,
        parameter="start",
        page_size_parameter="",
        page_size=0,
    ),
)


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class PrometheusClient(IntegrationClient):
    """Prometheus, reached through the credential proxy."""

    integration = INTEGRATION

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        region: str = "",
        base_url: str = "",
        retry: RetryPolicy | None = None,
    ) -> None:
        # The operator's own address wins over the shipped region, which is a
        # placeholder: nobody packaging this knows where your Prometheus is.
        # The egress allow-list still decides whether the host may be reached.
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url or _region_url(region),
            retry=retry,
        )

    async def query_metric(
        self,
        query: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Prometheus holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {"query": query, "start": start, "end": end, "step": "60s"}
            asked.update(parameters)
            answer = (await self.get(QUERY_METRIC_PATH, params=asked)).json()
            return Page(items=records(answer, "data", "result"), cursor="" or None)

        return await walk(_pagination("query_metric"), fetch, max_pages=max_pages, max_items=limit)

    async def query_instant(self, expression: str) -> tuple[dict[str, Any], ...]:
        """Return the series ``expression`` evaluates to, now.

        One request and no paging: an instant query answers with a vector whose
        length is the number of series that matched, and Prometheus does not
        page it.
        """
        answer = (await self.get(INSTANT_QUERY_PATH, params={"query": expression})).json()
        return records(answer, "data", "result")

    async def list_alerts(
        self,
        state: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Prometheus holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Prometheus narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del state, start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {}
            asked.update(parameters)
            answer = (await self.get(LIST_ALERTS_PATH, params=asked)).json()
            return Page(items=records(answer, "data", "alerts"), cursor="" or None)

        return await walk(_pagination("list_alerts"), fetch, max_pages=max_pages, max_items=limit)

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Prometheus offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.get(PING_PATH)


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "INSTANT_QUERY_PATH",
    "QUERY_METRIC_PATH",
    "LIST_ALERTS_PATH",
    "PrometheusClient",
]
