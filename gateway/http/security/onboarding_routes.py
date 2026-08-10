"""The routes an operator's first run needs, and what each one takes.

Three decisions are recorded here rather than in a review nobody scheduled.

**The credential write takes ``credential.write``, not ``config.write``.** They
are held by the same roles today, which is not the point: whoever may adjust a
masking threshold is not automatically whoever may replace the API token a
cluster is reached with, and a deployment narrowing one must not silently narrow
the other. There is no separate rotation verb — writing again supersedes — so
this one row covers onboarding and rotation both, and the audit trail carries
the sequence.

**Reading the provider inventory takes ``config.read``.** It reveals no value:
what comes back is which providers this build supports, which fields each needs,
and whether one is configured and verified. That is the same class of fact
``/v1/setup/checklist`` serves, and requiring more would put the provider list
out of reach of the credential a first run is holding.

**Verifying a provider takes ``integration.manage``.** It is a real call against
the operator's own endpoint and it spends their tokens, so it is a managed
action rather than a read — the same reason it is a ``POST`` and the same reason
the self-check does not run it by default.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

ONBOARDING_ROUTES: Final[tuple[Route, ...]] = (
    # --- Putting a credential into the vault -----------------------------------
    Route(
        method="PUT",
        path="/v1/integrations/{name}/credential",
        permission=Permission.CREDENTIAL_WRITE,
    ),
    # --- The providers this deployment can be pointed at -------------------------
    Route(method="GET", path="/v1/providers", permission=Permission.CONFIG_READ),
    Route(method="GET", path="/v1/providers/{provider_id}", permission=Permission.CONFIG_READ),
    Route(
        method="POST",
        path="/v1/providers/{provider_id}/verify",
        permission=Permission.INTEGRATION_MANAGE,
    ),
)

__all__ = ["ONBOARDING_ROUTES"]
