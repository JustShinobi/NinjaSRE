"""Railway's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Railway's authentication changed tomorrow, because the authentication is
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
from integrations._base.payload import records, text
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.railway.schema import INTEGRATION, base_url

PING_PATH: Final = "/graphql/v2"
LIST_RUNS_PATH: Final = "/graphql/v2"
LIST_FAILED_RUNS_PATH: Final = "/graphql/v2"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="list_runs",
        style=PaginationStyle.CURSOR,
        parameter="after",
        page_size_parameter="",
        page_size=0,
    ),
    EndpointPagination(
        endpoint="list_failed_runs",
        style=PaginationStyle.CURSOR,
        parameter="after",
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


class RailwayClient(IntegrationClient):
    """Railway, reached through the credential proxy."""

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

    async def list_runs(
        self,
        project: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Railway holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Railway narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "query": "query($p: String!) { deployments(input: {projectId: $p}) { edges { node { id status createdAt } } } }",
                "variables": {"p": project},
            }
            body.update(parameters)
            answer = (await self.post(LIST_RUNS_PATH, json_body=body)).json()
            return Page(
                items=records(answer, "data", "deployments", "edges"),
                cursor=text(answer, "data", "deployments", "pageInfo", "endCursor") or None,
            )

        return await walk(_pagination("list_runs"), fetch, max_pages=max_pages, max_items=limit)

    async def list_failed_runs(
        self,
        project: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Railway holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Railway narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "query": "query($p: String!) { deployments(input: {projectId: $p, status: FAILED}) { edges { node { id status createdAt } } } }",
                "variables": {"p": project},
            }
            body.update(parameters)
            answer = (await self.post(LIST_FAILED_RUNS_PATH, json_body=body)).json()
            return Page(
                items=records(answer, "data", "deployments", "edges"),
                cursor=text(answer, "data", "deployments", "pageInfo", "endCursor") or None,
            )

        return await walk(
            _pagination("list_failed_runs"), fetch, max_pages=max_pages, max_items=limit
        )

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Railway offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.post(PING_PATH, json_body={"query": "{ me { id } }"})


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "LIST_RUNS_PATH",
    "LIST_FAILED_RUNS_PATH",
    "RailwayClient",
]
