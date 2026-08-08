"""The routes an operator meets before the deployment is finished, and what they take.

The permissions here are deliberately the *narrowest* that still let a first run
happen, because the credential a first run is holding is the narrowest this
platform issues: two permissions, one of which is only there so it can ask who
it is.

``/v1/setup/checklist`` therefore takes ``investigation.read`` rather than
``config.read``. It reveals no configuration value — only whether each step has
been done — and requiring ``config.read`` would mean the bootstrap credential
could not see the checklist that tells it what to do next, which is the exact
dead end this feature exists to remove.

The self-check is the opposite call. Its findings name settings and quote
dependency errors, so it takes ``config.read``: an operator who may not see the
configuration may not see a report about it either.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

FIRST_RUN_ROUTES: Final[tuple[Route, ...]] = (
    # --- What is left to do ----------------------------------------------------
    Route(method="GET", path="/v1/setup/checklist", permission=Permission.INVESTIGATION_READ),
    # Exchanging the bootstrap credential *is* minting a token, which is exactly
    # the one permission the bootstrap credential carries for the purpose.
    Route(
        method="POST",
        path="/v1/setup/durable-credential",
        permission=Permission.TOKEN_MANAGE,
    ),
    # --- What is wrong ----------------------------------------------------------
    Route(method="GET", path="/v1/setup/self-check", permission=Permission.CONFIG_READ),
    Route(method="GET", path="/v1/setup/diagnostics", permission=Permission.CONFIG_READ),
    Route(method="GET", path="/v1/setup/support-bundle", permission=Permission.CONFIG_READ),
    # --- The demonstration -------------------------------------------------------
    # Seeding writes a tenant's worth of records and removing one deletes a
    # tenant. Both are organisation-level changes and neither is a configuration
    # edit, so ``org.manage`` is the honest permission rather than the convenient
    # one.
    Route(method="POST", path="/v1/setup/demo", permission=Permission.ORG_MANAGE),
    Route(method="DELETE", path="/v1/setup/demo", permission=Permission.ORG_MANAGE),
)

__all__ = ["FIRST_RUN_ROUTES"]
