"""What an operator has left to do, established by asking rather than by reading.

Five steps, in the order they depend on each other: claim the deployment, give
it something to think with, give it something to look at, give it something to
look *with*, and watch it look.

The fourth is the one that reads oddly and is the reason this docstring is
longer than it was. Every other step leaves a trace an operator can find from
the console — an account, a key, a resource in the estate. A process with no
investigation runtime composed leaves none: it looks identical to one that has,
until somebody presses Investigate and the run fails before it starts. A
checklist that could go to five-of-five on that deployment would be promising a
first investigation the deployment cannot perform, so it carries the step.

The rule the whole module is built around is FR-012's: **a step is done because
the dependency answered, never because a setting is present**. A checklist that
ticked "model provider" on the presence of an API key would tick it for a key
that is wrong, for an endpoint that is down, and for a model that cannot call a
tool — and all three of those are exactly the states this exists to catch. So
the provider step verifies against the endpoint, the source step counts what a
sweep actually found in the estate, and the investigation step looks for a run
that finished.

The blocked/ready distinction is the second piece of editorial content. Every
outstanding step could be shown as "to do", but three of the four cannot
usefully be attempted yet, and a console that offered all four as equal choices
would send an operator to configure an integration before they have an account
of their own.

**Readiness is a third vocabulary, and it is not the same as state.** A step is
``done`` or it is not; a *thing* — the model provider, one vendor integration —
is ``absent``, ``configured``, or ``verified``. The middle one is why it exists:
a stored key nobody has checked is neither nothing nor working, it is the state a
wrong key sits in until an incident finds it, and a console that had only a
boolean would show it as one of the two things it is not. The first run screen
and ``ninjasre doctor`` both branch on this, from this one document, because two
implementations of "are we set up" would disagree on the day it mattered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.first_run import (
    BOOTSTRAP_PRINCIPAL_ID,
    SETUP_READINESS_ABSENT,
    SETUP_READINESS_CONFIGURED,
    SETUP_READINESS_FAILING,
    SETUP_READINESS_VERIFIED,
    SETUP_STATE_BLOCKED,
    SETUP_STATE_DONE,
    SETUP_STATE_READY,
    SETUP_STEP_DURABLE_CREDENTIAL,
    SETUP_STEP_FIRST_INVESTIGATION,
    SETUP_STEP_INFRASTRUCTURE_SOURCE,
    SETUP_STEP_INVESTIGATION_RUNTIME,
    SETUP_STEP_MODEL_PROVIDER,
)
from config.constants.llm import SUPPORTED_PROVIDERS
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.ports.estate_repository import EstateQuery, Resource
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, TurnRecord
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.verification_ledger import VerificationRecord

#: How many resources are named in the guided objective before it stops listing.
#: Enough to make the objective concrete, few enough that the prompt does not
#: turn into an inventory.
_NAMED_RESOURCES = 3


@dataclass(frozen=True, slots=True)
class ChecklistStep:
    """One thing left to do, what was found when it was checked, and what to do."""

    name: str
    title: str
    state: str
    #: What the verification actually found. Shown under the step, and the reason
    #: a failing step is useful rather than merely red.
    detail: str = ""
    #: The next action. Present on every step including a done one, because
    #: "done" still wants to say what it is done *with*.
    action: str = ""
    #: How far along the thing this step configures is, where that is a question
    #: with more than two answers. Steps whose subject is either done or not —
    #: an account exists, a run finished — carry ``absent`` until they are done.
    readiness: str = SETUP_READINESS_ABSENT

    @property
    def done(self) -> bool:
        """Return whether this step needs nothing further."""
        return self.state == SETUP_STATE_DONE

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console renders."""
        return {
            "name": self.name,
            "title": self.title,
            "state": self.state,
            "detail": self.detail,
            "action": self.action,
            "readiness": self.readiness,
        }


@dataclass(frozen=True, slots=True)
class IntegrationReadiness:
    """One integration this deployment declares, and how far along it is.

    ``absent`` here means declared and holding nothing — the list only ever
    contains integrations the deployment knows about, so "not in the list" and
    "in the list with nothing stored" are different facts and both are useful.
    """

    name: str
    readiness: str = SETUP_READINESS_ABSENT

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console renders."""
        return {"name": self.name, "readiness": self.readiness}


@dataclass(frozen=True, slots=True)
class SetupChecklist:
    """Every step, in order, with the state of each."""

    steps: tuple[ChecklistStep, ...]
    #: Every integration this deployment declares, in name order. Empty when the
    #: caller supplied none — this module is tier 3 and may not walk the
    #: integration catalogue itself, so which vendors exist is told to it.
    integrations: tuple[IntegrationReadiness, ...] = ()

    @property
    def provider_readiness(self) -> str:
        """Return how far along this deployment's model provider is.

        The three answers acceptance asks a console to tell apart: no provider,
        a provider configured and unverified, and one that answered.
        """
        return next(
            (step.readiness for step in self.steps if step.name == SETUP_STEP_MODEL_PROVIDER),
            SETUP_READINESS_ABSENT,
        )

    @property
    def complete(self) -> bool:
        """Return whether this deployment has finished setting itself up."""
        return all(step.done for step in self.steps)

    @property
    def outstanding(self) -> tuple[ChecklistStep, ...]:
        """Return what is left, in the order it can be attempted."""
        return tuple(step for step in self.steps if not step.done)

    @property
    def next_step(self) -> ChecklistStep | None:
        """Return the one step an operator can usefully do right now."""
        return next((step for step in self.steps if step.state == SETUP_STATE_READY), None)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console reads."""
        return {
            "complete": self.complete,
            "steps": [step.to_record() for step in self.steps],
            "next": None if self.next_step is None else self.next_step.name,
            "provider": self.provider_readiness,
            "integrations": [entry.to_record() for entry in self.integrations],
        }


async def build_checklist(
    gateway: PersistenceGateway,
    *,
    organisation_id: str,
    integrations: Sequence[str] = (),
    provider_checks: Mapping[str, VerificationRecord] | None = None,
    integration_checks: Mapping[str, VerificationRecord] | None = None,
    runtime_composed: bool = False,
) -> SetupChecklist:
    """Return the checklist this deployment is actually at.

    ``integrations`` is which vendors this deployment declares. ``provider_checks``
    and ``integration_checks`` are the last recorded verdict for a provider or an
    integration, by name — the same record the verification ledger already holds,
    read once by the caller and handed down rather than looked up again here.
    This module never calls a provider's endpoint or a vendor's API to answer a
    checklist read: verifying makes a real call against the operator's own
    infrastructure, and rendering a console page must not be able to spend that
    by accident. A name absent from either mapping is a thing nobody has checked
    — which is not the same claim as "it does not work", and the wording says so.

    The catalogue of declared integrations and the ledger are told to this
    module rather than discovered by it: both are tier 2, and reaching up for
    them is the boundary ``make check-imports`` exists to hold.

    ``runtime_composed`` is whether this process holds something that can
    actually drive an investigation. Told for the same reason and one more: the
    runtime lives in the entry point that composed it, which is a tier above
    this and is the one fact about a deployment that no store can be asked.
    ``False`` is the honest default — a caller who did not say has not
    established it, and guessing yes is how the checklist comes to promise a
    first investigation the deployment cannot perform.
    """
    scope = TenantScope(org_id=organisation_id)
    stored = await _stored_credentials(gateway, scope)
    checked_providers = provider_checks or {}
    checked_integrations = integration_checks or {}

    async with gateway.begin(scope) as uow:
        people = [
            user
            for user in await uow.identity.list_users()
            if user.user_id != BOOTSTRAP_PRINCIPAL_ID and user.is_active
        ]
        claimed = False
        for person in people:
            tokens = await uow.identity.tokens_for_user(person.user_id)
            if any(token.revoked_at is None for token in tokens):
                claimed = True
                break

        resources = await uow.estate.query(EstateQuery(limit=1))
        finished = await uow.run_traces.list_runs(status=RunStatus.COMPLETED, limit=1)

    configured_providers = tuple(name for name in SUPPORTED_PROVIDERS if name in stored)
    credential = _credential_step(claimed, people_count=len(people))
    provider = _provider_step(
        blocked=not credential.done,
        configured=configured_providers,
        checked=checked_providers,
    )
    source = _source_step(bool(resources), blocked=not provider.done)
    runtime = _runtime_step(runtime_composed, blocked=not source.done)
    investigation = _investigation_step(bool(finished), blocked=not runtime.done)

    return SetupChecklist(
        steps=(credential, provider, source, runtime, investigation),
        integrations=tuple(
            IntegrationReadiness(
                name=name,
                readiness=readiness_of(
                    configured=name in stored, checked=checked_integrations.get(name)
                ),
            )
            for name in sorted(set(integrations))
        ),
    )


def readiness_of(*, configured: bool, checked: VerificationRecord | None) -> str:
    """Return how far along one thing is, given what was found about it.

    Public, and reused outside this module: `/v1/providers` derives the same
    word for the same provider from the same record, which is what FR-003
    asks for structurally rather than by two implementations agreeing to.

    A recorded check outranks configuration either way: something a check
    reached and passed is verified without re-establishing that it is
    configured (a working provider's credential plainly resolved), and
    something a check reached and did not pass is reported as failing even
    though a credential is present — a stored key and a working one are
    different facts, and collapsing a known-broken one into "configured" is
    the state a wrong key would otherwise sit in until an incident finds it.
    ``checked`` absent — nobody has checked, or the ledger could not be read —
    falls back to whether a credential is stored at all.
    """
    if checked is not None:
        return SETUP_READINESS_VERIFIED if checked.verified else SETUP_READINESS_FAILING
    return SETUP_READINESS_CONFIGURED if configured else SETUP_READINESS_ABSENT


async def _stored_credentials(gateway: PersistenceGateway, scope: TenantScope) -> frozenset[str]:
    """Return every integration this organisation holds a live credential for.

    Across teams, not only the organisation-wide handle. The question a first
    run asks is "has anybody configured Datadog on this deployment", and a read
    scoped to one team would answer no for a deployment where the one operator
    who set it up did so under theirs.

    Metadata only — the vault exposes no path that reads a value, which is what
    lets a checklist ask this at all. The empty schema registry is the honest
    argument for a read: nothing here validates anything.
    """
    vault = Vault(gateway=gateway, schemas=CredentialSchemaRegistry())
    return frozenset(version.integration for version in await vault.list(scope))


def _state(done: bool, *, blocked: bool) -> str:
    """Return the state one step is in, given whether its predecessors are done."""
    if done:
        return SETUP_STATE_DONE
    return SETUP_STATE_BLOCKED if blocked else SETUP_STATE_READY


def _credential_step(claimed: bool, *, people_count: int) -> ChecklistStep:
    """Return the step that says whether a person owns this deployment yet."""
    return ChecklistStep(
        name=SETUP_STEP_DURABLE_CREDENTIAL,
        title="Create your own account",
        state=_state(claimed, blocked=False),
        detail=(
            f"{people_count} account(s) hold a live credential"
            if claimed
            else (
                "only the bootstrap credential exists, and it expires within the hour — "
                "nobody owns this deployment yet"
            )
        ),
        action=(
            "nothing further"
            if claimed
            else "exchange the bootstrap credential for your own, which revokes the bootstrap one"
        ),
    )


def _provider_step(
    *,
    blocked: bool,
    configured: Sequence[str],
    checked: Mapping[str, VerificationRecord],
) -> ChecklistStep:
    """Return the step that says whether a usable model is configured.

    Usable, not merely configured — but established by reading the last
    recorded check (FR-001), never by calling the endpoint from here
    (FR-004): verification exercises tool calling and structured output
    against the operator's own infrastructure, and rendering this document
    must not be able to spend that by accident. The route that serves it
    calls the provider's own verify endpoint, which writes the record this
    step reads.

    ``configured`` is which providers hold a vault credential — the fact
    that makes the middle, unverified state sayable. ``checked`` is the last
    recorded verdict, by provider id, for whichever provider was ever
    checked, and it is read on its own rather than filtered to ``configured``:
    a provider that runs on the operator's own infrastructure can be verified
    with nothing in the vault at all, and a record that exists is evidence a
    check actually happened regardless of where its credential came from. A
    passed record wins over a failed one when a deployment has tried more
    than one provider, because "usable at all" is the question this step
    answers.
    """
    record = next((entry for entry in checked.values() if entry.verified), None) or next(
        iter(checked.values()), None
    )
    readiness = readiness_of(configured=bool(configured), checked=record)
    if record is None:
        stored = ", ".join(configured)
        return ChecklistStep(
            name=SETUP_STEP_MODEL_PROVIDER,
            title="Connect a model provider",
            state=_state(False, blocked=blocked),
            readiness=readiness,
            detail=(
                f"a credential is stored for {stored}, and nothing has verified it against "
                f"this deployment — a stored key and a working one are different facts"
                if configured
                else "no provider is configured on this deployment"
            ),
            action=(
                "verify the provider — verification calls a tool and asks for structured "
                "output, rather than checking that the endpoint answers"
                if configured
                else "configure a provider, then verify it"
            ),
        )

    exercised = f" ({record.model_id})" if record.model_id else ""
    return ChecklistStep(
        name=SETUP_STEP_MODEL_PROVIDER,
        title="Connect a model provider",
        state=_state(record.verified, blocked=blocked),
        readiness=readiness,
        detail=(
            f"a check reached {record.subject}{exercised} and it answered"
            if record.verified
            else f"the last check of {record.subject}{exercised} did not pass: {record.detail}"
        ),
        action=(
            "nothing further"
            if record.verified
            else "verify the provider again once the finding above is addressed"
        ),
    )


def _source_step(has_resources: bool, *, blocked: bool) -> ChecklistStep:
    """Return the step that says whether there is anything to investigate."""
    return ChecklistStep(
        name=SETUP_STEP_INFRASTRUCTURE_SOURCE,
        title="Connect an infrastructure source",
        state=_state(has_resources, blocked=blocked),
        detail=(
            "1 or more resources have been discovered and are in the estate"
            if has_resources
            else (
                "the estate is empty, so a sweep has either not run or found nothing — a "
                "configured integration that has discovered nothing is not a connected source"
            )
        ),
        action=(
            "nothing further"
            if has_resources
            else "configure an integration and run a discovery sweep"
        ),
    )


def _runtime_step(composed: bool, *, blocked: bool) -> ChecklistStep:
    """Return the step that says whether anything here can run an investigation.

    Neither sentence names a setting of the process. This document is what the
    console renders, and a step whose text is a deploy instruction would put the
    environment variable back on the screen an operator opens — which is the
    thing the console's failure translation exists to keep it off. The variable
    is still named where it belongs: in the refusal the entry point logs, and in
    the deployment documentation.
    """
    return ChecklistStep(
        name=SETUP_STEP_INVESTIGATION_RUNTIME,
        title="Give it something to investigate with",
        state=_state(composed, blocked=blocked),
        # Not through `_readiness`: this step has no verification ledger
        # entry to read, and no "stored but unchecked" middle state — the
        # runtime either is or is not composed, established by the entry
        # point that would have composed it.
        readiness=SETUP_READINESS_VERIFIED if composed else SETUP_READINESS_ABSENT,
        detail=(
            "this deployment holds a runtime, so an investigation has something to run in"
            if composed
            else (
                "nothing here can drive an investigation yet — a model provider and an "
                "integration are both configured, and the part that puts them together "
                "has not been supplied to this process"
            )
        ),
        action=(
            "nothing further"
            if composed
            else (
                "whoever operates this deployment supplies the investigation runtime; "
                "until they do, starting an investigation will fail immediately"
            )
        ),
    )


def _investigation_step(has_finished_run: bool, *, blocked: bool) -> ChecklistStep:
    """Return the step that says whether anything has actually been investigated."""
    return ChecklistStep(
        name=SETUP_STEP_FIRST_INVESTIGATION,
        title="Run your first investigation",
        state=_state(has_finished_run, blocked=blocked),
        detail=(
            "an investigation has completed and its transcript is readable"
            if has_finished_run
            else "no investigation has completed on this deployment"
        ),
        action=(
            "nothing further"
            if has_finished_run
            else "start the guided investigation; it runs against what you have connected"
        ),
    )


# --- The guided first investigation -----------------------------------------------


def guided_objective(resources: Sequence[Resource]) -> str:
    """Return the objective the guided investigation runs, built from the estate.

    Built from what is there rather than from a template. An objective about "a
    cluster" produces a run against nothing, and the operator's conclusion is
    that the first investigation was a canned demonstration — which for a
    platform whose whole claim is evidence over assertion is the worst possible
    first impression.

    Raises:
        ValueError: the estate is empty, so there is nothing to run against.
    """
    if not resources:
        raise ValueError(
            "the estate is empty, so there is nothing to investigate. Connect an "
            "infrastructure source and run a discovery sweep first."
        )

    sources = sorted({resource.source for resource in resources if resource.source})
    named = [
        resource.display_name or resource.native_id or resource.resource_id
        for resource in resources[:_NAMED_RESOURCES]
    ]
    remainder = len(resources) - len(named)
    listing = ", ".join(named) + (f" and {remainder} more" if remainder > 0 else "")

    return (
        f"Report the current health of this estate and name anything that needs attention. "
        f"It is served by {', '.join(sources) or 'an unnamed source'} and includes {listing}. "
        f"Read the state of each resource, say what you found, and cite the observation "
        f"behind every claim. Change nothing."
    )


def readable_transcript(run: AgentRun, turns: Sequence[TurnRecord]) -> str:
    """Return the run as something a person reads top to bottom.

    FR-014 asks for a transcript that is readable, which is a property of the
    rendering rather than of the trace. So the rendering lives here, beside the
    step that promises it, and is asserted on directly.
    """
    header = [
        f"Investigation {run.run_id} — {run.status}",
        f"  started: {run.started_at.isoformat() if run.started_at else 'not recorded'}",
    ]
    if run.summary:
        header.append(f"  finding: {run.summary}")

    body: list[str] = []
    for turn in sorted(turns, key=lambda record: record.index):
        thought = str(turn.payload.get("thought", "")).strip()
        text = str(turn.payload.get("text", "")).strip()
        body.append(f"\n  step {turn.index + 1}")
        if thought:
            body.append(f"    thinking: {thought}")
        if text:
            body.append(f"    {text}")
        if not thought and not text:
            body.append("    (this step recorded no narration)")

    if not body:
        body.append("\n  This run recorded no steps.")

    return "\n".join([*header, *body])


__all__ = [
    "ChecklistStep",
    "IntegrationReadiness",
    "SetupChecklist",
    "build_checklist",
    "guided_objective",
    "readable_transcript",
    "readiness_of",
]
