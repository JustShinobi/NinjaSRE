"""The only sanctioned way to make an authenticated external call (FR-015).

Every vendor client in NinjaSRE inherits this, and inheriting it is what makes
Article IV structural rather than aspirational: there is no constructor argument
for a credential, no attribute to hold one, and no method that would accept one.
A client is built from a base URL, a transport, and a ``RequestContext`` that
names an organisation, a team, and a capability — all of which are safe in a
prompt.

What the base client provides, so no vendor has to provide it
differently (FR-016):

**Proxy routing.** ``request`` builds a ``ProxyRequest`` and hands it to the
transport. The vendor URL is constructed here and checked against the
integration's declared hosts by the proxy, so a client cannot reach somewhere its
integration did not declare.

**Retry with backoff.** Only on retryable classes, honouring ``Retry-After``,
with jitter. See ``retry.py`` for why each of those is not optional.

**Timeouts.** A budget per call, from a named constant. A vendor that never
answers must not be able to hold an investigation's only worker.

**Structured errors.** A non-2xx becomes an ``IntegrationError`` carrying a
classified reason, which becomes a ``CapabilityError`` the model can act on.
Raising rather than returning is deliberate here: a vendor client's caller is a
capability, and the capability is where the decision to turn a failure into a
result belongs.

**Bounded bodies.** A response is read into memory, so it is bounded. A vendor
answering a bad request with a megabyte of HTML should not put a megabyte of
HTML into a trace.

The one thing it does *not* provide is knowledge of the vendor. Path shapes,
query grammar, payload parsing, and pagination cursors belong to the subclass,
because that is the part that changes when a vendor changes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlencode, urljoin

from config.constants.security import CREDENTIAL_PROXY_TIMEOUT_SECONDS
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.retry import RetryPolicy, parse_retry_after
from integrations._base.transport import ProxyTransport, RequestContext
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: How much of a vendor's error body reaches an exception. Enough to identify
#: the problem, short enough that a trace stays readable.
MAX_ERROR_BODY_CHARS: Final = 512

#: How much of a vendor's *successful* body a client will parse. A response
#: larger than this is a query that should have been narrowed, and truncating it
#: silently would hide that.
MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ClientResponse:
    """One vendor answer, before the subclass decides what it means."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def text(self) -> str:
        """Return the body decoded as UTF-8, replacing anything undecodable."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Return the body parsed as JSON, or raise ``ValueError`` saying it was not."""
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"the vendor answered {self.status_code} with a body that is not JSON: {error.msg}"
            ) from error


class IntegrationClient:
    """A vendor API, reached through the credential proxy and never around it.

    Subclasses add the vendor's own methods and nothing about authentication —
    which is what makes writing an integration a matter of knowing the API
    rather than knowing the security model.
    """

    #: The integration this client speaks for. Subclasses set it, and it is what
    #: selects the injection rule and the egress allow-list at the proxy.
    integration: str = ""

    __slots__ = ("_base_url", "_context", "_retry", "_timeout_seconds", "_transport")

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        base_url: str,
        retry: RetryPolicy | None = None,
        timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS,
    ) -> None:
        if not self.integration:
            raise ValueError(
                f"{type(self).__name__} does not declare an integration name, so the proxy "
                f"cannot tell which injection rule applies to its calls"
            )
        self._transport = transport
        self._context = context
        self._base_url = base_url if base_url.endswith("/") else base_url + "/"
        self._retry = retry if retry is not None else RetryPolicy()
        self._timeout_seconds = timeout_seconds

    @property
    def base_url(self) -> str:
        """Return the vendor base URL this client builds requests against."""
        return self._base_url

    @property
    def context(self) -> RequestContext:
        """Return who this client is making calls for."""
        return self._context

    # -- the one call path ----------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> ClientResponse:
        """Make one authenticated call and return the vendor's answer.

        Raises ``IntegrationError`` for a proxy refusal or a non-2xx status.
        ``path`` may be absolute, which is how a client follows a vendor's own
        pagination link — the proxy's allow-list still applies, so an absolute
        URL cannot leave the declared hosts.
        """
        url = self._url(path, params)
        payload, request_headers = self._payload(json_body, body, headers)

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._send(method, url, request_headers, payload)
                return self._check(response, method=method, path=path)
            except IntegrationError as error:
                if not self._retry.should_retry(error, attempt=attempt):
                    raise
                delay = self._retry.delay_for(
                    attempt, retry_after=parse_retry_after(error.detail or None)
                )
                logger.info(
                    "integration.retry",
                    integration=self.integration,
                    capability=self._context.capability,
                    reason=str(error.reason),
                    attempt=attempt,
                    delay_seconds=round(delay, 3),
                )
                await asyncio.sleep(delay)

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ClientResponse:
        """Make an authenticated ``GET``."""
        return await self.request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        *,
        json_body: Any = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ClientResponse:
        """Make an authenticated ``POST``."""
        return await self.request("POST", path, params=params, json_body=json_body, headers=headers)

    async def put(
        self,
        path: str,
        *,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> ClientResponse:
        """Make an authenticated ``PUT``."""
        return await self.request("PUT", path, json_body=json_body, headers=headers)

    async def delete(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ClientResponse:
        """Make an authenticated ``DELETE``."""
        return await self.request("DELETE", path, params=params, headers=headers)

    # -- the pieces -----------------------------------------------------------

    def _url(self, path: str, params: Mapping[str, str] | None) -> str:
        """Return the absolute vendor URL for ``path`` with ``params`` attached."""
        url = path if "://" in path else urljoin(self._base_url, path.lstrip("/"))
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(dict(params))}"
        return url

    def _payload(
        self,
        json_body: Any,
        body: bytes | None,
        headers: Mapping[str, str] | None,
    ) -> tuple[bytes | None, dict[str, str]]:
        """Return the encoded body and the headers that describe it."""
        request_headers = dict(headers) if headers else {}
        if json_body is not None and body is not None:
            raise ValueError("a request carries either a JSON body or raw bytes, not both")
        if json_body is not None:
            request_headers.setdefault("content-type", "application/json")
            return json.dumps(json_body).encode("utf-8"), request_headers
        return body, request_headers

    async def _send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> OutboundResponse:
        """Hand one request to the proxy, inside the call's time budget."""
        request = ProxyRequest(
            integration=self.integration,
            org_id=self._context.org_id,
            team_id=self._context.team_id,
            capability=self._context.capability,
            method=method.upper(),
            url=url,
            headers=dict(headers),
            body=body,
        )
        try:
            return await asyncio.wait_for(
                self._transport.forward(request), timeout=self._timeout_seconds
            )
        except TimeoutError as error:
            raise IntegrationError(
                f"{self.integration} did not answer within {self._timeout_seconds:g}s",
                integration=self.integration,
                reason=IntegrationErrorReason.TIMEOUT,
            ) from error

    def _check(
        self,
        response: OutboundResponse,
        *,
        method: str,
        path: str,
    ) -> ClientResponse:
        """Return ``response`` as a client response, or raise the classified failure."""
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise IntegrationError(
                f"{self.integration} answered {len(response.body)} bytes to {method} "
                f"{path}, above the {MAX_RESPONSE_BYTES} the client will hold. Narrow "
                f"the query rather than raising the bound.",
                integration=self.integration,
                reason=IntegrationErrorReason.INVALID_REQUEST,
                status_code=response.status_code,
            )
        if response.succeeded:
            return ClientResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.body,
            )

        retry_after = _header(response.headers, "retry-after")
        error = IntegrationError.from_status(
            integration=self.integration,
            status_code=response.status_code,
            body=response.body.decode("utf-8", errors="replace")[:MAX_ERROR_BODY_CHARS],
            method=method.upper(),
            path=path,
        )
        if retry_after and error.reason is IntegrationErrorReason.RATE_LIMITED:
            # The retry loop reads ``detail`` for the vendor's own wait, so a
            # rate-limit response carries the header rather than the body.
            error.detail = retry_after
        raise error


def _header(headers: Mapping[str, str], name: str) -> str:
    """Return a header's value case-insensitively, or the empty string."""
    lowered = name.lower()
    return next((value for key, value in headers.items() if key.lower() == lowered), "")


__all__ = [
    "MAX_ERROR_BODY_CHARS",
    "MAX_RESPONSE_BYTES",
    "ClientResponse",
    "IntegrationClient",
]
