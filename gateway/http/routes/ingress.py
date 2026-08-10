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

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gateway.http.deps import authorized, get_state
from gateway.webhooks.router import PROFILES
from platform.identity.permissions import Permission

router = APIRouter(prefix="/v1/ingress", tags=["ingress"])


class IngressSourceView(BaseModel):
    """One receiver an alert router can be pointed at."""

    source: str
    path: str
    #: The absolute address, built from the one this request arrived on.
    url: str
    expects: str
    verification: str


class IngressSourceListView(BaseModel):
    sources: list[IngressSourceView] = Field(default_factory=list)
    #: What a delivery credential must be scoped to. Named rather than assumed,
    #: so a panel issuing one asks for the narrow permission by name instead of
    #: handing an alert router a token as wide as the person who created it.
    delivery_permission: str = Permission.WEBHOOK_DELIVER.value


@router.get("/sources", response_model=IngressSourceListView, dependencies=[Depends(get_state)])
async def list_ingress_sources(
    request: Request,
    _auth: object = Depends(authorized),
) -> IngressSourceListView:
    """Return every receiver this deployment serves, with its address and its body."""
    base = str(request.base_url).rstrip("/")
    return IngressSourceListView(
        sources=[
            IngressSourceView(
                source=name,
                path=f"/webhooks/{name}",
                url=f"{base}/webhooks/{name}",
                expects=profile.expects,
                verification=profile.verification,
            )
            for name, profile in sorted(PROFILES.items())
        ]
    )


__all__ = ["IngressSourceListView", "IngressSourceView", "router"]
