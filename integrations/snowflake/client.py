"""Snowflake's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Snowflake's authentication changed tomorrow, because the authentication is
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
from integrations._base.payload import tabular
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.snowflake.schema import INTEGRATION, base_url

PING_PATH: Final = "/api/v2/statements"
LIST_SESSIONS_PATH: Final = "/api/v2/statements"
SLOW_QUERIES_PATH: Final = "/api/v2/statements"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="list_sessions",
        style=PaginationStyle.OFFSET,
        parameter="partition",
        page_size_parameter="",
        page_size=100,
    ),
    EndpointPagination(
        endpoint="slow_queries",
        style=PaginationStyle.OFFSET,
        parameter="partition",
        page_size_parameter="",
        page_size=20,
    ),
)


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class SnowflakeClient(IntegrationClient):
    """Snowflake, reached through the credential proxy."""

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

    async def list_sessions(
        self,
        scope: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Snowflake holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Snowflake narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del scope, start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "statement": "SELECT query_id, user_name, execution_status FROM TABLE(information_schema.query_history()) WHERE execution_status = 'RUNNING'",
                "timeout": 30,
            }
            body.update(parameters)
            answer = (await self.post(LIST_SESSIONS_PATH, json_body=body)).json()
            return Page(
                items=tabular(answer, "resultSetMetaData.rowType", "data", name="name"),
                cursor="" or None,
            )

        return await walk(_pagination("list_sessions"), fetch, max_pages=max_pages, max_items=limit)

    async def slow_queries(
        self,
        scope: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what Snowflake holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Snowflake narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del scope, start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "statement": "SELECT query_text, total_elapsed_time FROM TABLE(information_schema.query_history()) ORDER BY total_elapsed_time DESC LIMIT 20",
                "timeout": 30,
            }
            body.update(parameters)
            answer = (await self.post(SLOW_QUERIES_PATH, json_body=body)).json()
            return Page(
                items=tabular(answer, "resultSetMetaData.rowType", "data", name="name"),
                cursor="" or None,
            )

        return await walk(_pagination("slow_queries"), fetch, max_pages=max_pages, max_items=limit)

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Snowflake offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.post(PING_PATH, json_body={"statement": "SELECT 1", "timeout": 10})


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "LIST_SESSIONS_PATH",
    "SLOW_QUERIES_PATH",
    "SnowflakeClient",
]
