"""Integrations: list what is installed, verify one team's credential for it.

"Verify" checks the credential this team has configured is present, current,
and decryptable — the same three facts ``platform/credentials/health.py``
reports to an operator's diagnostics. A live call to the vendor is each
integration client's own concern and is not repeated here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.state import GatewayState
from integrations.registry import discover
from platform.credentials.health import CredentialHealth
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


class IntegrationView(BaseModel):
    name: str
    hosts: list[str]


class IntegrationList(BaseModel):
    integrations: list[IntegrationView]


class IntegrationVerification(BaseModel):
    integration: str
    state: str
    usable: bool


@router.get("", response_model=IntegrationList)
async def list_integrations() -> IntegrationList:
    """Return every installed integration."""
    descriptors = discover()
    return IntegrationList(
        integrations=[
            IntegrationView(name=name, hosts=list(descriptor.rule.hosts))
            for name, descriptor in sorted(descriptors.items())
        ]
    )


@router.post("/{name}/verify", response_model=IntegrationVerification)
async def verify_integration(
    name: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationVerification:
    """Check this team's credential for ``name``: configured, current, decryptable."""
    descriptors = discover()
    descriptor = descriptors.get(name)
    if descriptor is None:
        raise not_found(f"no installed integration named {name!r}")

    schemas = CredentialSchemaRegistry.from_schemas(descriptor.schema)
    vault = Vault(gateway=state.gateway, schemas=schemas)
    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=auth.team_node_id)
    entry = report.entries[0]
    return IntegrationVerification(
        integration=name, state=entry.state.value, usable=entry.state.usable
    )


__all__ = ["router"]
