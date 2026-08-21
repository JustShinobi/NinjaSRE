"""``ReActInvestigationRunner`` composes the canonical loop, and only that loop.

Three things this file proves, each with its own assertion rather than one
assertion standing in for all three:

- the object driving one investigation is ``core.agent.react_loop.ReActLoop``
  itself — the loop Article V reserves for published numbers — not an
  adapter that merely behaves like it;
- the bounds that loop enforces (the tool-schema ceiling, the iteration and
  wall-clock ceilings) are the named constants on the composed object, not
  merely present somewhere;
- steering a running investigation (cancel, take-over, a queued message)
  reaches the same loop instance this runner tracked for that run's id.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from capabilities.registry.catalogue import Registry
from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MAX_INVESTIGATION_LOOPS,
    RUN_WALL_CLOCK_SECONDS,
)
from core.agent.react_loop import CANONICAL_RUNTIME_NAME, ReActLoop
from core.agent.runtime_port import RunResult, RunStatus
from core.agent.session import Session
from gateway.http.services import InvestigationStart
from gateway.runtime.investigator import (
    InvestigationDidNotComplete,
    NoPendingInteraction,
    ReActInvestigationRunner,
    _LiveRun,
)
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentSubject,
    PersistenceGateway,
    TenantScope,
    TimelineKind,
)
from tests.unit.gateway.runtime.conftest import ScriptedLLM, failed_turn, fixture_tool, text_turn

pytestmark = pytest.mark.unit


def _registry(*names: str) -> Registry:
    return Registry(tools={name: fixture_tool(name) for name in names})


def _request(run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="disk on host-1 is at 98%",
        team_node_id="platform",
        principal_id="operator-1",
        alert_source="prometheus",
    )


# -- T016: the composed runtime is the canonical loop, and its bounds hold ----


class TestComposesTheCanonicalLoop:
    def test_the_object_built_per_investigation_is_the_canonical_loop(self) -> None:
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([text_turn("no evidence gathered")]),
            registry=_registry("fixture_probe"),
        )

        built = runner._build_runtime(_request(), messages=None)  # type: ignore[arg-type]

        assert isinstance(built, ReActLoop)
        assert built.is_canonical is True
        assert built.name == CANONICAL_RUNTIME_NAME

    def test_a_second_investigation_composes_its_own_loop_not_a_shared_one(self) -> None:
        """Proves the loop is built fresh, not reused across investigations.

        A shared loop would carry one investigation's tool set into another's,
        which is exactly the wrong thing when tool selection is scored per
        alert.
        """
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([text_turn("x")]), registry=_registry("fixture_probe")
        )

        first = runner._build_runtime(_request("run-a"), messages=None)  # type: ignore[arg-type]
        second = runner._build_runtime(_request("run-b"), messages=None)  # type: ignore[arg-type]

        assert first is not second

    def test_the_tool_schema_ceiling_is_the_named_constant_not_merely_respected(self) -> None:
        """The composed object is capped at exactly ``MAX_AGENT_TOOL_SCHEMAS``.

        The registry here declares more than the ceiling on purpose, so a
        selection that forgot to cap would be caught rather than passing by
        coincidence because nobody wrote a large enough fixture.
        """
        names = [f"fixture_tool_{index}" for index in range(MAX_AGENT_TOOL_SCHEMAS + 15)]
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([text_turn("x")]), registry=_registry(*names)
        )

        selected = runner._select_tools(_request())

        assert len(selected) == MAX_AGENT_TOOL_SCHEMAS

    def test_the_loops_own_guard_is_what_the_cap_relies_on(self) -> None:
        """The ceiling is a real refusal on ``ReActLoop`` itself, not a convention.

        Regression insurance: if ``ReActLoop`` ever stopped enforcing its own
        ceiling, a selection bug here would start reaching a live model with
        too many tool schemas instead of failing loudly at construction.
        """
        too_many = tuple(
            fixture_tool(f"fixture_overflow_{i}") for i in range(MAX_AGENT_TOOL_SCHEMAS + 1)
        )

        with pytest.raises(ValueError, match="tool schemas"):
            ReActLoop(llm=ScriptedLLM([text_turn("x")]), tools=too_many)

    def test_the_run_request_carries_the_iteration_and_wall_clock_ceilings(self) -> None:
        """The composed request asks for the full ceiling, never a private smaller one."""
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        built = runner._request_of(_request())

        assert built.max_iterations == MAX_INVESTIGATION_LOOPS
        assert built.wall_clock_seconds == RUN_WALL_CLOCK_SECONDS

    def test_the_run_request_carries_this_runs_own_identity(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        built = runner._request_of(_request("run-xyz"))

        assert built.session_id == "run-xyz"


# -- T015: investigate() actually drives the loop to a real outcome ----------


class TestInvestigate:
    async def test_a_completed_run_returns_the_loops_own_answer(self) -> None:
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([text_turn("diagnosis: disk on host-1 is full")]),
            registry=_registry("fixture_probe"),
        )

        summary = await runner.investigate(_request())

        assert summary == "diagnosis: disk on host-1 is full"

    async def test_a_run_where_every_turn_errors_is_reported_degraded_not_raised(self) -> None:
        """The edge case for a degraded provider: two claims, not one.

        Every turn the loop tries comes back as a soft provider failure — the
        shape a real outage produces, not a raised exception. The canonical
        loop's own answer to "nothing landed" is ``PARTIAL`` ("the evidence
        gathered so far is intact"), and the edge case asks this composition
        for two separate things: report it as a completion rather than a
        failure (so this must return normally rather than raise), and name
        the degradation with the product's own canonical word rather than
        leaving a reader to infer it from a sentence that never uses it. An
        assertion that only checked the return type would pass equally
        against a summary that never mentioned the degradation at all — which
        is exactly what this composition did before this test asserted the
        word.
        """
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([failed_turn()], repeat_last=True),
            registry=_registry("fixture_probe"),
        )

        summary = await runner.investigate(_request())

        assert isinstance(summary, str)  # returned, not raised — not refused
        assert "degraded" in summary.lower(), (
            f"the canonical word for this outcome must be named, not implied: {summary!r}"
        )

    async def test_a_runtime_reported_as_failed_raises_rather_than_reads_as_completed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run that produced nothing must not read as completed.

        ``gateway.http.orchestration._drive`` marks a run ``COMPLETED`` on any
        normal return and ``FAILED`` only on a raise — so an ``investigate``
        that turned a ``FAILED`` ``RunResult`` into a plain string would let a
        run that produced nothing usable be recorded, and later shown, as
        done. ``ReActLoop`` itself never reaches this status (a fully
        degraded run is ``PARTIAL``, covered above) — the port declares it for
        every ``Runtime``, so this drives the same composed object through a
        stubbed outcome rather than asserting behaviour no fixture can coax
        out of the canonical loop.
        """
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        class _FailingLoop:
            is_canonical = True

            async def run(self, request: object) -> RunResult:
                return RunResult(
                    session=_session("run-1"), status=RunStatus.FAILED, failure="no evidence at all"
                )

        monkeypatch.setattr(
            ReActInvestigationRunner, "_build_runtime", lambda *_args, **_kwargs: _FailingLoop()
        )

        with pytest.raises(InvestigationDidNotComplete, match="no evidence at all"):
            await runner.investigate(_request())


# -- Steering reaches the tracked loop for that run's id ----------------------


class _RecordingLoop:
    """Records what it was asked to do, standing in for a live ``ReActLoop``."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.paused: list[str] = []
        self.resumed: list[Session] = []

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def pause(self, session_id: str) -> None:
        self.paused.append(session_id)

    async def resume(self, session: Session) -> RunResult:
        self.resumed.append(session)
        return RunResult(session=session, status=RunStatus.COMPLETED, answer="resumed and done")


def _session(run_id: str) -> Session:
    return Session(id=run_id, objective="x", system_prompt="x")


class TestSteeringReachesTheTrackedRun:
    async def test_cancel_reaches_the_loop_tracked_for_that_run(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())
        loop = _RecordingLoop()
        runner._live["run-1"] = _LiveRun(loop=loop, messages=None)  # type: ignore[arg-type]

        await runner.cancel("run-1")

        assert loop.cancelled == ["run-1"]

    async def test_cancel_on_an_untracked_run_is_a_quiet_no_op(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        await runner.cancel("no-such-run")  # must not raise

    async def test_take_over_pauses_the_loop_tracked_for_that_run(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())
        loop = _RecordingLoop()
        runner._live["run-1"] = _LiveRun(loop=loop, messages=None)  # type: ignore[arg-type]

        await runner.take_over("run-1", principal="operator-1")

        assert loop.paused == ["run-1"]

    async def test_resume_hands_the_saved_session_back_to_the_same_loop(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())
        loop = _RecordingLoop()
        session = _session("run-1")
        runner._live["run-1"] = _LiveRun(loop=loop, messages=None, session=session)  # type: ignore[arg-type]

        await runner.resume("run-1")

        assert loop.resumed == [session]

    async def test_resume_without_a_prior_take_over_is_a_quiet_no_op(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())
        loop = _RecordingLoop()
        runner._live["run-1"] = _LiveRun(loop=loop, messages=None)  # type: ignore[arg-type]

        await runner.resume("run-1")  # nothing was taken over

        assert loop.resumed == []

    async def test_queue_message_reaches_the_queue_built_for_that_run(self) -> None:
        from core.agent.message_queue import MessageQueue

        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())
        queue = MessageQueue(run_id="run-1")
        runner._live["run-1"] = _LiveRun(loop=_RecordingLoop(), messages=queue)  # type: ignore[arg-type]

        await runner.queue_message("run-1", "the on-call already restarted the service")

        pending = queue.drain_now()
        assert [message.text for message in pending] == [
            "the on-call already restarted the service"
        ]


# -- Interactions: honestly absent, not silently faked -----------------------


class TestInteractionsAreHonestlyAbsent:
    async def test_no_interaction_is_ever_pending(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        assert await runner.pending_interactions("run-1") == ()

    async def test_no_interaction_can_be_found_by_id(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        assert await runner.find_interaction("interaction-1") is None

    async def test_answering_a_non_existent_interaction_is_refused_not_faked(self) -> None:
        runner = ReActInvestigationRunner(llm=ScriptedLLM([text_turn("x")]), registry=_registry())

        with pytest.raises(NoPendingInteraction):
            await runner.answer_interaction(
                "interaction-1", text="approved", principal="operator-1"
            )


# -- A real run records receipt, when given somewhere to write it ------------


@pytest.fixture
async def gateway() -> PersistenceGateway:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


def _epoch() -> datetime:
    return datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _a_raise() -> IncidentRaise:
    return IncidentRaise(
        correlation_key="alert:instance-down:host-1",
        title="InstanceDown",
        summary="host-1 stopped responding to scrapes",
        origin=IncidentOrigin.ALERT,
        origin_id="alertmanager",
        severity="critical",
        subjects=(IncidentSubject(resource_id="host-1", detail="down"),),
    )


class TestRecordsReceiptWhenComposedWithAnIncidentLifecycle:
    """Receipt recording, wired into a real ``investigate()`` call rather than proven in isolation.

    ``ReActInvestigationRunner.incidents`` and ``InvestigationStart``'s
    ``incident_id``/``alert_labels``/``credential_name`` are all optional —
    every test above this class, none of which sets any of them, keeps
    passing unchanged (proven by running this whole file, not asserted
    here). This class is the proof that when they *are* given, a real run —
    a real ``ReActLoop``, stubbed only at the model boundary, exactly like
    every other test in this file — writes a real receipt entry onto the
    named incident's own timeline.
    """

    async def test_a_run_started_with_an_incident_records_its_receipt(
        self, gateway: PersistenceGateway
    ) -> None:
        async with gateway.begin(TenantScope(org_id="acme")) as uow:
            lifecycle = IncidentLifecycle(store=uow.incidents)
            incident = await lifecycle.raise_incident(_a_raise(), now=_epoch())

            runner = ReActInvestigationRunner(
                llm=ScriptedLLM([text_turn("no evidence gathered")]),
                registry=_registry("fixture_probe"),
                incidents=lifecycle,
            )
            request = InvestigationStart(
                run_id="run-1",
                objective="disk on host-1 is at 98%",
                team_node_id="platform",
                principal_id="operator-1",
                alert_source="prometheus",
                incident_id=incident.incident_id,
                alert_labels={"alertname": "InstanceDown", "severity": "critical"},
                credential_name="delivery token am-cluster",
            )

            await runner.investigate(request)

            history = await lifecycle.timeline(incident.incident_id)

        receipts = [item for item in history if item.kind is TimelineKind.ALERT_RECEIVED]
        assert len(receipts) == 1
        assert "am-cluster" in receipts[0].cause
        assert "alertname=InstanceDown" in receipts[0].detail

    async def test_without_a_credential_name_nothing_is_recorded_and_the_run_still_completes(
        self, gateway: PersistenceGateway
    ) -> None:
        """An operator-triggered investigation has no delivery to name.

        A silent no-op rather than a refusal: ``record_alert_received``
        itself requires a credential name (``record_alert_received``'s own guard), and an
        investigation with nothing to name there must still complete.
        """
        async with gateway.begin(TenantScope(org_id="acme")) as uow:
            lifecycle = IncidentLifecycle(store=uow.incidents)
            incident = await lifecycle.raise_incident(_a_raise(), now=_epoch())

            runner = ReActInvestigationRunner(
                llm=ScriptedLLM([text_turn("no evidence gathered")]),
                registry=_registry("fixture_probe"),
                incidents=lifecycle,
            )
            request = InvestigationStart(
                run_id="run-1",
                objective="disk on host-1 is at 98%",
                team_node_id="platform",
                principal_id="operator-1",
                incident_id=incident.incident_id,
                # alert_labels and credential_name are left at their defaults.
            )

            summary = await runner.investigate(request)

            history = await lifecycle.timeline(incident.incident_id)

        assert summary == "no evidence gathered"
        assert not any(item.kind is TimelineKind.ALERT_RECEIVED for item in history)

    async def test_without_an_incidents_collaborator_composed_nothing_is_recorded(self) -> None:
        """Today's actual composition: no persistence handle, so no recording — and no error.

        ``gateway.runtime.factory.build_investigator`` does not compose
        ``incidents`` yet (see this feature's report); this is the honest
        characterisation of what that means for a real run today.
        """
        runner = ReActInvestigationRunner(
            llm=ScriptedLLM([text_turn("no evidence gathered")]),
            registry=_registry("fixture_probe"),
        )
        request = InvestigationStart(
            run_id="run-1",
            objective="disk on host-1 is at 98%",
            team_node_id="platform",
            principal_id="operator-1",
            incident_id="inc-1",
            alert_labels={"alertname": "InstanceDown"},
            credential_name="delivery token am-cluster",
        )

        summary = await runner.investigate(request)  # must not raise despite no `incidents`

        assert summary == "no evidence gathered"
