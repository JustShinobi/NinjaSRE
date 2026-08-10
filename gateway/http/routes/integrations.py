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

**Writing a credential is the one route on this surface that carries a secret.**
The value goes from the request body to ``Vault.store`` and stops there: it is
not returned, not logged, not put in an audit detail, and not quoted in a
validation failure. Only field *names* travel outward, which is the same line
``SetupOutcome`` holds on the CLI side. There is no route that reads one back,
masked or otherwise — the absence is the guarantee, and a ``GET`` beside this
handler would be the thing that removed it.

Rotation is this route again. Storing supersedes, the vault keeps the previous
version, and the version number in the response plus the audit entry is the
sequence somebody reconstructs six months later.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.credential_schemas import schema_for
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request
from gateway.http.state import GatewayState
from integrations._catalogue.discovery import catalogue
from platform.credentials.errors import CredentialSchemaViolation
from platform.credentials.handles import CredentialHandle
from platform.credentials.health import CredentialHealth
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.identity.audit.recorder import (
    CREDENTIAL_AUDIT_ACTION_WRITE,
    AuditContext,
    AuditRecorder,
)
from platform.observability.logging import get_logger
from platform.persistence.ports.audit_repository import ActorKind

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])

#: What an audit query groups a credential write by. The integration, never the
#: handle: a handle carries the team identifier as well and reads as an internal
#: address, whereas the question people ask the trail is "who changed Datadog's
#: key, and when".
_CREDENTIAL_RESOURCE_KIND = "credential"


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


class CredentialWriteRequest(BaseModel):
    """A flat map of field name to value, checked against the vendor's own schema.

    Flat rather than nested, because a credential is a set of named strings and
    a shape with room for anything else would be a shape a secret could be
    smuggled through under a key nothing validates.
    """

    values: dict[str, str] = Field(default_factory=dict)


class CredentialWriteView(BaseModel):
    """What was written, described without any part of it being readable.

    There is no field here a value could sit in, which is the same argument
    ``CredentialVersion`` makes one layer down: the type is the guarantee rather
    than a rule somebody has to remember when adding a key.
    """

    integration: str
    state: str
    usable: bool
    #: Which version of this credential is now live. One on a first write, and
    #: incrementing on every rotation — this is what makes "the key was changed
    #: at 02:00" answerable from the response as well as from the trail.
    version: int
    #: The field *names* that were supplied, in name order. Never their values.
    fields: list[str]


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


def _team_of(auth: AuthenticatedRequest) -> str:
    """Return the credential-handle team this request writes and reads under.

    An organisation-scoped token has no team, and a handle needs one: the vault
    spells the organisation-wide owner as a literal rather than as an empty
    string, because ``datadog/`` and ``datadog`` would otherwise be two
    spellings of one handle.
    """
    return auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM


@router.post("/{name}/verify", response_model=IntegrationVerification)
async def verify_integration(
    name: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationVerification:
    """Check this team's credential for ``name``: configured, current, decryptable.

    ``name`` is an installed integration or a supported model provider, the same
    two as the write beside it — the guided first run stores a provider key and
    then verifies it, and a verify that only knew about vendor packages would
    refuse the second half of its own flow.
    """
    schemas = CredentialSchemaRegistry.from_schemas(schema_for(name))
    vault = Vault(gateway=state.gateway, schemas=schemas)
    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=_team_of(auth))
    entry = report.entries[0]
    return IntegrationVerification(
        integration=name, state=entry.state.value, usable=entry.state.usable
    )


@router.put("/{name}/credential", response_model=CredentialWriteView)
async def store_credential(
    name: str,
    body: CredentialWriteRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> CredentialWriteView:
    """Store this team's credential for ``name`` and report what it now is.

    ``name`` is an installed integration or a supported model provider. One
    route for both, because a provider key that took a different path would be
    a second place credentials live and the one the audit misses.

    The team is the token's, exactly as it is for every other write on this
    surface: a body field naming somebody else's team would be a permission
    decision taken by the client.

    Raises:
        ApiProblem: nothing answers to ``name`` (404), or the values do not fit
            the declared schema (400). The refusal names the fields and never
            quotes one.
    """
    values = dict(body.values)
    names = sorted(values)

    vault = Vault(
        gateway=state.gateway,
        schemas=CredentialSchemaRegistry.from_schemas(schema_for(name)),
    )
    handle = CredentialHandle(integration=name, team_id=_team_of(auth))
    try:
        stored = await vault.store(auth.scope, handle, values)
    except CredentialSchemaViolation as violation:
        # ``CredentialSchemaViolation`` is written to name fields and never to
        # quote one, so it crosses the boundary as it stands.
        raise bad_request(str(violation)) from violation

    # The actor, the integration, the field names and the version sequence — and
    # no value. A credential replaced at 02:00 during an incident is a fact
    # somebody needs six months later, and the record of it must not be the
    # place the credential survives.
    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=CREDENTIAL_AUDIT_ACTION_WRITE,
        resource_kind=_CREDENTIAL_RESOURCE_KIND,
        resource_id=name,
        detail={"integration": name, "fields": names, "version": stored.version},
    )
    # The field names, never their values. This is the line that gets pasted
    # into a support thread.
    logger.info("gateway.integration_credential_stored", integration=name, fields=names)

    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=_team_of(auth))
    entry = report.entries[0]
    return CredentialWriteView(
        integration=name,
        state=entry.state.value,
        usable=entry.state.usable,
        version=stored.version,
        fields=names,
    )


__all__ = ["router"]
