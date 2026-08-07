"""CloudWatch, over the proxy, with no signing key anywhere in this process.

This is the client SC-006 is about. It builds an ordinary unsigned request — a
POST with a JSON body and the target header CloudWatch's protocol wants — and
hands it to the proxy, which signs it. Nothing here imports a crypto library,
holds a key, or knows what SigV4 is.

FR-018's ``PROXY_SIGNED`` row, and the reason the row exists. The vendor SDK
signs internally, in-process, with a key it loaded itself from the environment or
an instance profile. There is no way to configure that away, so the SDK is not
used; the signing moved to the proxy and the client became small.

The methods are the two CloudWatch reads an investigation makes: filter a log
group over the incident window, and read a metric's statistics. Both take the
window explicitly, because a capability that let the vendor default it would
silently read the wrong hours.
"""

from __future__ import annotations

import json
from typing import Any, Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.pagination import (
    MAX_PAGES_PER_CALL,
    EndpointPagination,
    Page,
    Pages,
    PaginationStyle,
    collect,
)
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.aws.schema import (
    CLOUDWATCH_LOGS,
    DEFAULT_REGION,
    INTEGRATION,
    host_for,
)

#: CloudWatch Logs speaks the JSON 1.1 protocol: one path, and the operation in
#: a header. That is why every call below is a POST to ``/``.
LOGS_TARGET_HEADER: Final = "X-Amz-Target"
LOGS_CONTENT_TYPE: Final = "application/x-amz-json-1.1"

FILTER_LOG_EVENTS: Final = "Logs_20140328.FilterLogEvents"
DESCRIBE_LOG_GROUPS: Final = "Logs_20140328.DescribeLogGroups"

#: CloudWatch's own ceiling for one FilterLogEvents page.
MAX_LOG_EVENTS_PER_PAGE: Final = 10_000

#: How each paginated endpoint asks for the page after the one it read (FR-005).
#: CloudWatch calls its cursor a next token and puts it in the request body
#: rather than a query string, which is the case the ``PAGE_TOKEN`` name exists
#: for: an integration author reads "nextToken" in AWS's documentation and finds
#: the style spelled the way they read it.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="filter_log_events",
        style=PaginationStyle.PAGE_TOKEN,
        parameter="nextToken",
        page_size_parameter="limit",
        page_size=MAX_LOG_EVENTS_PER_PAGE,
    ),
)


class CloudWatchLogsClient(IntegrationClient):
    """CloudWatch Logs, signed by the proxy and never by this process."""

    integration = INTEGRATION

    __slots__ = ("_region",)

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        region: str = DEFAULT_REGION,
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=f"https://{host_for(CLOUDWATCH_LOGS, region)}",
            retry=retry,
        )
        self._region = region

    @property
    def region(self) -> str:
        """Return the region this client reads from."""
        return self._region

    async def filter_log_events(
        self,
        log_group: str,
        *,
        start_ms: int,
        end_ms: int,
        pattern: str = "",
        limit: int = 100,
        max_pages: int = MAX_PAGES_PER_CALL,
    ) -> Pages[dict[str, Any]]:
        """Return the log events in ``log_group`` inside the window, bounded."""
        page_size = min(limit, MAX_LOG_EVENTS_PER_PAGE)

        async def fetch(cursor: str | None) -> Page[dict[str, Any]]:
            body: dict[str, Any] = {
                "logGroupName": log_group,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": page_size,
            }
            if pattern:
                body["filterPattern"] = pattern
            if cursor is not None:
                body["nextToken"] = cursor
            answer = await self._operation(FILTER_LOG_EVENTS, body)
            token = answer.get("nextToken")
            return Page(items=tuple(answer.get("events", ())), cursor=token or None)

        return await collect(fetch, max_pages=max_pages, max_items=limit)

    async def describe_log_groups(self, *, prefix: str = "") -> tuple[dict[str, Any], ...]:
        """Return the log groups, optionally narrowed by name prefix."""
        body: dict[str, Any] = {}
        if prefix:
            body["logGroupNamePrefix"] = prefix
        answer = await self._operation(DESCRIBE_LOG_GROUPS, body)
        return tuple(answer.get("logGroups", ()))

    async def ping(self) -> ClientResponse:
        """Ask for one log group — the cheapest signed call CloudWatch offers.

        Used by the verifier, and the concrete demonstration of SC-006: this
        succeeds against real AWS with no signing key in the process that made
        it.
        """
        return await self.post(
            "/",
            json_body={"limit": 1},
            headers={
                LOGS_TARGET_HEADER: DESCRIBE_LOG_GROUPS,
                "content-type": LOGS_CONTENT_TYPE,
            },
        )

    async def _operation(self, target: str, body: dict[str, Any]) -> dict[str, Any]:
        """Make one JSON-1.1 call and return the parsed answer."""
        response = await self.post(
            "/",
            json_body=body,
            headers={LOGS_TARGET_HEADER: target, "content-type": LOGS_CONTENT_TYPE},
        )
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise ValueError(
                f"CloudWatch answered {target} with a {type(parsed).__name__} rather than an object"
            )
        return parsed


def log_event_message(event: dict[str, Any]) -> str:
    """Return one CloudWatch event's message, whichever shape it arrived in.

    CloudWatch puts the text in ``message``, and a subscription-filtered event
    puts a JSON document there instead. Returning the raw string either way
    keeps the decision about what it means with the capability that asked.
    """
    message = event.get("message", "")
    return message if isinstance(message, str) else json.dumps(message)


__all__ = [
    "DESCRIBE_LOG_GROUPS",
    "FILTER_LOG_EVENTS",
    "LOGS_CONTENT_TYPE",
    "LOGS_TARGET_HEADER",
    "MAX_LOG_EVENTS_PER_PAGE",
    "PAGINATION",
    "CloudWatchLogsClient",
    "log_event_message",
]
