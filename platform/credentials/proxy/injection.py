"""How each vendor's secret enters the outbound request, declared not coded.

FR-008 lists seven ways a credential can be attached to an HTTP call: a header,
a query parameter, a path segment, a body field, basic auth, a bearer token, and
a signature over the whole request. Every vendor uses one or two of them, and
the temptation is to write a small ``if integration == "datadog"`` somewhere.
That is how eighty-five integrations become eighty-five subtly different
authentication paths, of which some number are wrong in a way that only shows up
under load.

So an integration *declares* its injections and the proxy applies them:

    InjectionRule(
        integration="datadog",
        hosts=("api.datadoghq.com", "api.datadoghq.eu"),
        injections=(
            HeaderInjection(header="DD-API-KEY", field="api_key"),
            HeaderInjection(header="DD-APPLICATION-KEY", field="app_key"),
        ),
    )

Three properties of that declaration are load-bearing.

**``hosts`` is the egress allow-list** (FR-009). The same tuple that says where
this integration lives says where it may go, so an integration cannot reach a
host it did not declare — and there is no second list to keep in step with the
first.

**Every injection names its fields.** ``fields()`` is what lets the contract
suite assert that an injection only reads fields the credential schema declares,
which catches the rename that would otherwise send an unauthenticated request
and get back a 401 nobody can explain.

**An injection is pure.** It takes a request and returns a new one. Nothing here
logs, caches, or keeps a reference to what it was given, so the window in which
a credential exists in memory is the width of one function call.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from platform.credentials.errors import UnknownIntegration
from platform.credentials.proxy.model import OutboundRequest

#: What ``BasicAuthInjection`` and ``BearerTokenInjection`` write into.
AUTHORIZATION_HEADER = "Authorization"


@runtime_checkable
class Injection(Protocol):
    """One way a credential attaches to a request."""

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the credential attached.

        ``now`` is passed rather than read because signing schemes date their
        signatures, and a signer that called the clock itself could not be
        tested against a recorded vendor fixture.
        """


@runtime_checkable
class RequestSigner(Protocol):
    """A vendor's signature scheme, run on the proxy side of the boundary.

    This exists because AWS is the case that would otherwise break the whole
    invariant. SigV4 needs the secret key at request-construction time, so a
    client that signs is a client that holds a key — and AWS is the most-used
    integration family, which would make the exception larger than the rule.
    """

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this scheme needs."""

    def sign(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the scheme's signature attached."""


@dataclass(frozen=True, slots=True)
class HeaderInjection:
    """Put a credential field in a request header. The common case."""

    header: str
    field: str
    #: Rendered around the value: ``"Token {value}"``, ``"{value}"``. A format
    #: rather than a prefix because some vendors want the value in the middle.
    template: str = "{value}"

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.field,)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the header set."""
        return request.with_header(self.header, self.template.format(value=values[self.field]))


@dataclass(frozen=True, slots=True)
class QueryParameterInjection:
    """Put a credential field in the query string.

    Some vendors still want this. It is worse than a header — query strings
    reach access logs and referrer headers — but the alternative to supporting
    it is an integration that keeps its key in the client, which is worse still.
    """

    parameter: str
    field: str

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.field,)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the parameter set."""
        return request.with_query({self.parameter: values[self.field]})


@dataclass(frozen=True, slots=True)
class PathSegmentInjection:
    """Substitute a credential field into a placeholder in the path.

    The client sends ``/services/{token}/events`` and never knows what fills it.
    A placeholder that the path does not contain is a declaration error, and it
    raises rather than sending a request with a literal ``{token}`` in the URL —
    which a vendor would answer with a 404 that looks like a missing resource.
    """

    placeholder: str
    field: str

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.field,)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the placeholder replaced."""
        marker = "{" + self.placeholder + "}"
        path = request.path
        if marker not in path:
            raise ValueError(
                f"the path {path!r} has no {marker} for this integration's "
                f"path-segment injection to fill"
            )
        return request.with_path(path.replace(marker, values[self.field]))


@dataclass(frozen=True, slots=True)
class BodyFieldInjection:
    """Put a credential field into a JSON request body.

    Only JSON, and only an object at the top level. A vendor wanting a secret in
    a form-encoded body or an XML document gets its own injection rather than a
    content-type sniffing branch here, because guessing wrong means writing a
    credential into a payload shape that neither side understands.
    """

    body_field: str
    field: str

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.field,)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the body field set."""
        document = json.loads(request.body) if request.body else {}
        if not isinstance(document, dict):
            raise ValueError(
                "a body-field injection needs a JSON object at the top level of the request body"
            )
        document[self.body_field] = values[self.field]
        return request.with_body(json.dumps(document).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class BasicAuthInjection:
    """RFC 7617 basic auth, built from two credential fields."""

    username_field: str
    password_field: str

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.username_field, self.password_field)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with an ``Authorization: Basic`` header."""
        pair = f"{values[self.username_field]}:{values[self.password_field]}"
        encoded = base64.b64encode(pair.encode("utf-8")).decode("ascii")
        return request.with_header(AUTHORIZATION_HEADER, f"Basic {encoded}")


@dataclass(frozen=True, slots=True)
class BearerTokenInjection:
    """``Authorization: Bearer <token>``, the OAuth and API-token default."""

    field: str = "token"
    scheme: str = "Bearer"

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields this injection reads."""
        return (self.field,)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with the bearer header set."""
        return request.with_header(AUTHORIZATION_HEADER, f"{self.scheme} {values[self.field]}")


@dataclass(frozen=True, slots=True)
class SignatureInjection:
    """Run a vendor's request-signing scheme over the whole request.

    Wraps a ``RequestSigner`` so that signing is one more entry in the same
    declared list as the header injections, rather than a special case the
    engine has to know about.
    """

    signer: RequestSigner

    def fields(self) -> tuple[str, ...]:
        """Return the credential fields the signer needs."""
        return self.signer.fields()

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` signed."""
        return self.signer.sign(request, values, now=now)


@dataclass(frozen=True, slots=True)
class InjectionRule:
    """Everything the proxy needs to authenticate one integration's calls.

    ``refreshable`` says the credential behind this rule is short-lived — an
    OAuth access token, an STS session — which is what turns on the refresh
    window and the single expiry retry (FR-013). It is declared rather than
    inferred from the presence of an expiry, because a long-lived key with a
    rotation reminder also has an expiry and refreshing it would be wrong.
    """

    integration: str
    hosts: tuple[str, ...]
    injections: tuple[Injection, ...]
    refreshable: bool = False

    def __post_init__(self) -> None:
        if not self.hosts:
            raise ValueError(
                f"the injection rule for {self.integration!r} declares no hosts, so it "
                f"would permit nothing — an integration's hosts are its egress allow-list"
            )
        if not self.injections:
            raise ValueError(
                f"the injection rule for {self.integration!r} declares no injection, so "
                f"its requests would leave unauthenticated"
            )
        for host in self.hosts:
            if "/" in host or ":" in host:
                raise ValueError(
                    f"{host!r} is not a host name. An allow-list entry is a host, not a "
                    f"URL and not a host:port — the port is not a security boundary and "
                    f"including one makes the list wrong the first time a vendor moves."
                )

    def permits(self, host: str) -> bool:
        """Return whether ``host`` is one this integration declared.

        Exact match, case-insensitively. No wildcards: ``*.vendor.com`` is one
        acquisition away from permitting a host the operator never approved, and
        an integration that genuinely spans regions can list them.
        """
        return host.lower() in {declared.lower() for declared in self.hosts}

    def required_fields(self) -> tuple[str, ...]:
        """Return every credential field this rule's injections read, deduplicated."""
        seen: dict[str, None] = {}
        for injection in self.injections:
            for name in injection.fields():
                seen[name] = None
        return tuple(seen)

    def apply(
        self,
        request: OutboundRequest,
        values: Mapping[str, str],
        *,
        now: datetime,
    ) -> OutboundRequest:
        """Return ``request`` with every declared injection applied, in order.

        Order matters when one of them is a signature: a signer covers the
        headers that exist when it runs, so a rule that signs must declare the
        signature last. That is the integration's decision to get right, and the
        contract suite for a signed vendor asserts it.
        """
        signed = request
        for injection in self.injections:
            signed = injection.apply(signed, values, now=now)
        return signed


@dataclass(slots=True)
class InjectionRuleRegistry:
    """Which rule applies to which integration.

    A registry rather than a lookup into ``integrations/`` because ``platform/``
    is tier 3 and may not import tier 2. Composition fills it; the proxy reads
    it; and the indirection is what lets a deployment run with a subset of the
    catalogue installed.
    """

    _rules: dict[str, InjectionRule] = field(default_factory=dict)

    @classmethod
    def from_rules(cls, *rules: InjectionRule) -> InjectionRuleRegistry:
        """Return a registry holding ``rules``."""
        registry = cls()
        for rule in rules:
            registry.register(rule)
        return registry

    def register(self, rule: InjectionRule) -> None:
        """Add ``rule``, replacing any rule already held for its integration."""
        self._rules[rule.integration] = rule

    def register_all(self, rules: Iterable[InjectionRule]) -> None:
        """Add every rule in ``rules``."""
        for rule in rules:
            self.register(rule)

    def get(self, integration: str) -> InjectionRule:
        """Return the rule for ``integration``, or raise ``UnknownIntegration``."""
        rule = self._rules.get(integration)
        if rule is None:
            raise UnknownIntegration(integration, known=self.integrations())
        return rule

    def has(self, integration: str) -> bool:
        """Return whether a rule is declared for ``integration``."""
        return integration in self._rules

    def integrations(self) -> tuple[str, ...]:
        """Return every integration with a declared rule, in name order."""
        return tuple(sorted(self._rules))


__all__ = [
    "AUTHORIZATION_HEADER",
    "BasicAuthInjection",
    "BearerTokenInjection",
    "BodyFieldInjection",
    "HeaderInjection",
    "Injection",
    "InjectionRule",
    "InjectionRuleRegistry",
    "PathSegmentInjection",
    "QueryParameterInjection",
    "RequestSigner",
    "SignatureInjection",
]
