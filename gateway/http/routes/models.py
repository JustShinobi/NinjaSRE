"""What each role actually runs on, said by the deployment that runs it.

Nothing served this, so the console derived it — and the derivation was wrong in
the one way that costs an afternoon. It read the *schema's* default for a role
nobody had bound, which is a value in a Pydantic field and not a decision
anybody made, and printed ``anthropic / claude-sonnet-5`` over a deployment
whose every call went to Gemini. A panel that names a model no call will ever
reach is worse than a panel that says nothing, because it is read and believed.

The rule is one function, :func:`core.llm.factory.resolve_binding`, and its
answer has three shapes rather than two: somebody chose this for this role, this
role follows the investigator, or nothing is configured anywhere. A caller
holding only a provider string cannot tell them apart — which is exactly why the
console guessed — so the shape is on the wire.

**No node in the address, deliberately.** A model binding is published once, at
boot, from the root of the configuration tree; nothing republishes it per team.
An endpoint that accepted a node would promise a per-team answer the runtime
does not honour, which is the same divergence between screen and behaviour that
this route exists to close.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config.constants.config_service import MODEL_ROLES
from core.llm.factory import resolve_binding
from gateway.http.deps import authorized

router = APIRouter(prefix="/v1/models", tags=["models"])


class RoleBindingView(BaseModel):
    role: str
    provider: str
    model: str
    #: ``configured``, ``investigator`` or ``default``. See
    #: ``core.llm.factory``, which declares the three and is what decides them.
    source: str


class RoleBindings(BaseModel):
    roles: list[RoleBindingView]


@router.get("/roles", response_model=RoleBindings, dependencies=[Depends(authorized)])
async def model_roles() -> RoleBindings:
    """Return what every declared role resolves to, and on whose say-so."""
    return RoleBindings(
        roles=[
            RoleBindingView(
                role=role,
                provider=binding.provider_id,
                model=binding.model_id,
                source=binding.source,
            )
            for role in MODEL_ROLES
            for binding in (resolve_binding(role),)
        ]
    )


__all__ = ["router"]
