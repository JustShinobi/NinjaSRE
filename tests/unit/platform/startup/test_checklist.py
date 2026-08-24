"""The setup checklist: four steps, each verified against the thing itself.

The property under test throughout is FR-012's — a step is done because the
dependency answered, never because a setting is present. Each test here sets the
configuration and asserts the step is *not* done, then makes the dependency real
and asserts it is.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.first_run import (
    DEFAULT_ORGANISATION_ID,
    GUIDED_INVESTIGATION_TRIGGER,
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
    SETUP_STEP_ORDER,
)
from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import (
    CredentialField,
    CredentialSchema,
    CredentialSchemaRegistry,
)
from platform.credentials.vault import Vault
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, TurnRecord
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.verification_ledger import (
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
)
from platform.startup.bootstrap import bring_up, establish_durable_credential
from platform.startup.checklist import (
    build_checklist,
    guided_objective,
    readable_transcript,
)

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id=DEFAULT_ORGANISATION_ID)
CHECKED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def environ(tmp_path: object) -> dict[str, str]:
    from config.constants.first_run import NINJASRE_STATE_DIR_ENV

    return {NINJASRE_STATE_DIR_ENV: str(tmp_path)}


@pytest.fixture
async def store(environ: dict[str, str]) -> FakePersistence:
    """Return a deployment brought up and no further: nothing is configured."""
    gateway = FakePersistence()
    await bring_up(gateway, TokenService(gateway=gateway), environ=environ)
    return gateway


def _step(checklist: object, name: str) -> object:
    return next(step for step in checklist.steps if step.name == name)  # type: ignore[attr-defined]


async def _store_credential(gateway: FakePersistence, integration: str) -> None:
    """Put a credential in the vault for ``integration``, as the write route would.

    Through the real vault rather than by writing a row, so what the checklist
    reads is what a credential written over HTTP actually leaves behind.
    """
    schema = CredentialSchema(integration=integration, fields=(CredentialField(name="api_key"),))
    vault = Vault(gateway=gateway, schemas=CredentialSchemaRegistry.from_schemas(schema))
    await vault.store(SCOPE, CredentialHandle.for_organisation(integration), {"api_key": "stored"})


def _passed(
    subject: str,
    *,
    kind: VerificationSubject = VerificationSubject.MODEL_PROVIDER,
    **fields: object,
) -> VerificationRecord:
    """Return the recorded verdict a passing check of ``subject`` would leave."""
    return VerificationRecord(
        subject=subject,
        kind=kind,
        outcome=VerificationOutcome.PASSED,
        checked_at=CHECKED_AT,
        **fields,  # type: ignore[arg-type]
    )


def _failed(
    subject: str,
    *,
    kind: VerificationSubject = VerificationSubject.MODEL_PROVIDER,
    detail: str = "it did not answer",
    **fields: object,
) -> VerificationRecord:
    """Return the recorded verdict a failing check of ``subject`` would leave."""
    return VerificationRecord(
        subject=subject,
        kind=kind,
        outcome=VerificationOutcome.FAILED,
        checked_at=CHECKED_AT,
        detail=detail,
        **fields,  # type: ignore[arg-type]
    )


# --- Shape ----------------------------------------------------------------------


async def test_a_fresh_deployment_has_every_step_outstanding(store: FakePersistence) -> None:
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert [step.name for step in checklist.steps] == list(SETUP_STEP_ORDER)
    assert checklist.complete is False


async def test_every_outstanding_step_names_what_to_do_next(store: FakePersistence) -> None:
    """FR-011. A checklist that says "not configured" four times is a list of
    nouns, not a next action."""
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    for step in checklist.steps:
        assert step.title
        assert step.action, f"{step.name} says nothing about what to do"


async def test_a_step_whose_predecessor_is_outstanding_is_blocked_rather_than_ready(
    store: FakePersistence,
) -> None:
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_DURABLE_CREDENTIAL).state == SETUP_STATE_READY
    assert _step(checklist, SETUP_STEP_MODEL_PROVIDER).state == SETUP_STATE_BLOCKED
    assert _step(checklist, SETUP_STEP_FIRST_INVESTIGATION).state == SETUP_STATE_BLOCKED


# --- Each step verifies the dependency, not the configuration --------------------


async def test_the_credential_step_is_done_when_a_person_holds_a_live_token(
    store: FakePersistence, environ: dict[str, str]
) -> None:
    tokens = TokenService(gateway=store)
    result = await bring_up(store, tokens, environ=environ)
    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
        password="a very long passphrase",
        environ=environ,
    )

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_DURABLE_CREDENTIAL).state == SETUP_STATE_DONE


async def test_the_bootstrap_principal_alone_does_not_complete_the_credential_step(
    store: FakePersistence,
) -> None:
    """The whole point of the step. A deployment holding only the credential it
    printed itself has not been claimed by anybody."""
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_DURABLE_CREDENTIAL).state != SETUP_STATE_DONE


async def test_the_provider_step_reads_the_recorded_check_rather_than_asking_the_endpoint(
    store: FakePersistence,
) -> None:
    """FR-001, FR-004: verifying a provider makes a real call against the
    operator's endpoint, and the checklist may not spend that on a render — it
    reads what the last recorded check already found instead."""
    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        provider_checks={
            "local": _failed("local", detail="tiny-1b did not call the tool it was given")
        },
    )

    step = _step(checklist, SETUP_STEP_MODEL_PROVIDER)
    assert step.state != SETUP_STATE_DONE
    assert step.readiness == SETUP_READINESS_FAILING
    assert "did not call the tool" in step.detail


async def test_a_verified_provider_completes_its_step(store: FakePersistence) -> None:
    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        provider_checks={"local": _passed("local", model_id="qwen2.5:32b")},
    )

    assert _step(checklist, SETUP_STEP_MODEL_PROVIDER).state == SETUP_STATE_DONE


# --- Three deployments a console has to tell apart ------------------------------
#
# "Nothing is set up", "a key is stored and nobody has checked it", and "ready"
# are three different screens and three different next actions. A checklist that
# collapsed the middle one would show a green provider to a deployment whose key
# is wrong, which is the state this whole checklist exists to catch.


async def test_a_deployment_with_no_provider_says_so(store: FakePersistence) -> None:
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert checklist.provider_readiness == SETUP_READINESS_ABSENT
    assert _step(checklist, SETUP_STEP_MODEL_PROVIDER).readiness == SETUP_READINESS_ABSENT


async def test_a_stored_provider_credential_nobody_verified_is_its_own_state(
    store: FakePersistence,
) -> None:
    """Configured is not verified, and the difference is discovered at 03:00."""
    await _store_credential(store, "anthropic")

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert checklist.provider_readiness == SETUP_READINESS_CONFIGURED
    step = _step(checklist, SETUP_STEP_MODEL_PROVIDER)
    assert step.state != SETUP_STATE_DONE
    assert step.readiness == SETUP_READINESS_CONFIGURED
    assert "anthropic" in step.detail


async def test_a_verified_provider_reads_as_ready(store: FakePersistence) -> None:
    await _store_credential(store, "anthropic")

    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        provider_checks={"anthropic": _passed("anthropic", model_id="claude-sonnet-5")},
    )

    assert checklist.provider_readiness == SETUP_READINESS_VERIFIED
    assert _step(checklist, SETUP_STEP_MODEL_PROVIDER).readiness == SETUP_READINESS_VERIFIED


async def test_a_provider_whose_last_check_failed_is_never_reported_as_configured(
    store: FakePersistence,
) -> None:
    """FR-006: a broken key must not read the same as an unchecked one."""
    await _store_credential(store, "anthropic")

    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        provider_checks={"anthropic": _failed("anthropic")},
    )

    assert checklist.provider_readiness == SETUP_READINESS_FAILING
    step = _step(checklist, SETUP_STEP_MODEL_PROVIDER)
    assert step.readiness == SETUP_READINESS_FAILING
    assert step.state != SETUP_STATE_DONE


async def test_the_four_provider_states_are_distinguishable_in_the_record(
    store: FakePersistence,
) -> None:
    """The document a console and ``doctor`` both branch on carries the distinction."""
    absent = (await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)).to_record()
    await _store_credential(store, "anthropic")
    configured = (await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)).to_record()
    failing = (
        await build_checklist(
            store,
            organisation_id=DEFAULT_ORGANISATION_ID,
            provider_checks={"anthropic": _failed("anthropic")},
        )
    ).to_record()
    ready = (
        await build_checklist(
            store,
            organisation_id=DEFAULT_ORGANISATION_ID,
            provider_checks={"anthropic": _passed("anthropic", model_id="m")},
        )
    ).to_record()

    assert absent["provider"] == SETUP_READINESS_ABSENT
    assert configured["provider"] == SETUP_READINESS_CONFIGURED
    assert failing["provider"] == SETUP_READINESS_FAILING
    assert ready["provider"] == SETUP_READINESS_VERIFIED
    assert (
        len(
            {
                absent["provider"],
                configured["provider"],
                failing["provider"],
                ready["provider"],
            }
        )
        == 4
    )


# --- Which integrations are where -----------------------------------------------


async def test_a_declared_integration_with_nothing_stored_reads_as_absent(
    store: FakePersistence,
) -> None:
    checklist = await build_checklist(
        store, organisation_id=DEFAULT_ORGANISATION_ID, integrations=("datadog", "kubernetes")
    )

    assert {entry.name: entry.readiness for entry in checklist.integrations} == {
        "datadog": SETUP_READINESS_ABSENT,
        "kubernetes": SETUP_READINESS_ABSENT,
    }


async def test_an_integration_with_a_credential_reads_as_configured(
    store: FakePersistence,
) -> None:
    await _store_credential(store, "datadog")

    checklist = await build_checklist(
        store, organisation_id=DEFAULT_ORGANISATION_ID, integrations=("datadog", "kubernetes")
    )

    assert {entry.name: entry.readiness for entry in checklist.integrations} == {
        "datadog": SETUP_READINESS_CONFIGURED,
        "kubernetes": SETUP_READINESS_ABSENT,
    }


async def test_an_integration_a_live_run_reached_reads_as_verified(
    store: FakePersistence,
) -> None:
    """Verified means something answered, which only a recorded check can establish."""
    await _store_credential(store, "datadog")

    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        integrations=("datadog", "kubernetes"),
        integration_checks={"datadog": _passed("datadog", kind=VerificationSubject.INTEGRATION)},
    )

    assert {entry.name: entry.readiness for entry in checklist.integrations} == {
        "datadog": SETUP_READINESS_VERIFIED,
        "kubernetes": SETUP_READINESS_ABSENT,
    }


async def test_an_integration_whose_last_check_failed_reads_as_failing_not_configured(
    store: FakePersistence,
) -> None:
    """FR-007: the same distinction the provider step draws, for an integration."""
    await _store_credential(store, "datadog")

    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        integrations=("datadog",),
        integration_checks={"datadog": _failed("datadog", kind=VerificationSubject.INTEGRATION)},
    )

    assert {entry.name: entry.readiness for entry in checklist.integrations} == {
        "datadog": SETUP_READINESS_FAILING,
    }


async def test_an_integration_nobody_declared_is_not_reported(
    store: FakePersistence,
) -> None:
    """The list is what this deployment has, not everything that could be installed."""
    await _store_credential(store, "datadog")

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert checklist.integrations == ()
    assert checklist.to_record()["integrations"] == []


async def test_the_integration_detail_is_in_the_record_the_console_reads(
    store: FakePersistence,
) -> None:
    await _store_credential(store, "datadog")

    record = (
        await build_checklist(
            store,
            organisation_id=DEFAULT_ORGANISATION_ID,
            integrations=("datadog",),
        )
    ).to_record()

    assert record["integrations"] == [{"name": "datadog", "readiness": SETUP_READINESS_CONFIGURED}]


async def test_the_source_step_is_done_when_the_estate_actually_holds_something(
    store: FakePersistence,
) -> None:
    """Not "an integration is configured" — a resource that a sweep found."""
    async with store.begin(SCOPE) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="pve-node-1",
                kind="proxmox.node",
                source="proxmox",
                native_id="node-1",
                display_name="node-1",
            )
        )

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_INFRASTRUCTURE_SOURCE).state == SETUP_STATE_DONE
    assert "1" in _step(checklist, SETUP_STEP_INFRASTRUCTURE_SOURCE).detail


async def test_the_investigation_step_is_done_when_one_has_actually_finished(
    store: FakePersistence,
) -> None:
    async with store.begin(SCOPE) as uow:
        await uow.run_traces.start_run(
            AgentRun(
                run_id="run-1",
                trigger=GUIDED_INVESTIGATION_TRIGGER,
                status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC),
                summary="the node was out of memory",
            )
        )

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_FIRST_INVESTIGATION).state == SETUP_STATE_DONE


async def test_a_run_that_is_still_going_does_not_complete_the_step(
    store: FakePersistence,
) -> None:
    async with store.begin(SCOPE) as uow:
        await uow.run_traces.start_run(
            AgentRun(
                run_id="run-1",
                trigger=GUIDED_INVESTIGATION_TRIGGER,
                status=RunStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
        )

    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_FIRST_INVESTIGATION).state != SETUP_STATE_DONE


# --- Completion ------------------------------------------------------------------


async def test_a_finished_deployment_reports_the_checklist_complete(
    store: FakePersistence, environ: dict[str, str]
) -> None:
    """FR-013. The console hides it on completion, and this is what it reads."""
    tokens = TokenService(gateway=store)
    result = await bring_up(store, tokens, environ=environ)
    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
        password="a very long passphrase",
        environ=environ,
    )
    async with store.begin(SCOPE) as uow:
        await uow.estate.upsert(Resource(resource_id="r1", kind="k", source="s", native_id="n1"))
        await uow.run_traces.start_run(
            AgentRun(
                run_id="run-1",
                trigger=GUIDED_INVESTIGATION_TRIGGER,
                status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC),
            )
        )

    # A composed runtime is part of being finished now, and deliberately so:
    # this deployment has an account, a verified provider, an estate and a
    # completed run, and without something to run investigations in it still
    # cannot perform the next one. "Complete" that did not include it was the
    # console's promise of a first investigation, made on a deployment that
    # would refuse it.
    checklist = await build_checklist(
        store,
        organisation_id=DEFAULT_ORGANISATION_ID,
        provider_checks={"local": _passed("local", model_id="m")},
        runtime_composed=True,
    )

    assert checklist.complete is True
    assert all(step.state == SETUP_STATE_DONE for step in checklist.steps)
    assert checklist.to_record()["complete"] is True


async def test_the_checklist_is_still_answerable_after_it_is_complete(
    store: FakePersistence,
) -> None:
    """FR-013's second half: it disappears from the way, not from the product."""
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert len(checklist.steps) == len(SETUP_STEP_ORDER)


# --- The guided first investigation ------------------------------------------------


def test_the_guided_objective_names_what_the_operator_actually_connected() -> None:
    """T-020. "Run against whatever the operator connected" is only true if the
    objective mentions it — an objective about a generic cluster produces a run
    against nothing."""
    resources = (
        Resource(
            resource_id="pve-1",
            kind="proxmox.node",
            source="proxmox",
            native_id="pve-1",
            display_name="pve-1",
        ),
        Resource(
            resource_id="pve-2",
            kind="proxmox.node",
            source="proxmox",
            native_id="pve-2",
            display_name="pve-2",
        ),
    )

    objective = guided_objective(resources)

    assert "proxmox" in objective
    assert "pve-1" in objective


def test_the_guided_objective_refuses_when_nothing_is_connected() -> None:
    with pytest.raises(ValueError, match="nothing to investigate"):
        guided_objective(())


def test_a_transcript_reads_as_a_sequence_of_turns_a_person_can_follow() -> None:
    """FR-014. "Readable" is a property of the rendering, so it is asserted on
    the rendering rather than on the existence of a trace."""
    run = AgentRun(
        run_id="run-1",
        trigger=GUIDED_INVESTIGATION_TRIGGER,
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        summary="pve-1 is out of memory",
    )
    turns = (
        TurnRecord(
            turn_id="t1",
            run_id="run-1",
            index=0,
            payload={"thought": "check the node's memory", "text": "reading node status"},
        ),
        TurnRecord(
            turn_id="t2",
            run_id="run-1",
            index=1,
            payload={"text": "the node reports 98% memory used"},
        ),
    )

    transcript = readable_transcript(run, turns)

    assert "pve-1 is out of memory" in transcript
    assert "reading node status" in transcript
    assert "98% memory used" in transcript
    assert transcript.index("reading node status") < transcript.index("98% memory used")


def test_a_run_with_no_turns_still_renders_rather_than_producing_an_empty_string() -> None:
    run = AgentRun(run_id="run-1", trigger=GUIDED_INVESTIGATION_TRIGGER, status=RunStatus.FAILED)

    transcript = readable_transcript(run, ())

    assert "run-1" in transcript
    assert "failed" in transcript.lower()


# --- The investigation runtime ---------------------------------------------------


async def test_the_runtime_step_is_outstanding_when_nothing_is_composed(
    store: FakePersistence,
) -> None:
    """The step that exists because this is the one nothing else would show.

    A deployment whose account, provider, model and estate are all in place looks
    finished from every screen in the console — right up to the moment somebody
    presses Investigate and the run fails before it starts. Every other step
    leaves a trace an operator can go and look at; this one does not, which is
    exactly why the checklist has to carry it.
    """
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_INVESTIGATION_RUNTIME).state != SETUP_STATE_DONE
    assert _step(checklist, SETUP_STEP_INVESTIGATION_RUNTIME).action


async def test_the_runtime_step_never_names_a_setting_of_the_process(
    store: FakePersistence,
) -> None:
    """The refusal an operator used to get named an environment variable.

    The console reads this document. A step whose text is a deploy instruction
    puts the same sentence back on the screen this whole feature exists to keep
    it off.
    """
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    step = _step(checklist, SETUP_STEP_INVESTIGATION_RUNTIME)
    assert "NINJASRE_" not in step.detail
    assert "NINJASRE_" not in step.action


async def test_a_composed_runtime_completes_the_step(store: FakePersistence) -> None:
    checklist = await build_checklist(
        store, organisation_id=DEFAULT_ORGANISATION_ID, runtime_composed=True
    )

    assert _step(checklist, SETUP_STEP_INVESTIGATION_RUNTIME).state == SETUP_STATE_DONE


async def test_the_first_investigation_waits_on_the_runtime_rather_than_on_the_estate(
    store: FakePersistence,
) -> None:
    """Ordering, and it is the ordering that stops the checklist lying.

    Telling somebody to run their first investigation on a deployment with no
    runtime is telling them to press a button that cannot work. The step is
    blocked until the thing that would run it exists.
    """
    checklist = await build_checklist(store, organisation_id=DEFAULT_ORGANISATION_ID)

    assert _step(checklist, SETUP_STEP_FIRST_INVESTIGATION).state == SETUP_STATE_BLOCKED
