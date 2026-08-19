"""What to paste into the system that will send the alerts.

Every other part of this feature is inside the deployment. This one is not: the
loop only closes when somebody configures a receiver in their alert router, on
the other side of a boundary NinjaSRE deliberately does not write to — the same
rule that keeps it out of the observability stack. So what it can do is say
exactly what to paste, and this route is that sentence.

**The URL comes from the request.** An operator reading this reached the
deployment at some address, and that is the address that works. A configured
public URL would be a second copy of the same fact, right until somebody put the
deployment behind a different name and forgot this one.

**Nothing here is a secret.** The credential is issued through
``POST /identity/tokens``, shown once, and never read back — the store holds a
hash. This route names the *permission* a delivery token needs so a panel can
ask for the narrow one instead of a personal access token.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from gateway.webhooks.router import PROFILES
from gateway.webhooks.sources import alertmanager
from platform.identity.local_accounts import CREDENTIAL_NAME
from platform.identity.permissions import Permission
from platform.persistence.ports.identity_repository import ApiToken

router = APIRouter(prefix="/v1/ingress", tags=["ingress"])

#: The one source whose vendor speaks a receiver format this deployment knows
#: how to template. Grafana and the generic source take whatever an operator's
#: own tooling already sends; only Alertmanager's `webhook_configs` shape is
#: something this deployment can hand over ready to paste.
_RECEIVER_YAML_SOURCE = "alertmanager"


class IngressSourceView(BaseModel):
    """One receiver an alert router can be pointed at."""

    source: str
    path: str
    #: The absolute address, built from the one this request arrived on.
    url: str
    expects: str
    verification: str
    #: A ready-to-paste `webhook_configs` block, Alertmanager's own source
    #: only, and only once a delivery token exists to name in it. Absent
    #: rather than a block that could not authenticate anything — the same
    #: reading FR-063 gives the trust line: no token means nothing to copy.
    receiver_yaml: str | None = None


class IngressSourceListView(BaseModel):
    sources: list[IngressSourceView] = Field(default_factory=list)
    #: What a delivery credential must be scoped to. Named rather than assumed,
    #: so a panel issuing one asks for the narrow permission by name instead of
    #: handing an alert router a token as wide as the person who created it.
    delivery_permission: str = Permission.WEBHOOK_DELIVER.value


def _delivery_token_name(tokens: Iterable[ApiToken]) -> str:
    """Return the name of the delivery token this deployment's receivers use.

    Mirrors the console's own selection (``alert-intake.tsx``'s
    ``deliveryTokenNamed``): the console-sign-in pseudo-token is never a
    delivery credential — it stands in for a whole session, not one declared
    purpose — a revoked token cannot authenticate anything, and among what is
    left the most recently issued one is the one actually in use. An operator
    who issued a second token stopped pasting the first; naming an older one
    here would send an operator to rotate a credential nothing still reads.
    """
    candidates = [
        token
        for token in tokens
        if token.name != CREDENTIAL_NAME
        and not token.is_revoked
        and Permission.WEBHOOK_DELIVER.value in token.scopes
    ]
    if not candidates:
        return ""
    newest = max(candidates, key=lambda token: token.created_at or datetime.min.replace(tzinfo=UTC))
    return newest.name


@router.get("/sources", response_model=IngressSourceListView)
async def list_ingress_sources(
    request: Request,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IngressSourceListView:
    """Return every receiver this deployment serves, with its address and its body."""
    base = str(request.base_url).rstrip("/")
    async with state.gateway.begin(auth.scope) as uow:
        tokens = await uow.identity.list_tokens()
    token_name = _delivery_token_name(tokens)

    sources: list[IngressSourceView] = []
    for name, profile in sorted(PROFILES.items()):
        url = f"{base}/webhooks/{name}"
        sources.append(
            IngressSourceView(
                source=name,
                path=f"/webhooks/{name}",
                url=url,
                expects=profile.expects,
                verification=profile.verification,
                receiver_yaml=(
                    alertmanager.receiver_yaml(url=url, token_name=token_name)
                    if name == _RECEIVER_YAML_SOURCE and token_name
                    else None
                ),
            )
        )
    return IngressSourceListView(sources=sources)


__all__ = ["IngressSourceListView", "IngressSourceView", "router"]
