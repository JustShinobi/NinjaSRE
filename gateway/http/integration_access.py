"""Binding the one thing every vendor tool in the catalogue needs.

``integrations/_base/access.py`` states the arrangement plainly: one binding per
process, set by whoever composes the deployment, and a tool either has it or
reports itself unavailable by name. Nothing set it. ``IntegrationAccess`` was
referenced only inside its own module, while a hundred and ninety-three vendor
tool modules read ``current()`` to make their calls — so all of them reported
themselves unavailable, on every deployment, always.

**One binding, at the root.** A tool that built its own client from ambient
configuration would be one lookup away from acting on somebody else's estate,
which is the reason the module refuses to let it.

**Nothing here holds a credential.** The binding carries a transport and two
tenant identifiers, all three safe in a prompt. The proxy on the far side of the
transport is what turns them into an authenticated request.

**No proxy means no binding.** A vendor call goes through the proxy and never
around it, so a deployment without one has nothing to bind — and its tools say
so by name rather than answering as though the vendor had nothing to report.

**The binding carries where each vendor is.** An integration ships a placeholder
host, because nobody packaging one knows where your cluster is, and the operator
declares the real address in the configuration tree. Reading it here is what
turns that declaration into the address a client actually uses; without it a
deployment could configure an Alertmanager completely and still have every call
addressed to ``alertmanager.example.com``. It is re-read whenever an address is
written, so a change takes effect on the next call rather than the next restart.
"""

from __future__ import annotations

from typing import Any

from gateway.http.credential_handles import resolve_process_credential_team
from gateway.http.integration_endpoints import configured_endpoints
from integrations._base import access
from integrations._base.access import IntegrationAccess
from integrations._base.transport import HttpProxyTransport
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)


async def compose_integration_access(
    state: Any, *, org_id: str, proxy_url: str
) -> IntegrationAccess | None:
    """Bind this process's vendor access, or bind nothing and say why.

    The team is the one that holds a credential for something in the
    catalogue, discovered from the vault (``resolve_process_credential_team``)
    rather than assumed to be the organisation's. A tool called by an
    investigation acts for the deployment and has no caller of its own to ask,
    which is exactly the shape that function exists for; the organisation-wide
    handle is still where it lands when nobody holds anything by team, or when
    more than one team does — never a handle the grammar would refuse.
    """
    if not proxy_url.strip():
        logger.info("integrations.access_skipped", reason="no credential proxy is configured")
        access.bind(None)
        return None

    resolved = await resolve_process_credential_team(state.gateway, TenantScope(org_id=org_id))
    if resolved.is_ambiguous:
        logger.warning(
            "integrations.access_team_ambiguous",
            org_id=org_id,
            teams=list(resolved.ambiguous_teams),
        )

    bound = IntegrationAccess(
        transport=HttpProxyTransport(base_url=proxy_url.strip()),
        org_id=org_id,
        team_id=resolved.team_id,
        endpoints=await _endpoints(state, org_id=org_id),
    )
    access.bind(bound)
    state.integration_access = bound
    logger.info(
        "integrations.access_composed",
        org_id=org_id,
        team_id=bound.team_id,
        endpoints=sorted(bound.endpoints),
    )
    return bound


async def _endpoints(state: Any, *, org_id: str) -> dict[str, str]:
    """Return the configured addresses, or none and a line saying why.

    A deployment whose configuration cannot be read still makes calls: every
    integration falls back to the region its own package ships, which is exactly
    the behaviour before addresses were configurable. Refusing to bind over an
    unreadable document would take the whole catalogue offline for a fact that
    is empty on most deployments anyway.
    """
    try:
        return await configured_endpoints(
            state.gateway, scope=TenantScope(org_id=org_id), node_id=org_id
        )
    except Exception as unreadable:  # noqa: BLE001 — the catalogue must still work
        logger.warning("integrations.endpoints_unreadable", error=str(unreadable))
        return {}


async def refresh_integration_endpoints(state: Any, *, org_id: str) -> None:
    """Re-read the configured addresses into this process's binding.

    Called after an address is written, so that an operator who corrects a typo
    and presses test does not have to know that the answer they get is about the
    address they replaced. A deployment with no binding has nothing to refresh,
    which is the ordinary case for a process composed without a proxy.
    """
    bound = access.current()
    if bound is None:
        return
    refreshed = bound.with_endpoints(await _endpoints(state, org_id=org_id))
    access.bind(refreshed)
    state.integration_access = refreshed
    logger.info("integrations.endpoints_refreshed", endpoints=sorted(refreshed.endpoints))


__all__ = ["compose_integration_access", "refresh_integration_endpoints"]
