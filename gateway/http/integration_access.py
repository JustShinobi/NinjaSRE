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
"""

from __future__ import annotations

from typing import Any

from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from integrations._base import access
from integrations._base.access import IntegrationAccess
from integrations._base.transport import HttpProxyTransport
from platform.observability.logging import get_logger

logger = get_logger(__name__)


async def compose_integration_access(
    state: Any, *, org_id: str, proxy_url: str
) -> IntegrationAccess | None:
    """Bind this process's vendor access, or bind nothing and say why.

    The organisation's own handle rather than a team's: a tool called by an
    investigation acts for the deployment, and the credential a team-less token
    wrote went to the organisation-wide handle. Asking for a blank team would
    build a handle the grammar refuses and be turned away at the proxy.
    """
    if not proxy_url.strip():
        logger.info("integrations.access_skipped", reason="no credential proxy is configured")
        access.bind(None)
        return None

    bound = IntegrationAccess(
        transport=HttpProxyTransport(base_url=proxy_url.strip()),
        org_id=org_id,
        team_id=CREDENTIAL_ORG_WIDE_TEAM,
    )
    access.bind(bound)
    state.integration_access = bound
    logger.info("integrations.access_composed", org_id=org_id)
    return bound


__all__ = ["compose_integration_access"]
