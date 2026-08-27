"""Binding the system a remediation actually changes, from what the operator configured.

Everything a write needs has existed for some time: the port, the thirteen
declared hypervisor actions with their risk table and preconditions, the plane
that performs them, the gate in front, the approval routes, and the three tables
behind. **Nothing bound the port.** A sweep for a call to ``bind`` returned tests
and nothing else, so ``control_plane.current()`` was ``None`` in every deployment
there has ever been.

That single absence is load-bearing all the way down. ``unmet_for_remediation``
names a missing control plane, so ``compose_remediation`` composes no desk and
logs what is missing; with no desk the request builder reads a snapshot it
declares unreadable, the plan factory derives no undo, and the call is refused
for want of a plan. **No approval is ever queued.** A deployment in that state
reports "nothing was proposed", which reads exactly like a policy decision and
is not one.

**Binding is explicit and there is no fallback.** A cluster that is not
configured, is switched off, is pointed nowhere, or has no credential proxy to
reach binds nothing, and the line says which. Binding a plane that cannot answer
would move the failure from composition — where it is one log line an operator
can read — to the middle of an incident.

**Binding does not authorise anything.** What it makes possible is a *proposal*:
the gate in front still resolves this deployment's posture at the moment a write
is decided, the approval is stored pending, and execution is a second entry
through a route a person presses. Nothing here shortens that path, and the
propose-only default is unchanged by binding.

**Nothing here holds a credential and nothing here can.** The write client
reaches the cluster through the credential proxy like every other authenticated
call, which is why this is composed with a proxy address rather than with a
token, and why a deployment without a proxy binds nothing rather than building a
client that would have to hold one itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.proxmox import DECLARATIONS, ProxmoxControlPlane
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.discovery_sources import _active_integrations, _endpoints
from integrations._base.transport import HttpProxyTransport, RequestContext
from integrations.proxmox.writes import ProxmoxWriteClient
from platform.config_service.schema.integrations import CertificateTrustSettings
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the proxy is told is asking when a write is proposed or carried out. Its
#: own name rather than the sweep's, so an audit line answers "which half of the
#: product used this credential" without anybody correlating timestamps.
REMEDIATION_CAPABILITY = "remediation.control_plane"

#: The integrations this deployment knows how to change, by name. A row rather
#: than a branch, for the reason the discovery sources give: a second vendor is
#: a line here and not a fork below.
_PLANES: Mapping[str, Any] = {"proxmox": (ProxmoxWriteClient, ProxmoxControlPlane)}


async def compose_control_plane(state: Any, *, org_id: str, proxy_url: str) -> Any | None:
    """Bind the control plane this deployment's configuration describes.

    Returns what was bound so a caller can log it. ``None`` is a working
    deployment that cannot act: it proposes nothing above a sensitive read, and
    the line below names the piece that would change that.
    """
    if not proxy_url:
        # A control plane reaches its vendor through the proxy and never around
        # it, so a deployment without one binds nothing rather than a client
        # that would have to hold a credential itself.
        logger.info("remediation.control_plane_skipped", reason="no credential proxy is configured")
        control_plane.clear()
        return None

    try:
        entries = await _active_integrations(state, org_id)
    except Exception as unreadable:  # noqa: BLE001 — an unread posture is never permission
        # Unreadable is not permission. The process still comes up, because the
        # console somebody would fix it from is served by it.
        logger.warning("remediation.control_plane_unreadable", error=str(unreadable))
        control_plane.clear()
        return None

    transport = HttpProxyTransport(base_url=proxy_url)
    # The organisation's own handle, not an empty team, for the reason the sweep
    # gives: the credential a team-less token wrote went to the organisation-wide
    # handle, and asking for "" would build a handle the grammar refuses.
    context = RequestContext(
        org_id=org_id, team_id=CREDENTIAL_ORG_WIDE_TEAM, capability=REMEDIATION_CAPABILITY
    )

    for entry in entries:
        name = str(entry.get("name", ""))
        builders = _PLANES.get(name)
        if builders is None:
            continue
        if not bool(entry.get("enabled", True)):
            logger.info("remediation.control_plane_disabled", integration=name)
            continue
        endpoints = _endpoints(str(entry.get("base_url", "")))
        if not endpoints:
            logger.warning("remediation.control_plane_unaddressed", integration=name)
            continue
        client_type, plane_type = builders
        bound = plane_type(
            client=client_type(
                transport=transport,
                context=context,
                endpoints=endpoints,
                trust=_trust_of(entry),
            ),
            declarations=DECLARATIONS,
        )
        control_plane.bind(bound)
        logger.info(
            "remediation.control_plane_bound",
            integration=name,
            # The address, deliberately, and the trust form. Neither is a
            # secret, and an operator reading a log to find out what this
            # deployment can act on should find the answer rather than a
            # redaction.
            endpoints=sorted(endpoints),
            trust=_trust_of(entry).anchor.value,
            capabilities=len(DECLARATIONS),
        )
        return bound

    control_plane.clear()
    logger.info(
        "remediation.control_plane_skipped",
        reason="no configured integration is one this deployment knows how to change",
    )
    return None


def _trust_of(entry: Mapping[str, Any]) -> Any:
    """Return what this entry accepts from its endpoint's certificate.

    Read from the same document the address came from, so a report reads back
    what the deployment actually accepts rather than the package default. The
    decision is applied at the proxy's egress and never here — nothing in this
    module opens a socket.
    """
    declared = entry.get("trust")
    section = (
        CertificateTrustSettings.model_validate(declared)
        if isinstance(declared, Mapping)
        else CertificateTrustSettings()
    )
    return section.declaration(str(entry.get("base_url", "")))


__all__ = ["REMEDIATION_CAPABILITY", "compose_control_plane"]
