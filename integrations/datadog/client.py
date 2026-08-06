"""Datadog's API, over the proxy, holding no key.

A direct client rather than the vendor SDK (FR-018, ``DIRECT_CLIENT``). The
reasoning is in ``config.py``; what it means here is that this file is the whole
integration — paths, query grammar, and cursor handling — and every line of it
would be the same if Datadog's authentication changed tomorrow, because the
authentication is not in it.

The methods are the three an investigation actually reaches for: search logs,
read a metric series, and list the monitors that are alerting. Each is bounded,
each pages through ``integrations/_base/pagination.py``, and each returns the
vendor's own documents rather than a normalised shape — normalisation belongs to
the capability, which knows what the investigation asked.
"""

from __future__ import annotations

from typing import Any, Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.pagination import MAX_PAGES_PER_CALL, Page, Pages, collect
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.datadog.config import INTEGRATION, base_url

LOGS_SEARCH_PATH: Final = "/api/v2/logs/events/search"
LOGS_EVENTS_PATH: Final = "/api/v2/logs/events"
METRICS_QUERY_PATH: Final = "/api/v1/query"
MONITORS_PATH: Final = "/api/v1/monitor"

#: Datadog's own per-page ceiling for the logs API. Asking for more is answered
#: with this anyway, so requesting it makes the page count predictable.
MAX_LOGS_PAGE_SIZE: Final = 1000


class DatadogClient(IntegrationClient):
    """Datadog, reached through the credential proxy.

    ``site`` is the organisation's regional deployment and is not a secret — it
    selects the base URL, and the proxy's allow-list holds whichever one it
    resolves to.
    """

    integration = INTEGRATION

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        site: str = "datadoghq.com",
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url(site),
            retry=retry,
        )

    async def search_logs(
        self,
        query: str,
        *,
        start: str,
        end: str,
        limit: int = 100,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return the log events matching ``query`` in the window, bounded.

        The result carries ``truncated``, and a capability that drops it is
        reporting "no more matches" when what happened was "we stopped
        looking".
        """
        page_size = min(limit, MAX_LOGS_PAGE_SIZE)

        async def fetch(cursor: str | None) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "filter": {"query": query, "from": start, "to": end},
                "page": {"limit": page_size},
                "sort": "-timestamp",
            }
            if cursor is not None:
                body["page"]["cursor"] = cursor
            answer = (await self.post(LOGS_SEARCH_PATH, json_body=body)).json()
            return Page(
                items=tuple(answer.get("data", ())),
                cursor=_logs_cursor(answer),
            )

        return await collect(fetch, max_pages=max_pages, max_items=limit)

    async def query_metric(self, query: str, *, start: int, end: int) -> dict[str, Any]:
        """Return one metric series for the window, as Datadog returns it."""
        response = await self.get(
            METRICS_QUERY_PATH,
            params={"query": query, "from": str(start), "to": str(end)},
        )
        return dict(response.json())

    async def alerting_monitors(self, *, tags: str = "") -> tuple[dict[str, Any], ...]:
        """Return the monitors currently in an alerting state, optionally by tag."""
        params = {"group_states": "alert"}
        if tags:
            params["monitor_tags"] = tags
        return tuple((await self.get(MONITORS_PATH, params=params)).json())

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call Datadog offers.

        Used by the verifier. Listing zero monitors costs nothing and still
        requires both keys, which is exactly what a credential check needs.
        """
        return await self.get(MONITORS_PATH, params={"page_size": "1"})


def _logs_cursor(answer: dict[str, Any]) -> str | None:
    """Return the next-page cursor Datadog's logs response carries, if any.

    Datadog puts it in ``meta.page.after``, and puts nothing there on the last
    page. Reading it defensively rather than by index matters because an error
    response has the same content type and would otherwise raise a ``KeyError``
    a long way from the cause.
    """
    page = answer.get("meta", {}).get("page", {})
    cursor = page.get("after")
    return str(cursor) if cursor else None


__all__ = [
    "LOGS_EVENTS_PATH",
    "LOGS_SEARCH_PATH",
    "MAX_LOGS_PAGE_SIZE",
    "METRICS_QUERY_PATH",
    "MONITORS_PATH",
    "DatadogClient",
]
