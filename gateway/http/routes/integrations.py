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

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.llm import SUPPORTED_PROVIDERS
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.configured import configured_integrations
from gateway.http.credential_schemas import schema_for
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.state import GatewayState
from gateway.http.verifications import forget_check, integration_health, record_check
from integrations._catalogue.discovery import catalogue
from integrations._catalogue.gaps import gaps
from platform.credentials.errors import CredentialSchemaViolation
from platform.credentials.handles import CredentialHandle
from platform.credentials.health import (
    CredentialHealth,
    CredentialHealthState,
    IntegrationCredentialHealth,
)
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.estate.service import EstateService
from platform.estate.suggestions import Suggestion, suggest_integrations
from platform.identity.audit.recorder import (
    CREDENTIAL_AUDIT_ACTION_WRITE,
    AuditContext,
    AuditRecorder,
)
from platform.observability.logging import get_logger
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.estate_repository import EstateQuery
from platform.persistence.ports.verification_ledger import VerificationSubject

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])

#: What an audit query groups a credential write by. The integration, never the
#: handle: a handle carries the team identifier as well and reads as an internal
#: address, whereas the question people ask the trail is "who changed Datadog's
#: key, and when".
_CREDENTIAL_RESOURCE_KIND = "credential"

#: How much of the estate the suggestion pass reads. A homelab's whole estate
#: fits inside it; past that, a suggestion nobody scrolled to was not worth a
#: second page of a listing that renders on every visit to the catalogue.
MAX_ESTATE_SCAN = 500


class SuggestionView(BaseModel):
    """Where this deployment already found this vendor running.

    Present only where the estate makes it obvious, which is the whole design:
    a suggestion that had to be guessed is one an operator has to verify, and
    then the alphabet would have been cheaper.
    """

    address: str
    from_resource: str
    because: str
    #: The resource's own display name, empty when the estate never resolved
    #: one. A console names the resource from this field rather than
    #: ``from_resource``, and it never falls back to the raw id the way
    #: ``because`` does.
    resource_label: str
    #: The resource's own kind, always present.
    resource_kind: str


class KnownGapView(BaseModel):
    """A vendor this catalogue does not cover, and why it does not.

    ``cause`` separates "the architecture cannot reach this" from "this was
    weighed and decided against". Collapsing them would turn a decision somebody
    can reopen into a limitation nobody can.
    """

    integration: str
    display_name: str
    category: str
    cause: str
    reason: str
    resolution: str


class CredentialFieldView(BaseModel):
    """One credential field, exactly as a form renders it.

    Replaces the bare list of field names this route used to serve. A name
    alone left the console inventing a label and leaving "where do I get this"
    and "what permission does it need" unanswered; this is the vendor's own
    declaration (``platform.credentials.schemas.CredentialField``), read
    through the gateway rather than copied by the console.
    """

    name: str
    label: str
    secret: bool
    required: bool
    help: str
    min_scope: str = ""
    guide_url: str = ""


class RequiredPermissionView(BaseModel):
    """One permission the credential has to be allowed, exactly as declared.

    Replaces the bare list of permission names this route used to serve. A
    name alone left an operator to look up what it grants and where it is
    turned on; this is the vendor's own declaration
    (`integrations._verification.permissions.RequiredPermission`), read
    through the gateway rather than copied by the console. Every one of these
    is probed, not merely declared — `tools.verify_integrations` makes the
    call each names.
    """

    name: str
    grants: str
    where: str = ""
    capabilities: list[str] = Field(default_factory=list)


class IntegrationView(BaseModel):
    name: str
    #: What a person calls this vendor — never the raw id above, outside a
    #: technical context.
    display_name: str
    category: str
    summary: str
    hosts: list[str]
    regions: list[str]
    capabilities: list[str]
    #: Every field the credential form needs, required and optional alike —
    #: the same declaration `/v1/config/{node_id}/integration-schemas` reads,
    #: so the catalogue and the wizard never disagree about a vendor's fields.
    fields: list[CredentialFieldView]
    #: Every permission this vendor's capabilities need, each with what it
    #: grants and where an operator turns it on.
    permissions: list[RequiredPermissionView]
    health: str
    health_detail: str
    parity: str
    missing_artefacts: list[str]
    #: Set when the estate holds something this vendor plainly runs on. Absent
    #: otherwise, and absent is the ordinary case.
    suggested: SuggestionView | None = None


class IntegrationList(BaseModel):
    integrations: list[IntegrationView]
    #: The vendors this catalogue does not cover. Served with the catalogue
    #: rather than from a route of their own, because the question they answer —
    #: "can this deployment look at X" — is the question the catalogue is being
    #: read to answer, and an operator who has to know to ask a second time
    #: discovers the absence by not finding it.
    known_gaps: list[KnownGapView] = Field(default_factory=list)


class IntegrationVerification(BaseModel):
    integration: str
    state: str
    usable: bool


class IntegrationVerificationReport(BaseModel):
    """What an integration's own verifier found, in the vendor's own terms.

    ``report`` is deliberately untyped at this layer. Each verifier answers the
    question its vendor can actually be asked — Proxmox reports the token's
    effective privileges because Proxmox has an endpoint for them; another
    vendor reports which probes were permitted because it has not. A schema
    imposed here would either be the union of every vendor's answer or the
    intersection, and the intersection is a boolean.
    """

    integration: str
    report: dict[str, Any]


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


async def _suggestions(
    state: GatewayState, auth: AuthenticatedRequest, entries: Any
) -> dict[str, Suggestion]:
    """Return what this team's estate says about where each vendor is running.

    Empty for a deployment that has discovered nothing, which is every
    deployment until the estate step of the wizard has run — and is why the
    steps are in that order.
    """
    offers = {entry.name: entry.profile.default_port for entry in entries}
    if not any(offers.values()):
        return {}
    service = EstateService(gateway=state.gateway, kinds=state.estate_kinds)
    found = await service.query(
        auth.scope,
        EstateQuery(include_absent=False, limit=MAX_ESTATE_SCAN),
        now=datetime.now(UTC),
    )
    return {
        suggestion.integration: suggestion
        for suggestion in suggest_integrations((view.resource for view in found), offers=offers)
    }


def _credential_field_view(declared: Any) -> CredentialFieldView:
    """Return one declared schema field as the catalogue's own view of it."""
    return CredentialFieldView(
        name=declared.name,
        label=declared.display_label,
        secret=declared.is_secret,
        required=declared.required,
        help=declared.description,
        min_scope=declared.min_scope,
        guide_url=declared.guide_url,
    )


def _required_permission_view(declared: Any) -> RequiredPermissionView:
    """Return one declared permission as the catalogue's own view of it."""
    return RequiredPermissionView(
        name=declared.name,
        grants=declared.grants,
        where=declared.where,
        capabilities=list(declared.capabilities),
    )


@router.get("", response_model=IntegrationList)
async def list_integrations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationList:
    """Return the catalogue: every installed integration and what is known about it.

    Ordered by relevance where the estate supplies any and by name otherwise.
    The ordering is computed here rather than by each surface, because the
    console wizard and the CLI wizard ask the same question and two surfaces
    deriving relevance separately is how one of them offers Prometheus first
    while the other buries it, with nobody able to say which is right.
    """
    entries = catalogue(
        health=await integration_health(state.gateway, auth.scope),
        configured=frozenset(await configured_integrations(state, auth)),
    )
    suggested = await _suggestions(state, auth, entries)
    ordered = sorted(entries, key=lambda entry: (entry.name not in suggested, entry.name))
    return IntegrationList(
        known_gaps=[
            KnownGapView(
                integration=str(record["integration"]),
                display_name=str(record["display_name"]),
                category=str(record["category"]),
                cause=str(record["cause"]),
                reason=str(record["reason"]),
                resolution=str(record["resolution"]),
            )
            for record in (gap.to_record() for gap in gaps())
        ],
        integrations=[
            IntegrationView(
                name=entry.name,
                display_name=entry.display_name,
                category=entry.category.value,
                summary=entry.summary,
                hosts=list(entry.descriptor.rule.hosts),
                regions=list(entry.regions),
                capabilities=list(entry.capabilities),
                fields=[
                    _credential_field_view(declared) for declared in entry.descriptor.schema.fields
                ],
                permissions=[_required_permission_view(declared) for declared in entry.permissions],
                health=entry.health.value,
                health_detail=entry.health_detail,
                parity=entry.parity.status.value,
                missing_artefacts=[artefact.value for artefact in entry.parity.missing],
                suggested=(
                    SuggestionView(
                        address=suggested[entry.name].address,
                        from_resource=suggested[entry.name].from_resource,
                        because=suggested[entry.name].because,
                        resource_label=suggested[entry.name].resource_label,
                        resource_kind=suggested[entry.name].resource_kind,
                    )
                    if entry.name in suggested
                    else None
                ),
            )
            for entry in ordered
        ],
    )


def _team_of(auth: AuthenticatedRequest) -> str:
    """Return the credential-handle team this request writes and reads under.

    An organisation-scoped token has no team, and a handle needs one: the vault
    spells the organisation-wide owner as a literal rather than as an empty
    string, because ``datadog/`` and ``datadog`` would otherwise be two
    spellings of one handle.
    """
    return auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM


def _affected_kinds(name: str) -> tuple[VerificationSubject, ...]:
    """Return every kind of recorded check a credential write for ``name`` invalidates.

    Both, for a name that is a vendor *and* a supported provider — Gemini is one
    stored credential that two different checks are run against. Replacing the
    key falsifies both verdicts, and forgetting only one of them would leave the
    other as a green tick earned by a credential that no longer exists.
    """
    if name in SUPPORTED_PROVIDERS:
        return (VerificationSubject.INTEGRATION, VerificationSubject.MODEL_PROVIDER)
    return (VerificationSubject.INTEGRATION,)


def _check_detail(entry: IntegrationCredentialHealth) -> str:
    """Return the sentence a recorded check carries, for each credential state.

    Written here rather than taken from the enum because the record is read by a
    person: "undecryptable" is a state name, and "the stored credential cannot be
    decrypted with this deployment's key" is something somebody can act on.
    """
    return {
        CredentialHealthState.CONFIGURED: "the stored credential is present and current",
        CredentialHealthState.MISSING: "no credential is stored for this integration",
        CredentialHealthState.EXPIRED: "the stored credential has expired",
        CredentialHealthState.UNDECRYPTABLE: (
            "the stored credential cannot be decrypted with this deployment's key"
        ),
    }[entry.state]


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

    The answer is written down. A check whose result lived only in the response
    left the first run's "check that each of them works" step uncompletable:
    green while the tab was open, "nobody has checked this one" on reload.
    """
    schemas = CredentialSchemaRegistry.from_schemas(schema_for(name))
    vault = Vault(gateway=state.gateway, schemas=schemas)
    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=_team_of(auth))
    entry = report.entries[0]
    # Always as an integration, even where ``name`` is also a model provider.
    # What this route establishes is that a stored credential is present and
    # decryptable; the provider's own check exercises tool calling against the
    # endpoint. Writing this cheap answer into the provider's row would
    # overwrite a real verdict with a weaker claim wearing its name.
    await record_check(
        state.gateway,
        auth.scope,
        kind=VerificationSubject.INTEGRATION,
        subject=name,
        passed=entry.state.usable,
        detail=_check_detail(entry),
        checked_by=auth.principal_id,
        team_node_id=_team_of(auth),
    )
    return IntegrationVerification(
        integration=name, state=entry.state.value, usable=entry.state.usable
    )


@router.post("/{name}/verify/report", response_model=IntegrationVerificationReport)
async def verify_integration_deeply(
    name: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationVerificationReport:
    """Run ``name``'s own verifier against the vendor and return its report.

    A separate route rather than a flag on the verify beside it, and the
    separation is the point. The shallow verify is cheap and safe to call from
    any screen that wants to know whether a credential is configured; this one
    makes live vendor calls and answers with a document. Two behaviours behind
    one route with a query parameter is how a screen accidentally makes the
    expensive call on every render.

    Raises:
        ApiProblem: this deployment composed no deep verifier, or ``name`` has
            none to run (404). The refusal says which of the two it was.
    """
    del auth
    if state.deep_verifier is None:
        raise not_found(
            f"This deployment cannot verify {name!r} against its vendor: no deep verifier "
            f"is composed. Reaching a vendor means a credential proxy and a transport, "
            f"which are wired at composition rather than guessed here. The credential "
            f"state itself is answered by POST /v1/integrations/{name}/verify."
        )
    report = await state.deep_verifier(name)
    if report is None:
        raise not_found(
            f"{name!r} has no verifier that produces a report. Its credential state is "
            f"answered by POST /v1/integrations/{name}/verify; there is nothing further "
            f"this vendor can be asked."
        )
    return IntegrationVerificationReport(integration=name, report=dict(report))


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

    # A verdict belongs to the credential it was reached with. Keeping the last
    # one across a rotation would leave a green tick on a key nothing has
    # tested, which is worse than never having checked — it is a wrong answer
    # with the authority of a measurement.
    for kind in _affected_kinds(name):
        await forget_check(state.gateway, auth.scope, kind=kind, subject=name)

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
