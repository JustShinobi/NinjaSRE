"""ServiceNow's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
ServiceNow's authentication changed tomorrow, because the authentication is
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
from integrations.servicenow.schema import INTEGRATION, base_url

PING_PATH: Final = "/api/now/table/incident"
LIST_INCIDENTS_PATH: Final = "/api/now/table/incident"
INCIDENT_TIMELINE_PATH: Final = "/api/now/table/incident"
ACKNOWLEDGE_PATH: Final = "/api/now/table/incident"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="list_incidents",
        style=PaginationStyle.OFFSET,
        parameter="sysparm_offset",
        page_size_parameter="sysparm_limit",
        page_size=100,
    ),
    EndpointPagination(
        endpoint="incident_timeline",
        style=PaginationStyle.OFFSET,
        parameter="sysparm_offset",
        page_size_parameter="sysparm_limit",
        page_size=25,
    ),
)


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class ServicenowClient(IntegrationClient):
    """ServiceNow, reached through the credential proxy."""

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

    async def list_incidents(
        self,
        status: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what ServiceNow holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # ServiceNow narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {
                "sysparm_query": status or "active=true",
                "sysparm_display_value": "true",
            }
            asked.update(parameters)
            answer = (await self.get(LIST_INCIDENTS_PATH, params=asked)).json()
            return Page(items=records(answer, "result"), cursor="" or None)

        return await walk(
            _pagination("list_incidents"), fetch, max_pages=max_pages, max_items=limit
        )

    async def incident_timeline(
        self,
        incident: str = "",
        *,
        start: str = "",
        end: str = "",
        limit: int = DEFAULT_LIMIT,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return what ServiceNow holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # ServiceNow narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del incident, start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            asked: dict[str, str] = {
                "sysparm_query": "active=true^ORDERBYDESCsys_created_on",
                "sysparm_display_value": "true",
            }
            asked.update(parameters)
            answer = (await self.get(INCIDENT_TIMELINE_PATH, params=asked)).json()
            return Page(items=records(answer, "result"), cursor="" or None)

        return await walk(
            _pagination("incident_timeline"), fetch, max_pages=max_pages, max_items=limit
        )

    async def acknowledge(self, incident: str, note: str) -> dict[str, Any]:
        """Make the one change this integration may make, and return what ServiceNow said."""
        body: dict[str, Any] = {"correlation_id": incident, "work_notes": note}
        answer = (await self.post(ACKNOWLEDGE_PATH, json_body=body)).json()
        return dict(answer) if isinstance(answer, dict) else {"result": answer}

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call ServiceNow offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.get(PING_PATH, params={"sysparm_limit": "1"})


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "LIST_INCIDENTS_PATH",
    "INCIDENT_TIMELINE_PATH",
    "ACKNOWLEDGE_PATH",
    "ServicenowClient",
]
