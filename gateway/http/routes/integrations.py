"""Integrations: the catalogue, and one team's credential state for an integration.

The listing is the catalogue (FR-022): category, capabilities, required
credentials, required permissions, regions, health, and parity status, per
vendor. It is deliberately more than a name and a host list, because the two
questions a console actually gets asked are "what can this deployment look at"
and "which of it is currently working", and neither is answerable from a name.

Health is what the scheduled live runs recorded. An integration nothing has run
against reports ``unknown`` rather than ``healthy`` — a vendor whose API broke
and a vendor nobody has checked are different facts, and collapsing them is the
same failure as reporting a truncated answer as a complete one.

"Verify" checks the credential this team has configured is present, current, and
decryptable — the same three facts ``platform/credentials/health.py`` reports to
an operator's diagnostics. The end-to-end vendor call, with its permission
probes, is the verification runner's job and runs from the CLI and from CI,
where a live call is expected rather than surprising.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.state import GatewayState
from integrations._catalogue.discovery import catalogue
from integrations.registry import discover
from platform.credentials.health import CredentialHealth
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


class IntegrationView(BaseModel):
    name: str
    category: str
    summary: str
    hosts: list[str]
    regions: list[str]
    capabilities: list[str]
    required_credentials: list[str]
    required_permissions: list[str]
    health: str
    health_detail: str
    parity: str
    missing_artefacts: list[str]


class IntegrationList(BaseModel):
    integrations: list[IntegrationView]


class IntegrationVerification(BaseModel):
    integration: str
    state: str
    usable: bool


@router.get("", response_model=IntegrationList)
async def list_integrations(
    state: GatewayState = Depends(get_state),
) -> IntegrationList:
    """Return the catalogue: every installed integration and what is known about it."""
    ledger = getattr(state, "integration_health", None)
    return IntegrationList(
        integrations=[
            IntegrationView(
                name=entry.name,
                category=entry.category.value,
                summary=entry.summary,
                hosts=list(entry.descriptor.rule.hosts),
                regions=list(entry.regions),
                capabilities=list(entry.capabilities),
                required_credentials=list(entry.required_credentials),
                required_permissions=list(entry.required_permissions),
                health=entry.health.value,
                health_detail=entry.health_detail,
                parity=entry.parity.status.value,
                missing_artefacts=[artefact.value for artefact in entry.parity.missing],
            )
            for entry in catalogue(health=ledger)
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
