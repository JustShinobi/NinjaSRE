"""Recording a refused connection, with enough context to act on it.

A blocked egress attempt is audited with its target, its
capability, and its investigation. All three matter and none is optional:

- **the target** is what the operator adds to an integration's declared hosts if
  the refusal was wrong,
- **the capability** is which tool asked, which is the difference between "our
  Datadog client moved region" and "something read a URL out of a log line",
- **the investigation** is what ties it to everything else that run did.

Two things observe a refusal and neither is the capability's own process. The
credential proxy refuses a host outside the integration's allow-list before it
touches the vault; the Envoy sidecar refuses one outside the sandbox's, and
answers with a 403 naming the allow-list rather than a reset, so the capability
gets a message it can report rather than a timeout it cannot explain.

This module is where either of them lands it, and the function returns the error
rather than raising it — the caller decides whether a refusal ends the tool call
or is reported to the model as a value, and that decision belongs one tier up.
"""

from __future__ import annotations

from platform.observability.logging import get_logger
from platform.sandbox.errors import SandboxEgressDenied
from platform.sandbox.port import SandboxInstance
from platform.sandbox.spec import EgressPolicy
from platform.sandbox.trace import SandboxEvent, SandboxEventKind, SandboxEventSink

_logger = get_logger(__name__)


async def record_blocked_egress(
    events: SandboxEventSink,
    *,
    instance: SandboxInstance,
    policy: EgressPolicy,
    host: str,
    capability: str = "",
) -> SandboxEgressDenied:
    """Audit a refused connection and return the error describing it.

    Returns rather than raises. A refusal is sometimes the end of a tool call
    and sometimes a classified result the model should see and route around, and
    a function that raised would take that choice away from the layer that has
    it.
    """
    await events.record(
        SandboxEvent(
            kind=SandboxEventKind.EGRESS_DENIED,
            sandbox_id=instance.sandbox_id,
            profile=instance.profile,
            org_id=instance.org_id,
            team_id=instance.team_id,
            investigation_id=instance.investigation_id,
            capability=capability,
            host=host,
        )
    )
    _logger.warning(
        "sandbox.egress.blocked",
        sandbox_id=instance.sandbox_id,
        investigation_id=instance.investigation_id,
        capability=capability,
        host=host,
    )
    return SandboxEgressDenied(host, sandbox_id=instance.sandbox_id, allowed=policy.reachable())


__all__ = ["record_blocked_egress"]
