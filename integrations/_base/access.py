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

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from integrations._base.client import IntegrationClient
from integrations._base.transport import ProxyTransport, RequestContext


@dataclass(frozen=True, slots=True)
class IntegrationAccess:
    """The transport and the tenant one process makes vendor calls for."""

    transport: ProxyTransport
    org_id: str
    team_id: str

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
        """
        return factory(transport=self.transport, context=self.context(capability), **options)


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


__all__ = [
    "IntegrationAccess",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
