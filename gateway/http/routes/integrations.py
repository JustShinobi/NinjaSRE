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

import asyncio
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.llm import SUPPORTED_PROVIDERS
from config.constants.security import (
    CREDENTIAL_ORG_WIDE_TEAM,
    INTEGRATION_TRUST_AUDIT_ACTION,
    INTEGRATION_TRUST_AUDIT_RESOURCE_KIND,
    NINJASRE_CREDENTIAL_PROXY_URL_ENV,
    PROXY_TRUST_REFRESH_PATH,
)
from gateway.http.configured import configured_integrations
from gateway.http.control_plane import compose_control_plane
from gateway.http.credential_schemas import schema_for
from gateway.http.credential_state import credential_detail, effective_credential_state
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.integration_access import refresh_integration_endpoints
from gateway.http.integration_endpoints import (
    configured_endpoints,
    record_certificate_trust,
    record_endpoint,
    split_by_destination,
    stamped_trust,
    trust_audit_detail,
)
from gateway.http.provider_credentials import compose_provider_credentials
from gateway.http.state import GatewayState
from gateway.http.verifications import forget_check, integration_health, record_check
from gateway.webhooks.router import PROFILES as WEBHOOK_PROFILES
from integrations._catalogue.discovery import catalogue, entry
from integrations._catalogue.gaps import gaps
from platform.credentials.errors import CredentialSchemaViolation
from platform.credentials.handles import CredentialHandle
from platform.credentials.health import CredentialHealth
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.estate.service import EstateService
from platform.estate.suggestions import Suggestion, suggest_integrations
from platform.identity.audit.recorder import (
    CREDENTIAL_AUDIT_ACTION_DELETE,
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

#: The version reported for a write that stored no credential at all.
#:
#: An address on its own is a complete configuration for a vendor that ships no
#: authentication, and writing an empty credential version to represent it would
#: be worse than writing nothing: the proxy goes out unauthenticated only when a
#: rule is optional *and* nothing resolved, and an empty version resolves. Nought
#: rather than one, because no version was written and a number that named a
#: version nobody could roll back to would be a lie a console renders.
ADDRESS_ONLY_VERSION = 0


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


#: What a vendor whose traffic only leaves this deployment is called.
DIRECTION_OUTBOUND = "outbound"
#: Both, which is Alertmanager and Grafana: this deployment reads their API, and
#: they post alerts to it. Two directions, two entirely different credentials —
#: which is the fact the catalogue exists to state, because both are "a token".
DIRECTION_BOTH = "both"


def _direction(name: str) -> tuple[str, str]:
    """Return how ``name``'s traffic flows, and the path it delivers to.

    Derived from the webhook router's own source list rather than declared on
    each vendor profile. A vendor package sits below the gateway and cannot see
    the router, so a declared direction would be fifteen separate chances to say
    something the router does not agree with — and the one that drifts is the
    one an operator is reading while waiting for an alert that is going
    somewhere else.

    Only two answers, because a catalogued integration always has a client: the
    contract suite refuses a package without one. "Inbound only" is a state this
    catalogue cannot hold, and a name for it would be a word nothing ever
    returns and a branch no test could reach.
    """
    if name in WEBHOOK_PROFILES:
        return DIRECTION_BOTH, f"/webhooks/{name}"
    return DIRECTION_OUTBOUND, ""


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
    #: Which way this vendor's traffic flows: ``outbound`` when this deployment
    #: only calls it, ``both`` when it also delivers alerts here. The one fact
    #: that makes "which token is this" answerable on the screen that asks for
    #: one — the credential below is always the outbound one, and a vendor that
    #: also delivers needs a second, separately issued delivery token.
    direction: str = DIRECTION_OUTBOUND
    #: Where this vendor posts, when it posts. Empty for an outbound-only
    #: vendor, and a path rather than a URL: the absolute address depends on
    #: which name the deployment was reached at, which only the request knows.
    intake_path: str = ""
    #: Set when the estate holds something this vendor plainly runs on. Absent
    #: otherwise, and absent is the ordinary case.
    suggested: SuggestionView | None = None
    #: One sentence naming where an operator obtains this vendor's credential,
    #: read from the vendor's own profile. The same declaration the guided
    #: first run reads for the same vendor, so the two screens that ask for a
    #: credential never disagree about where it comes from. Empty where a
    #: vendor has not declared one.
    where_to_get_it: str = ""


class IntegrationList(BaseModel):
    integrations: list[IntegrationView]
    #: The vendors this catalogue does not cover. Served with the catalogue
    #: rather than from a route of their own, because the question they answer —
    #: "can this deployment look at X" — is the question the catalogue is being
    #: read to answer, and an operator who has to know to ask a second time
    #: discovers the absence by not finding it.
    known_gaps: list[KnownGapView] = Field(default_factory=list)


class IntegrationDocsView(BaseModel):
    """One vendor package's own documentation, as its ``docs.md`` reads.

    ``markdown`` is the file's text, unmodified — the console renders it with
    the markdown reader it already has rather than this route parsing
    anything. ``readable`` is false in exactly one situation: the vendor is
    installed and its parity report resolved a ``docs.md`` path, but the file
    at that path could not actually be read. That is never "no such vendor" —
    a name outside the catalogue is a 404, not a row here — and it is never
    "this vendor has no documentation", because every embedded vendor is
    required to ship one. It is this deployment's own build failing to carry
    a file its source tree has, which is exactly the failure the console has
    to say plainly rather than reporting as if the document never existed.
    """

    name: str
    display_name: str
    markdown: str
    readable: bool = True


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


class CredentialDeleteView(BaseModel):
    """What disconnecting removed. Nothing here a value could ever have sat in."""

    integration: str
    #: How many stored versions were removed. Zero is not an error — the
    #: console offers "Disconnect" on a connected integration only, but
    #: disconnecting something already bare is idempotent rather than refused.
    versions_removed: int


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
        integrations=[_integration_view(entry, suggested.get(entry.name)) for entry in ordered],
    )


@router.get("/{name}/docs", response_model=IntegrationDocsView)
async def integration_docs(
    name: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationDocsView:
    """Return one embedded vendor's own package documentation.

    Takes the same authorisation every other route on this router does, even
    though it reads nothing tenant-scoped: the permission check is what
    ``authorized`` performs against the route table, and a route mounted
    without it would be reachable by anyone who could reach this deployment
    at all.

    ``name`` is resolved against the installed catalogue and never used to
    build a filesystem path directly: the path this reads comes from the same
    parity report that already walked the package tree to confirm ``docs.md``
    is there, so a name that is not an installed vendor never reaches a disk
    access at all — it is a 404 before that.
    """
    del state, auth  # required for the permission check; this route reads no tenant data
    try:
        found = entry(name)
    except LookupError as unknown:
        raise not_found(str(unknown)) from unknown

    docs_path = found.parity.docs_path
    if docs_path is None:
        # Installed, but this deployment's own build did not carry the file
        # the source tree declares. A read failure, not an absence — see
        # IntegrationDocsView's own docstring for why the two must not be
        # collapsed into one signal.
        return IntegrationDocsView(
            name=found.name, display_name=found.display_name, markdown="", readable=False
        )

    try:
        markdown = docs_path.read_text(encoding="utf-8")
    except OSError:
        return IntegrationDocsView(
            name=found.name, display_name=found.display_name, markdown="", readable=False
        )

    return IntegrationDocsView(name=found.name, display_name=found.display_name, markdown=markdown)


def _integration_view(entry: Any, suggested: Suggestion | None) -> IntegrationView:
    """Return one catalogue entry as the view a console renders."""
    direction, intake_path = _direction(entry.name)
    return IntegrationView(
        name=entry.name,
        display_name=entry.display_name,
        category=entry.category.value,
        summary=entry.summary,
        hosts=list(entry.descriptor.rule.hosts),
        regions=list(entry.regions),
        capabilities=list(entry.capabilities),
        fields=[_credential_field_view(declared) for declared in entry.descriptor.schema.fields],
        permissions=[_required_permission_view(declared) for declared in entry.permissions],
        health=entry.health.value,
        health_detail=entry.health_detail,
        parity=entry.parity.status.value,
        missing_artefacts=[artefact.value for artefact in entry.parity.missing],
        direction=direction,
        intake_path=intake_path,
        where_to_get_it=entry.profile.where_to_get_it,
        suggested=(
            None
            if suggested is None
            else SuggestionView(
                address=suggested.address,
                from_resource=suggested.from_resource,
                because=suggested.because,
                resource_label=suggested.resource_label,
                resource_kind=suggested.resource_kind,
            )
        ),
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


async def _is_addressed(state: GatewayState, auth: AuthenticatedRequest, name: str) -> bool:
    """Return whether an operator has told this deployment where ``name`` is.

    Read from the organisation's node, which is where ``record_endpoint`` writes
    and where the proxy reads its egress allow-list from — the same join
    ``gateway/http/configured.py`` makes for the catalogue, rather than a second
    one that could disagree with it.
    """
    addresses = await configured_endpoints(
        state.gateway, scope=auth.scope, node_id=auth.scope.org_id
    )
    return name in addresses


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
    schema = schema_for(name)
    schemas = CredentialSchemaRegistry.from_schemas(schema)
    vault = Vault(gateway=state.gateway, schemas=schemas)
    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=_team_of(auth))
    entry = report.entries[0]
    # A vendor that ships no authentication is configured by its address, and
    # the vault's "nothing is stored" is a true answer to a question nobody
    # asked. The write route beside this one has always said so; saying it in
    # only one of the two is what made "Save and test" green and "Test again"
    # red with nothing changed in between.
    addressed = await _is_addressed(state, auth, name)
    resolved = effective_credential_state(entry.state, schema=schema, addressed=addressed)
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
        passed=resolved.usable,
        detail=credential_detail(resolved, address_only=resolved is not entry.state),
        checked_by=auth.principal_id,
        team_node_id=_team_of(auth),
    )
    return IntegrationVerification(integration=name, state=resolved.value, usable=resolved.usable)


def _report_detail(report: Mapping[str, Any]) -> str:
    """Return the one sentence the ledger keeps from a whole vendor report.

    The vendor's own words first, because that is what decides what an operator
    does next: "401 Unauthorized" is a key to re-issue and "could not reach the
    host" is an egress rule to open, and a summary that lost the difference
    would be a row nobody can act on.

    A denied permission and a degradation ride along in the same sentence. The
    ledger records two outcomes and only two — a check passed or it did not —
    so a vendor that answered with a caveat is a pass whose detail says what the
    caveat was, rather than a third state the store has no room for.
    """
    connectivity = report.get("connectivity")
    said = ""
    if isinstance(connectivity, Mapping):
        said = str(connectivity.get("detail") or "")
    said = said or ("the vendor answered" if report.get("ok") else "the vendor did not answer")

    missing = [str(name) for name in report.get("missing_permissions") or ()]
    if missing:
        said = f"{said} Permissions the credential does not have: {', '.join(missing)}."

    degradations = [str(line) for line in report.get("degradations") or ()]
    if degradations:
        said = f"{said} {' '.join(degradations)}"
    return said.strip()


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
    if state.deep_verifier is None:
        raise not_found(
            f"This deployment cannot verify {name!r} against its vendor: no deep verifier "
            f"is composed. Reaching a vendor means a credential proxy and a transport, "
            f"which are wired at composition rather than guessed here. The credential "
            f"state itself is answered by POST /v1/integrations/{name}/verify."
        )
    report = await state.deep_verifier(name, _team_of(auth))
    if report is None:
        raise not_found(
            f"{name!r} has no verifier that produces a report. Its credential state is "
            f"answered by POST /v1/integrations/{name}/verify; there is nothing further "
            f"this vendor can be asked."
        )
    # The stronger measurement wins the card. The console calls the shallow
    # verify and then this one, so what an operator sees last is what the vendor
    # itself said — the same reasoning the shallow route gives for refusing to
    # write its cheap answer into a provider's row, applied the other way up.
    await record_check(
        state.gateway,
        auth.scope,
        kind=VerificationSubject.INTEGRATION,
        subject=name,
        passed=bool(report.get("ok")),
        detail=_report_detail(report),
        checked_by=auth.principal_id,
        team_node_id=_team_of(auth),
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

    schema = schema_for(name)
    # Two destinations, one form. The address is not a credential — it is
    # public, it belongs in a diagnostic, and the process that has to read it is
    # the proxy, which reads the configuration tree and cannot read the vault.
    # Writing it into the vault would put the one fact a client needs behind the
    # one door only the proxy may open.
    secrets, addresses = split_by_destination(schema, values)

    # Validated whole, before either half is written. The schema is what knows
    # an address from a token, and a write that stored the secret and then
    # refused the address would leave the deployment half-configured with a
    # green tick on the half that landed.
    try:
        schema.validate(values)
    except CredentialSchemaViolation as violation:
        # ``CredentialSchemaViolation`` is written to name fields and never to
        # quote one, so it crosses the boundary as it stands.
        raise bad_request(str(violation)) from violation

    # The vault's own view of the schema: everything but the address, because
    # validating what the vault is asked to hold against fields that went
    # elsewhere refuses a good write for a field that is not missing.
    stored_schema = schema.for_vault() or schema
    vault = Vault(
        gateway=state.gateway,
        schemas=CredentialSchemaRegistry.from_schemas(stored_schema),
    )
    handle = CredentialHandle(integration=name, team_id=_team_of(auth))
    version = ADDRESS_ONLY_VERSION
    if secrets:
        try:
            version = (await vault.store(auth.scope, handle, secrets)).version
        except CredentialSchemaViolation as violation:
            raise bad_request(str(violation)) from violation

    for address in addresses.values():
        # The organisation's node, not the caller's team. The binding that makes
        # the call is organisation-wide (`compose_integration_access`), so an
        # address written at a team node would be read by nothing and the
        # symptom would be a form that accepted a value and changed no
        # behaviour. Where a vendor lives is a fact about the deployment, not
        # about who typed it.
        await record_endpoint(
            state.gateway,
            scope=auth.scope,
            node_id=auth.scope.org_id,
            integration=name,
            base_url=address,
            actor_id=auth.principal_id,
        )
    if addresses:
        # So the next call goes to the address just written rather than to the
        # one it replaced. A binding refreshed at boot only would make "I fixed
        # the typo" a fact that took a restart to become true.
        await refresh_integration_endpoints(state, org_id=auth.scope.org_id)

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
        detail={"integration": name, "fields": names, "version": version},
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

    if name in SUPPORTED_PROVIDERS:
        # The model factory holds a lease taken at boot, because the port it
        # implements is synchronous and the vault is not. A key replaced here
        # and not re-leased would mean investigations kept using the one it
        # replaced — the same "I fixed it and nothing changed" the address
        # refresh above exists to prevent.
        await compose_provider_credentials(state, org_id=auth.scope.org_id)

    health = CredentialHealth(vault=vault)
    report = await health.report(auth.scope, integrations=(name,), team_id=_team_of(auth))
    entry = report.entries[0]
    # Named for what it is rather than `state`, which on this route is the
    # deployment's own. The same rule the verify route applies, from the same
    # function: an operator who has just pointed this deployment at their own
    # Alertmanager is reading the sentence under the button they pressed, and
    # `missing` is not what happened.
    #
    # An address written in this very request counts, and so does one written by
    # an earlier one — a token-only rotation on a vendor that was already
    # addressed must not read as unaddressed.
    credential_state = effective_credential_state(
        entry.state,
        schema=schema,
        addressed=bool(addresses) or await _is_addressed(state, auth, name),
    )
    return CredentialWriteView(
        integration=name,
        state=credential_state.value,
        usable=credential_state.usable,
        version=version,
        fields=names,
    )


class TrustWriteRequest(BaseModel):
    """What an operator declares about this vendor's certificate.

    There is no field here that turns verification off, and there is not going
    to be one. The insecure form is reached by writing down why, in
    ``unverified_reason`` — which is also what makes it need a permission the
    role that merely operates integrations does not hold. Who accepted it and
    when are stamped by the server; a value sent here for either is discarded
    before anything is validated.
    """

    fingerprints: list[str] = Field(default_factory=list)
    certificate_pem: str | None = None
    unverified_reason: str | None = None


class TrustWriteView(BaseModel):
    """What was written down, and which addresses it now covers."""

    integration: str
    anchor: str
    addresses: list[str] = Field(default_factory=list)
    #: The one line a report shows: what this endpoint is now checked against.
    describes: str = ""


#: How long this route waits on the credential proxy's own answer before
#: giving up and falling back to its periodic cycle. Short and deliberately
#: so: a declaration is already written and audited by the time this runs, so
#: nothing here is worth making an operator wait on — it is a nudge for the
#: common case, not a promise the write depends on.
_TRUST_REFRESH_TIMEOUT_SECONDS = 5.0


def _refresh_credential_proxy_trust(proxy_url: str) -> None:
    """Ask the credential proxy, over its own internal path, to re-read what it trusts.

    Runs in a worker thread at the call site via ``asyncio.to_thread`` — the
    same technique ``HttpProxyTransport`` uses to reach this same proxy for
    the same reason: this deployment's short, audited dependency list has no
    async HTTP client in it. Every failure is swallowed here rather than
    raised: an unreachable proxy, a timeout, or an older proxy that does not
    yet serve this path all leave the declaration exactly as written, and the
    proxy's own periodic cycle still applies it on its own next tick either
    way — this call only tries to make that sooner.
    """
    request = urllib.request.Request(  # noqa: S310 — the URL is the operator's own proxy
        urljoin(proxy_url, PROXY_TRUST_REFRESH_PATH), method="POST"
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — same
            request, timeout=_TRUST_REFRESH_TIMEOUT_SECONDS
        ):
            pass
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as unconfirmed:
        logger.info(
            "integration.trust_refresh_not_confirmed",
            error=str(unconfirmed),
            detail="the credential proxy's own periodic cycle still applies this declaration",
        )


@router.put("/{name}/trust", response_model=TrustWriteView)
async def store_certificate_trust(
    name: str,
    body: TrustWriteRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> TrustWriteView:
    """Declare what this deployment accepts from ``name``'s endpoint certificate.

    Written into the organisation's own configuration, beside the address, where
    the credential proxy already reads from. The write itself asks the proxy to
    re-read it immediately rather than waiting for the periodic cycle that
    rebuilds the egress allow-list — best-effort, and never a reason this write
    fails: an unreachable proxy still applies the declaration on that cycle's
    own next tick, without a restart, exactly as it always has.

    Accepting an unverified certificate needs a permission of its own and a
    reason in writing, and the identity recorded is the authenticated one rather
    than anything the body carried. Nothing is written when either check fails:
    the declaration is validated and authorised before the document is touched,
    so a refusal leaves it exactly as it was.

    Raises:
        ApiProblem: the declaration is not one the vocabulary will hold (400) —
            a blank reason, a private key where the certificate goes, a
            fingerprint that is not one. The refusal names the field and never
            quotes a value.
    """
    try:
        declared = stamped_trust(
            body.model_dump(exclude_none=True),
            actor_id=auth.principal_id,
            at=datetime.now(UTC),
        )
    except ValueError as refused:
        raise bad_request(str(refused)) from refused

    # Before anything is written, and it raises rather than returning: a partial
    # write behind a refusal is the failure this ordering exists to prevent.
    declared.refuse_unless_permitted(auth.context.permissions, node_id=auth.context.scope_node_id)

    covered = await record_certificate_trust(
        state.gateway,
        # The organisation's node, not the caller's team, for the reason the
        # address is written there: the binding that makes the call is
        # organisation-wide, and a declaration written at a team node would be
        # read by nothing.
        scope=auth.scope,
        node_id=auth.scope.org_id,
        integration=name,
        trust=declared,
        actor_id=auth.principal_id,
    )

    # Who, when, which integration, which addresses, which form, the
    # fingerprints when there are any and the reason when there is one — and no
    # certificate material. Accepting an unverified certificate is a decision
    # somebody needs to find six months later, and this is the row they find.
    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=INTEGRATION_TRUST_AUDIT_ACTION,
        resource_kind=INTEGRATION_TRUST_AUDIT_RESOURCE_KIND,
        resource_id=name,
        detail=trust_audit_detail(name, declared, addresses=covered),
    )

    # A verdict belongs to the trust it was reached under. Keeping the last one
    # across a change would leave a green tick on an anchor nothing has tested.
    for kind in _affected_kinds(name):
        await forget_check(state.gateway, auth.scope, kind=kind, subject=name)

    # The declaration is written and audited above this line; everything below
    # it is best-effort and never turns a stored declaration into a refused
    # write. Two things composed at a moment in the past now describe a moment
    # that just changed, and both are asked to catch up rather than left to
    # find out on their own timer: the credential proxy's own registry, which
    # otherwise governs the very next call on nothing sooner than its sixty
    # second cycle, and this deployment's control-plane binding, which
    # otherwise reports the trust anchor it was composed with at boot for as
    # long as the process runs.
    proxy_url = os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, "")
    if proxy_url:
        await asyncio.to_thread(_refresh_credential_proxy_trust, proxy_url)
    try:
        await compose_control_plane(state, org_id=auth.scope.org_id, proxy_url=proxy_url)
    except Exception as unrecomposed:  # noqa: BLE001 — the write already succeeded
        logger.warning("integration.control_plane_not_recomposed", error=str(unrecomposed))

    return TrustWriteView(
        integration=name,
        anchor=declared.anchor.value,
        addresses=list(covered),
        describes=declared.declaration(*covered).describe(),
    )


@router.delete("/{name}/credential", response_model=CredentialDeleteView)
async def delete_credential(
    name: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> CredentialDeleteView:
    """Disconnect: remove this team's stored credential for ``name``, every version.

    The same permission as the write beside it (``credential.write``), because
    whoever may put a credential in the vault is whoever may take it back out —
    a narrower rule here would be a second, undocumented gate on the same
    material. Idempotent: disconnecting an integration with nothing stored
    removes zero versions rather than refusing, so a viewer who reloads a stale
    panel and presses it again does not meet an error over a fact that is
    already true.

    Raises:
        ApiProblem: nothing answers to ``name`` (404) — the same refusal the
            write beside it gives, for the same reason.
    """
    vault = Vault(
        gateway=state.gateway,
        schemas=CredentialSchemaRegistry.from_schemas(schema_for(name)),
    )
    handle = CredentialHandle(integration=name, team_id=_team_of(auth))
    removed = await vault.delete(auth.scope, handle)

    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=CREDENTIAL_AUDIT_ACTION_DELETE,
        resource_kind=_CREDENTIAL_RESOURCE_KIND,
        resource_id=name,
        detail={"integration": name, "versions_removed": removed},
    )
    logger.info(
        "gateway.integration_credential_deleted", integration=name, versions_removed=removed
    )

    # A verdict belongs to the credential it was reached with. A disconnected
    # integration keeping yesterday's green tick would answer "is this
    # working" from a credential that no longer exists.
    for kind in _affected_kinds(name):
        await forget_check(state.gateway, auth.scope, kind=kind, subject=name)

    if name in SUPPORTED_PROVIDERS:
        # Same reason as the write: a key removed from the vault and left in the
        # factory's lease is a credential the operator believes they revoked.
        await compose_provider_credentials(state, org_id=auth.scope.org_id)

    return CredentialDeleteView(integration=name, versions_removed=removed)


__all__ = ["router"]
