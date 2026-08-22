"""Wiring the verifier that actually calls the vendor.

``GatewayState.deep_verifier`` is the seam between a console button and an
integration's own verification runner, and nothing had ever filled it. The field
defaulted to ``None``, no composition root assigned it, and so
``POST /v1/integrations/{name}/verify/report`` — the one route that reaches the
vendor and reports which of the declared permissions the credential actually
has — answered 404 on every deployment there has ever been.

The consequence was worse than a missing feature. The catalogue is careful to
report ``unknown`` rather than ``healthy`` for an integration nothing has run
against; then the single control that would turn ``unknown`` into a measurement
did nothing, so every integration an operator connected stayed ``unknown`` for
ever — and ``unknown`` is exactly what they connected it to find out.

**Composed here rather than in ``build_deployment``.** The verifier needs the
process's vendor binding, and that is read from the configuration tree, which
means it exists only after the store has answered. ``build_deployment`` is
synchronous and knows only the environment.

**The binding is re-read per call, never captured, and read from the one place
the verifiers read it.** ``refresh_integration_endpoints`` rebinds a new frozen
``IntegrationAccess`` every time an address is written, so a closure holding the
binding it was composed with would faithfully test the address an operator had
just corrected away from. It is ``integrations._base.access.current()`` rather
than the copy on ``GatewayState`` because that is where a verifier resolves the
configured address from — two sources for one fact is how a report ends up
addressed to one host and attributed to another.

**The team travels with the request.** A credential resolves team-first and
falls back to the organisation, never the other way round. A verify that always
asked as the organisation would report a team's perfectly good credential
missing, which is the same class of false negative this route exists to remove.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from integrations._base import access
from integrations._base.transport import RequestContext
from integrations._catalogue.discovery import catalogue
from integrations._verification.framework import VerificationRunner, runner_for
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the proxy is told is asking, so a forwarded verification call is
#: attributable in the audit trail rather than appearing as an anonymous read.
VERIFY_CAPABILITY = "integration.verify"


def compose_deep_verifier(state: Any) -> None:
    """Install the callable ``verify/report`` runs, or leave none and say why.

    Leaves ``deep_verifier`` as ``None`` for a deployment with no vendor binding,
    because that deployment has no credential proxy — and the route's refusal
    already says exactly that, which is a better answer than a report built over
    a transport that cannot reach anything.
    """
    if access.current() is None:
        logger.info("integrations.deep_verify_skipped", reason="no vendor binding is composed")
        return

    # Built once. The runner holds the packages' verifiers, which are singletons
    # declared at import; what varies per call is the transport, the tenant and
    # the address, and all three travel in the arguments below.
    runner: VerificationRunner = runner_for([entry.descriptor for entry in catalogue()])

    async def verify(name: str, team_id: str) -> Mapping[str, Any] | None:
        bound = access.current()
        if bound is None:
            return None
        context = RequestContext(
            org_id=bound.org_id,
            team_id=team_id or bound.team_id,
            capability=VERIFY_CAPABILITY,
        )
        try:
            report = await runner.verify(name, transport=bound.transport, context=context)
        except LookupError:
            # Not an error. A vendor with no verifier is a fact about the
            # catalogue, and the route says so in different words from the ones
            # it uses for a deployment that composed nothing.
            return None
        return report.to_record()

    state.deep_verifier = verify
    logger.info("integrations.deep_verify_composed", integrations=list(runner.names()))


__all__ = ["VERIFY_CAPABILITY", "compose_deep_verifier"]
