"""How a vendor's tools get a client, without any of them knowing how.

A capability in ``integrations/<vendor>/tools/`` needs three things to make a
call: the proxy transport, the tenant and team the call is for, and its own name
so the audit record says which capability spent the credential. None of those is
knowable from inside the tool, and all three are the same for every tool in the
process.

The obvious alternative is for each tool to construct its own client from
ambient configuration, and it is the wrong one for the same reason the
remediation control plane refuses it: a tool that builds its own client is one
lookup away from acting on somebody else's estate, and "it worked in
development" is how that ships.

So there is one binding per process, set by whoever composes the deployment, and
a tool either has it or reports itself unavailable **by name**. Unavailable is a
first-class outcome here rather than an empty result, because "nothing was
configured" and "the vendor had nothing to say" send an investigation to
completely different places — and only one of them is something an operator can
fix.

Nothing here holds a credential, and there is nowhere for one to be: the binding
carries a transport and two tenant identifiers, all three safe in a prompt, and
the proxy on the far side of the transport is what turns them into an
authenticated request.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from integrations._base.client import IntegrationClient
from integrations._base.transport import ProxyTransport, RequestContext


@dataclass(frozen=True, slots=True)
class IntegrationAccess:
    """The transport, the tenant, and where each vendor is, for one process."""

    transport: ProxyTransport
    org_id: str
    team_id: str
    #: Where each integration answers, by integration name — the addresses the
    #: operator declared, read from the configuration tree the proxy builds its
    #: egress allow-list from. Empty is ordinary: an integration with no entry
    #: here is built against the region its own package ships, which is a
    #: documentation placeholder for anything self-hosted.
    #:
    #: It belongs on the binding rather than in each tool because a tool that
    #: resolved its own configuration is a tool one lookup away from acting on
    #: somebody else's estate — the same argument the module makes above for the
    #: transport and the tenant, applied to the third thing a call needs.
    endpoints: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.org_id.strip() or not self.team_id.strip():
            raise ValueError(
                "an access binding needs an organisation and a team: the proxy resolves a "
                "credential per tenant, and a blank one would resolve to nothing"
            )

    def context(self, capability: str) -> RequestContext:
        """Return the request context a call made by ``capability`` carries."""
        return RequestContext(org_id=self.org_id, team_id=self.team_id, capability=capability)

    def client[Client: IntegrationClient](
        self,
        factory: Callable[..., Client],
        *,
        capability: str,
        **options: Any,
    ) -> Client:
        """Return a client of ``factory``'s type, wired to this process's proxy.

        ``options`` is the vendor's own non-secret configuration — a site, a
        region, a namespace. There is deliberately no way to pass a credential:
        the factory is an ``IntegrationClient`` subclass, and none of those has a
        parameter one could arrive through.

        The configured address is applied here, so that adding one is a change
        to this method rather than to every tool module in the catalogue. A
        caller that names ``base_url`` itself wins — that is the verifier
        probing an address the operator has just typed and not yet stored, and
        overriding it would make "test this" test something else.
        """
        configured = self.endpoints.get(getattr(factory, "integration", ""), "")
        if configured and "base_url" not in options:
            options = {**options, "base_url": configured}
        return factory(transport=self.transport, context=self.context(capability), **options)

    def with_endpoints(self, endpoints: Mapping[str, str]) -> IntegrationAccess:
        """Return this binding pointed at ``endpoints`` instead.

        A new binding rather than a mutation, because the type is frozen for the
        same reason the arrangement is one-per-process: whoever composed the
        deployment decides what a call is made with, and a caller that could
        edit it in place would be a caller that could redirect somebody else's
        in-flight investigation.
        """
        return IntegrationAccess(
            transport=self.transport,
            org_id=self.org_id,
            team_id=self.team_id,
            endpoints=dict(endpoints),
        )


_BOUND: IntegrationAccess | None = None


def bind(access: IntegrationAccess | None) -> IntegrationAccess | None:
    """Bind ``access`` for this process and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = access
    return previous


def restore(previous: IntegrationAccess | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind, so every integration capability reports itself unavailable."""
    restore(None)


def current() -> IntegrationAccess | None:
    """Return this process's binding, or ``None`` when nothing composed one."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (f"{_BOUND.org_id}/{_BOUND.team_id}",)


def configured_base_url(integration: str) -> str:
    """Return where the operator said ``integration`` is, or "" if nowhere.

    The same lookup ``IntegrationAccess.client`` makes, exposed for the one
    caller that cannot go through it: a verifier constructs its client itself,
    because it is a singleton built at import time and the client it needs
    varies per probe. Left to itself it would address the placeholder host its
    package ships, and report a documentation host unreachable to an operator
    who has configured their own.

    Empty rather than an exception for a deployment that has composed no
    binding at all — a verifier run from the CLI against a package's own region
    is a legitimate thing to do, and it is what the empty string produces.
    """
    bound = _BOUND
    return "" if bound is None else bound.endpoints.get(integration, "")


__all__ = [
    "IntegrationAccess",
    "bind",
    "bound_names",
    "clear",
    "configured_base_url",
    "current",
    "restore",
]
