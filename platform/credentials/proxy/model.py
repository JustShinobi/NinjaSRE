"""The two requests the proxy sits between, and the port that carries the second.

A capability builds a ``ProxyRequest``: what it wants to ask the vendor, plus
who is asking. It carries no credential, because there is none to carry — the
whole envelope is safe in a log line.

The proxy turns that into an ``OutboundRequest``: the same call with the secret
in it. That object exists for microseconds inside one function, is handed
straight to an ``OutboundSender``, and is never returned, logged, or stored. The
two types are separate so that "which of these may I write down" is a question
about a type rather than about a code path.

``OutboundRequest`` is immutable and its ``with_*`` methods return copies.
Injections compose by returning a new request each, which means an injection
cannot half-apply and leave a request that is neither authenticated nor clean —
either the whole chain ran or the original is what you still hold.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class OutboundRequest:
    """One request as it will leave for the vendor, credential included.

    Never rendered, never persisted, never returned to a caller above the proxy.
    Its ``repr`` is the dataclass default on purpose: adding a redacting ``repr``
    would suggest that printing one is a thing somebody might legitimately do.
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None

    @property
    def host(self) -> str:
        """Return the host this request is addressed to, without a port."""
        return urlsplit(self.url).hostname or ""

    @property
    def path(self) -> str:
        """Return the path component of the URL."""
        return urlsplit(self.url).path

    def with_header(self, name: str, value: str) -> OutboundRequest:
        """Return a copy carrying one more header."""
        return self.with_headers({name: value})

    def with_headers(self, headers: Mapping[str, str]) -> OutboundRequest:
        """Return a copy with ``headers`` merged over the current ones."""
        merged = dict(self.headers)
        merged.update(headers)
        return OutboundRequest(method=self.method, url=self.url, headers=merged, body=self.body)

    def with_url(self, url: str) -> OutboundRequest:
        """Return a copy addressed to ``url``."""
        return OutboundRequest(method=self.method, url=url, headers=self.headers, body=self.body)

    def with_body(self, body: bytes | None) -> OutboundRequest:
        """Return a copy carrying ``body``."""
        return OutboundRequest(method=self.method, url=self.url, headers=self.headers, body=body)

    def with_query(self, parameters: Mapping[str, str]) -> OutboundRequest:
        """Return a copy with ``parameters`` merged into the query string.

        Existing parameters of the same name are replaced rather than repeated.
        A vendor that received ``?api_key=old&api_key=new`` would pick one, and
        which one is a property of its framework rather than of anything written
        here.
        """
        split = urlsplit(self.url)
        existing = [
            (name, value)
            for name, value in parse_qsl(split.query, keep_blank_values=True)
            if name not in parameters
        ]
        query = urlencode([*existing, *parameters.items()])
        return self.with_url(urlunsplit(split._replace(query=query)))

    def with_path(self, path: str) -> OutboundRequest:
        """Return a copy whose path component is ``path``."""
        split = urlsplit(self.url)
        return self.with_url(urlunsplit(split._replace(path=path)))


@dataclass(frozen=True, slots=True)
class OutboundResponse:
    """What the vendor answered, on its way back to the capability.

    The body is bytes rather than a parsed document because the proxy has no
    business understanding it. Deciding what a vendor's payload means belongs to
    that vendor's client, one tier up.
    """

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def succeeded(self) -> bool:
        """Return whether the vendor answered with a 2xx."""
        return 200 <= self.status_code < 300


@dataclass(frozen=True, slots=True)
class ProxyRequest:
    """What a capability asks the proxy to do, carrying no secret.

    Every field here is safe in a trace. ``integration`` selects the injection
    rule, ``org_id`` and ``team_id`` scope the resolution (FR-007), and
    ``capability`` is what makes an audit line answer "which tool used this
    credential" rather than only "something did".
    """

    integration: str
    org_id: str
    team_id: str
    capability: str
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None

    def __post_init__(self) -> None:
        for name in ("integration", "org_id", "capability", "method", "url"):
            if not getattr(self, name):
                raise ValueError(f"a proxy request needs a {name}")

    def outbound(self) -> OutboundRequest:
        """Return this request as it stands before any credential is injected."""
        return OutboundRequest(
            method=self.method, url=self.url, headers=dict(self.headers), body=self.body
        )


@runtime_checkable
class OutboundSender(Protocol):
    """Whatever actually puts bytes on the wire.

    A port rather than a concrete client for two reasons that both matter here.
    The suite drives the whole proxy — resolution, injection, allow-list,
    signing, refresh, audit — with no network and no credential, which is what
    makes those tests run on every pull request. And a deployment that has to
    egress through its own hardened HTTP stack substitutes one class instead of
    forking the proxy.
    """

    async def send(
        self,
        request: OutboundRequest,
        *,
        timeout_seconds: float,
    ) -> OutboundResponse:
        """Send ``request`` and return what came back.

        Raises rather than returning a synthetic response when nothing came
        back at all: a 502 the proxy invented and a 502 the vendor sent lead to
        different operator actions, and a caller that cannot tell them apart
        will eventually take the wrong one.
        """


__all__ = [
    "OutboundRequest",
    "OutboundResponse",
    "OutboundSender",
    "ProxyRequest",
]
