"""Alertmanager's API, over the proxy, holding no credential.

This file is the whole integration as far as the vendor is concerned — paths,
query grammar, and pagination — and every line of it would be the same if
Alertmanager's authentication changed tomorrow, because the authentication is
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
from integrations.alertmanager.schema import INTEGRATION
from integrations.alertmanager.schema import base_url as _region_url

PING_PATH: Final = "/api/v2/status"
LIST_INCIDENTS_PATH: Final = "/api/v2/alerts"
INCIDENT_TIMELINE_PATH: Final = "/api/v2/alerts/groups"
ACKNOWLEDGE_PATH: Final = "/api/v2/silences"

#: How many records one call reads before it stops. Small on purpose: the model
#: reads what comes back, and the hundredth record buys nothing the tenth did not.
DEFAULT_LIMIT: Final = 100

#: How each paginated endpoint asks for the page after the one it read. Declared
#: beside the methods, so the declaration and the code it describes cannot drift
#: without the contract suite naming both.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="list_incidents",
        style=PaginationStyle.CURSOR,
        parameter="filter",
        page_size_parameter="",
        page_size=0,
    ),
    EndpointPagination(
        endpoint="incident_timeline",
        style=PaginationStyle.CURSOR,
        parameter="filter",
        page_size_parameter="",
        page_size=0,
    ),
)


#: Prefix every identifier this deployment mints carries. An agent handed one
#: as the only name it has for a subject will pass it here, and Alertmanager has
#: never heard of it: sending it as a matcher earns a 400, and sending it as an
#: ``alertname`` earns an empty answer, which reads as "there is nothing" rather
#: than "you asked wrongly". Neither is worth a turn.
_LOCAL_ID_PREFIXES: Final[tuple[str, ...]] = ("res-", "inc_", "run-")

#: The status words a caller might use, and what each one means to the two
#: boolean parameters Alertmanager actually narrows status by. ``filter`` is for
#: label matchers and nothing else — sending "firing" there is what produced
#: `400 bad matcher format: firing` on every statistics call staging made.
_STATUS_PARAMETERS: Final[dict[str, dict[str, str]]] = {
    "firing": {"active": "true", "silenced": "false"},
    "active": {"active": "true", "silenced": "false"},
    "silenced": {"active": "true", "silenced": "true"},
    "suppressed": {"active": "true", "silenced": "true"},
    "resolved": {"active": "false", "silenced": "false"},
    "inactive": {"active": "false", "silenced": "false"},
}


def _matcher(value: str) -> str:
    """Return ``value`` as a matcher Alertmanager parses, or the empty string.

    Alertmanager's ``filter`` takes ``name="value"`` and refuses anything else
    with `400 bad matcher format`. A caller that already wrote one gets it
    forwarded; a bare word is the alert's name, which is what a bare word
    almost always is; and one of this deployment's own identifiers is dropped,
    because Alertmanager cannot answer about it however it is spelled.

    Formatting the vendor's grammar here rather than in the tool's description
    is deliberate. A capability whose correct use depends on the caller knowing
    a vendor's query language is a capability that gets called wrongly, and
    being refused afterwards costs the turn either way.
    """
    trimmed = value.strip()
    if not trimmed or trimmed.startswith(_LOCAL_ID_PREFIXES):
        return ""
    if "=" in trimmed:
        return trimmed
    return f'alertname="{trimmed}"'


def _pagination(endpoint: str) -> EndpointPagination:
    """Return the declared pagination for one endpoint of this client."""
    for declared in PAGINATION:
        if declared.endpoint == endpoint:
            return declared
    raise LookupError(f"{endpoint!r} declares no pagination style")


class AlertmanagerClient(IntegrationClient):
    """Alertmanager, reached through the credential proxy."""

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
        # placeholder: nobody packaging this knows where a self-hosted
        # Alertmanager is. The egress allow-list still decides whether the host
        # may be reached.
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url or _region_url(region),
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
        """Return what Alertmanager holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Alertmanager narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            # An empty ``filter`` is not "no narrowing" to Alertmanager, it is a
            # matcher it cannot parse — `400 bad matcher format`. So the
            # ordinary call, the one that asks what is firing without narrowing
            # anything, was the one that failed.
            asked: dict[str, str] = {"active": "true", "silenced": "false"}
            narrowed = _STATUS_PARAMETERS.get(status.strip().lower())
            if narrowed is not None:
                asked.update(narrowed)
            elif status:
                matcher = _matcher(status)
                if matcher:
                    asked["filter"] = matcher
            asked.update(parameters)
            answer = (await self.get(LIST_INCIDENTS_PATH, params=asked)).json()
            return Page(
                items=records(
                    answer,
                ),
                cursor="" or None,
            )

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
        """Return what Alertmanager holds for this request, bounded.

        The answer carries ``truncated``, and a capability that drops it reports
        "there is no more" when what happened was "we stopped looking".
        """
        # Alertmanager narrows this endpoint by other means; the argument stays in the
        # signature so every read in the catalogue is asked for the same way.
        del start, end

        async def fetch(parameters: Mapping[str, str]) -> Page[dict[str, Any]]:
            # Omitted when empty, for the reason ``list_incidents`` gives above.
            asked: dict[str, str] = {"active": "true"}
            matcher = _matcher(incident)
            if matcher:
                asked["filter"] = matcher
            asked.update(parameters)
            answer = (await self.get(INCIDENT_TIMELINE_PATH, params=asked)).json()
            return Page(
                items=records(
                    answer,
                ),
                cursor="" or None,
            )

        return await walk(
            _pagination("incident_timeline"), fetch, max_pages=max_pages, max_items=limit
        )

    async def acknowledge(self, incident: str, note: str) -> dict[str, Any]:
        """Make the one change this integration may make, and return what Alertmanager said."""
        body: dict[str, Any] = {
            "matchers": [{"name": "alertname", "value": incident, "isRegex": False}],
            "createdBy": "ninjasre",
            "comment": note,
            "startsAt": "",
            "endsAt": "",
        }
        answer = (await self.post(ACKNOWLEDGE_PATH, json_body=body)).json()
        return dict(answer) if isinstance(answer, dict) else {"result": answer}

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Alertmanager offers.

        Used by the verifier, and the one method every client has: it is what
        proves a credential works without spending quota or reading data.
        """
        return await self.get(PING_PATH)


__all__ = [
    "DEFAULT_LIMIT",
    "PAGINATION",
    "PING_PATH",
    "LIST_INCIDENTS_PATH",
    "INCIDENT_TIMELINE_PATH",
    "ACKNOWLEDGE_PATH",
    "AlertmanagerClient",
]
