"""First run over HTTP: the checklist, the self-check, the diagnosis, the demonstration.

FR-010 and FR-022 both say the same thing in different words — what the terminal
showed at bring-up has to be reachable afterwards from the console and the CLI.
These are the routes that make that true. The logic is all in
``platform.startup``; every handler here is a view over it, which is what keeps
the CLI and the console reporting the same thing rather than two renderings of
two calculations.

The self-check is deliberately *not* given a live model verifier by default.
Verifying a provider makes real calls against the operator's endpoint, and a
console page that spent tokens every time somebody opened it would be a page
nobody opens twice. A deployment that wants the provider verified on every
self-check supplies the verifier at composition.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.first_run import LOCAL_ADMIN_SETUP_COMMAND
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.runtime import runtime_composed
from gateway.http.state import GatewayState
from gateway.http.verifications import integration_health
from integrations._catalogue.discovery import catalogue
from integrations._catalogue.entry import HealthStatus
from platform.identity.enrolment import identity_provider_is_active, local_sign_in_is_open
from platform.identity.errors import LocalEnrolmentBlockedBySso, LocalSignInAlreadyOpen
from platform.startup.bootstrap import (
    establish_durable_credential,
    organisation_id,
    read_credential,
)
from platform.startup.checklist import build_checklist
from platform.startup.demo import DemoRefused, remove_demonstration, seed_demonstration
from platform.startup.diagnostics import last_failure, support_bundle
from platform.startup.selfcheck import self_check

router = APIRouter(prefix="/v1/setup", tags=["setup"])


class ChecklistStepView(BaseModel):
    name: str
    title: str
    state: str
    detail: str = ""
    action: str = ""
    #: How far along the thing this step configures is: ``absent``,
    #: ``configured``, or ``verified``. Distinct from ``state``, which is about
    #: the step. A key that is stored and unchecked is the middle one, and it is
    #: the state a wrong key sits in until an incident finds it.
    readiness: str


class IntegrationReadinessView(BaseModel):
    name: str
    readiness: str


class ChecklistView(BaseModel):
    complete: bool
    steps: list[ChecklistStepView]
    next: str | None = None
    #: The provider step's readiness, lifted to the top level because it is what
    #: a first-run screen and ``ninjasre doctor`` both branch on first.
    provider: str
    #: Every integration this deployment declares, and how far along each is.
    integrations: list[IntegrationReadinessView]


class FindingView(BaseModel):
    check: str
    problem: str
    action: str
    blocks: str


class SelfCheckView(BaseModel):
    ok: bool
    findings: list[FindingView]
    passed: list[str]
    duration_seconds: float


class DiagnosisView(BaseModel):
    stage: str
    problem: str
    action: str
    settings: list[str] = Field(default_factory=list)
    occurred_at: str = ""


class DurableCredentialRequest(BaseModel):
    user_id: str
    email: str
    display_name: str
    #: The passphrase this administrator will sign in with afterwards.
    #:
    #: It arrives in the body while the bootstrap credential deliberately
    #: does not, and the asymmetry is the point: the bootstrap credential is
    #: read from the host because presenting it in a request would let a
    #: caller name somebody else's. This one is the caller's own, being set
    #: for the first time, and there is nowhere else it could come from.
    password: str = Field(min_length=1)
    name: str = "first administrator"


class DurableCredentialView(BaseModel):
    #: Returned exactly once, in the response to the call that created it. There
    #: is no route that reads a token back — the store holds a hash.
    secret: str
    token_id: str
    expires_at: str
    user_id: str


class DemoView(BaseModel):
    organisation_id: str
    counts: dict[str, int]
    total: int = 0
    forced: bool = False


class DemoRemovalView(BaseModel):
    organisation_id: str
    removed: bool
    counts: dict[str, int]


@router.get("/checklist", response_model=ChecklistView)
async def checklist(
    auth: AuthenticatedRequest = Depends(authorized),
    state: GatewayState = Depends(get_state),
) -> ChecklistView:
    """Return what is left to set up, each step verified against its dependency.

    The integration catalogue and its health ledger are read here rather than in
    ``build_checklist``: that module is tier 3 and reaching up for ``integrations``
    would be the boundary ``make check-imports`` exists to hold. Health is what
    the recorded checks found, so "verified" means something answered rather than
    that a credential is present — and it means that on the next request too,
    which is the whole reason the answer is written down.
    """
    ledger = await integration_health(state.gateway, auth.scope)
    entries = catalogue(health=ledger)
    declared = tuple(entry.name for entry in entries)
    reached = tuple(entry.name for entry in entries if entry.health is HealthStatus.HEALTHY)
    built = await build_checklist(
        state.gateway,
        organisation_id=auth.scope.org_id,
        integrations=declared,
        verified_integrations=reached,
        runtime_composed=runtime_composed(state),
    )
    record = built.to_record()
    return ChecklistView(
        complete=bool(record["complete"]),
        steps=[ChecklistStepView(**step) for step in record["steps"]],
        next=record["next"],
        provider=str(record["provider"]),
        integrations=[IntegrationReadinessView(**entry) for entry in record["integrations"]],
    )


@router.get("/self-check", response_model=SelfCheckView, dependencies=[Depends(authorized)])
async def run_self_check(state: GatewayState = Depends(get_state)) -> SelfCheckView:
    """Run every check in one pass and return the findings, most blocking first.

    The runtime check is handed what this process actually composed, because
    that is a fact only the running process holds — no store can be asked
    whether anything here can drive an investigation, and it is the one
    dependency that leaves no trace on any screen.
    """
    report = await self_check(
        state.gateway,
        investigation_runtime=lambda: runtime_composed(state),
    )
    return SelfCheckView(
        ok=report.ok,
        findings=[
            FindingView(
                check=finding.check,
                problem=finding.problem,
                action=finding.action,
                blocks=finding.blocks,
            )
            for finding in report.ordered()
        ],
        passed=[entry.check for entry in report.passed],
        duration_seconds=round(report.duration_seconds, 3),
    )


@router.get("/diagnostics", response_model=DiagnosisView, dependencies=[Depends(authorized)])
async def diagnostics() -> DiagnosisView:
    """Return the last bring-up failure this host recorded.

    404 when there was none, which is the honest answer: a deployment that
    started has no failure to describe, and returning an empty one would put a
    blank panel where a console should show nothing at all.
    """
    failure = last_failure()
    if failure is None:
        raise not_found("this deployment recorded no bring-up failure")
    return DiagnosisView(
        stage=failure.stage,
        problem=failure.problem,
        action=failure.action,
        settings=list(failure.settings),
        occurred_at=failure.occurred_at,
    )


@router.get("/support-bundle", dependencies=[Depends(authorized)])
async def bundle(state: GatewayState = Depends(get_state)) -> dict[str, object]:
    """Return the support bundle as a document, with every secret already removed.

    Returned rather than written, because over HTTP the caller decides where it
    lands. The CLI writes it to a file; the console offers it as a download. The
    redaction is the same either way, and it happens here.
    """
    health = await state.gateway.health()
    report = await self_check(state.gateway)
    return support_bundle(
        environ=dict(os.environ),
        self_check=report,
        logs=(),
        schema_revision=(health.migrations.applied_revision or "") if health.migrations else "",
    ).to_record()


@router.post(
    "/durable-credential",
    response_model=DurableCredentialView,
    dependencies=[Depends(authorized)],
)
async def durable_credential(
    body: DurableCredentialRequest,
    state: GatewayState = Depends(get_state),
) -> DurableCredentialView:
    """Exchange the bootstrap credential for one that lasts, and spend it.

    Reads the bootstrap credential from the host file rather than from the
    request: the caller has already proved they hold it by getting this far, and
    accepting it in a body would be a second way in — one where a caller could
    name somebody else's credential to revoke. The passphrase is the opposite
    case: it is the caller's own, chosen for the first time, and the request
    body is the only place it could come from.
    """
    bootstrap = read_credential()
    if bootstrap is None:
        raise bad_request(
            "there is no bootstrap credential on this host to exchange. It has already "
            "been used, or this deployment was brought up before that was recorded."
        )
    try:
        issued = await establish_durable_credential(
            state.gateway,
            state.tokens,
            bootstrap=bootstrap,
            user_id=body.user_id,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
            name=body.name,
        )
    except (LocalSignInAlreadyOpen, LocalEnrolmentBlockedBySso) as refused:
        raise bad_request(str(refused)) from refused
    return DurableCredentialView(**issued.to_record())


@router.post("/demo", response_model=DemoView, dependencies=[Depends(authorized)])
async def enable_demo(
    state: GatewayState = Depends(get_state),
    force: bool = False,
) -> DemoView:
    """Load the demonstration deployment, refusing to seed over real data."""
    try:
        report = await seed_demonstration(state.gateway, force=force)
    except DemoRefused as refusal:
        raise bad_request(str(refusal)) from refusal
    record = report.to_record()
    return DemoView(
        organisation_id=report.organisation_id,
        counts=dict(report.counts),
        total=int(record["total"]),
        forced=report.forced,
    )


@router.delete("/demo", response_model=DemoRemovalView, dependencies=[Depends(authorized)])
async def disable_demo(state: GatewayState = Depends(get_state)) -> DemoRemovalView:
    """Remove the demonstration deployment in one action, leaving nothing behind."""
    report = await remove_demonstration(state.gateway)
    return DemoRemovalView(
        organisation_id=report.organisation_id,
        removed=report.removed,
        counts=dict(report.counts),
    )


class LocalAdministratorAvailabilityView(BaseModel):
    """The one fact the sign-in and first-run screens need before anybody is signed in.

    Ternary, and nothing else deployment-specific: no name, no version, no
    organisation, no count of anything. ``state`` is one of ``"unclaimed"``
    (no local administrator and no identity provider — the CLI's own
    command is the way in), ``"administered"`` (a local administrator
    already exists, whether from the environment or a deliberate
    enrolment), or ``"identity_provider"`` (this deployment's identity
    provider is its way in).

    ``command`` carries the CLI invitation exactly when it is relevant —
    ``state == "unclaimed"`` — and is empty otherwise. It is a fixed
    constant, the same string on every deployment, read from the one place
    that also writes it into the boot announcement: naming nothing about
    *this* deployment is what keeps it inside FR-076's boundary despite
    being served unauthenticated.
    """

    state: str
    command: str = ""


@router.get("/local-administrator", response_model=LocalAdministratorAvailabilityView)
async def local_administrator_availability(
    state: GatewayState = Depends(get_state),
) -> LocalAdministratorAvailabilityView:
    """Return the ternary fact the sign-in and first-run screens read.

    Public by declaration: it is what tells an unauthenticated visitor
    whether there is a way in at all, and revealing that is the whole point
    of the route — see ``LocalAdministratorAvailabilityView`` for what it
    deliberately does not also reveal.
    """
    org_id = organisation_id()
    if await identity_provider_is_active(state.gateway, org_id=org_id):
        return LocalAdministratorAvailabilityView(state="identity_provider")
    administered = (
        state.local_sign_in is not None and state.local_sign_in.account is not None
    ) or await local_sign_in_is_open(state.gateway, org_id=org_id)
    if administered:
        return LocalAdministratorAvailabilityView(state="administered")
    return LocalAdministratorAvailabilityView(state="unclaimed", command=LOCAL_ADMIN_SETUP_COMMAND)


__all__ = ["router"]
