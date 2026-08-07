"""What Ctrl+C does, and what happens with nobody attached.

The two things that make a REPL usable during an incident and are impossible to
notice in review.

**Ctrl+C cancels the investigation, not the session.** Including mid-sub-agent,
which is the case the specification calls out because it is the one where a
naive implementation loses the most: a sub-agent dispatch is a nested loop, and
a signal that unwound it would strand its parent.

**Without a terminal it exits saying so.** A REPL that blocked on a closed
stdin turns a CI job into a timeout with no signal at all.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from config.constants.surfaces import EXIT_OK, EXIT_UNAVAILABLE
from core.pipeline.streaming import PipelineEvent, PipelineEventKind
from surfaces.cli.client import LocalClient
from surfaces.cli.invocation import Invocation
from surfaces.cli.output.degradation import Terminal
from surfaces.repl.commands import build_registry
from surfaces.repl.input import InputClosed, Reader
from surfaces.repl.loop import NO_TTY_MESSAGE, Repl, start
from surfaces.repl.session import ReplSession, SessionStore
from surfaces.repl.streaming import StreamRenderer
from tests.support.deployment import FakeServices

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class ScriptedReader(Reader):
    """Returns prepared lines, and raises what it was told to raise."""

    lines: list[object] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Deliberately not building a prompt_toolkit session. This reader is
        # the whole input path for the test.
        pass

    def read(self, prompt: str = "") -> str:
        if not self.lines:
            raise InputClosed
        nxt = self.lines.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return str(nxt)

    def remember(self, line: str) -> None:
        return None


@dataclass(slots=True)
class RecordingDriver:
    """A runtime that records what it was asked to do, and can be interrupted."""

    events: list[PipelineEvent] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    #: Raised from ``drain`` on the next call. What a Ctrl+C looks like from
    #: inside a running investigation.
    interrupt_on_drain: bool = False
    #: The event drained before the interrupt. Set to a sub-agent start so the
    #: interrupted run is interrupted mid-dispatch, which is the hard case.
    drained: list[PipelineEvent] = field(default_factory=list)

    async def start(self, session: ReplSession, objective: str) -> str:
        return "run-0001"

    async def drain(self, run_id: str, renderer: StreamRenderer) -> None:
        for event in self.events:
            renderer.handle(event)
            self.drained.append(event)
            if self.interrupt_on_drain and event.kind is PipelineEventKind.SUBAGENT_START:
                raise KeyboardInterrupt
        renderer.handle(
            PipelineEvent(kind=PipelineEventKind.RESULT, run_id=run_id, text="the pool was halved")
        )

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    async def finish(self, session: ReplSession, run_id: str) -> None:
        self.finished.append(run_id)


def _repl(
    reader: ScriptedReader,
    driver: RecordingDriver | None,
    services: FakeServices,
    tmp_path: Path,
) -> Repl:
    """Return a REPL wired to the scripted reader and driver."""
    out = io.StringIO()
    invocation = Invocation(terminal=Terminal(interactive=True, piped=False), out=out, err=out)
    invocation.with_client(LocalClient(services=services))
    return Repl(
        invocation=invocation,
        reader=reader,
        registry=build_registry(),
        session=ReplSession(session_id="sess-1"),
        sessions=SessionStore(directory=tmp_path / "sessions"),
        driver=driver,
        principal_id="alex",
    )


def test_without_a_terminal_it_exits_saying_so() -> None:
    out = io.StringIO()
    invocation = Invocation(terminal=Terminal(interactive=False, piped=True), out=out, err=out)

    code = start(invocation)

    assert code == EXIT_UNAVAILABLE
    assert "needs a terminal" in out.getvalue()
    # And it says what to run instead, rather than only that this will not work.
    assert "investigate" in out.getvalue()


def test_the_no_tty_message_names_a_next_step() -> None:
    assert "ninjasre investigate" in NO_TTY_MESSAGE
    assert "--help" in NO_TTY_MESSAGE


def test_control_c_mid_investigation_cancels_the_run_and_keeps_the_session(
    services: FakeServices, tmp_path: Path
) -> None:
    driver = RecordingDriver(
        events=[
            PipelineEvent(kind=PipelineEventKind.THOUGHT, text="checking the deploy"),
            PipelineEvent(kind=PipelineEventKind.SUBAGENT_START, subagent="log-reader"),
        ],
        interrupt_on_drain=True,
    )
    reader = ScriptedReader(lines=["checkout latency doubled", "/status"])
    repl = _repl(reader, driver, services, tmp_path)

    code = repl.run()

    # The run was asked to stop, through the runtime rather than by a signal.
    assert driver.cancelled == ["run-0001"]
    # And the session survived it: the next line was still read and handled.
    assert code == EXIT_OK
    assert "Status" in repl.invocation.out.getvalue()  # type: ignore[union-attr]


def test_the_interrupt_lands_during_a_sub_agent_dispatch(
    services: FakeServices, tmp_path: Path
) -> None:
    # The case worth naming: the interrupt arrives with a
    # sub-agent open, and what stops is the run rather than the process.
    driver = RecordingDriver(
        events=[PipelineEvent(kind=PipelineEventKind.SUBAGENT_START, subagent="log-reader")],
        interrupt_on_drain=True,
    )
    repl = _repl(ScriptedReader(lines=["look at the logs"]), driver, services, tmp_path)

    repl.run()

    assert driver.drained[-1].kind is PipelineEventKind.SUBAGENT_START
    assert driver.cancelled == ["run-0001"]
    assert driver.finished == [], "a cancelled run must not be finished as if it completed"


def test_the_transcript_survives_a_cancellation(services: FakeServices, tmp_path: Path) -> None:
    driver = RecordingDriver(
        events=[PipelineEvent(kind=PipelineEventKind.SUBAGENT_START, subagent="log-reader")],
        interrupt_on_drain=True,
    )
    repl = _repl(ScriptedReader(lines=["checkout is slow"]), driver, services, tmp_path)

    repl.run()

    assert [exchange.text for exchange in repl.session.transcript] == ["checkout is slow"]
    stored = SessionStore(directory=tmp_path / "sessions").load("sess-1")
    assert stored is not None
    assert len(stored.transcript) == 1


def test_control_c_at_an_idle_prompt_does_not_end_the_session(
    services: FakeServices, tmp_path: Path
) -> None:
    # Muscle memory. Ctrl+C at a prompt clears the line, as every shell does.
    reader = ScriptedReader(lines=[KeyboardInterrupt(), "/status", "/exit"])
    repl = _repl(reader, None, services, tmp_path)

    code = repl.run()

    assert code == EXIT_OK
    assert "Status" in repl.invocation.out.getvalue()  # type: ignore[union-attr]


def test_control_d_ends_the_session_without_cancelling_anything(
    services: FakeServices, tmp_path: Path
) -> None:
    # "I am finished" is not "stop what you are doing".
    driver = RecordingDriver()
    reader = ScriptedReader(lines=[InputClosed()])
    repl = _repl(reader, driver, services, tmp_path)

    assert repl.run() == EXIT_OK
    assert driver.cancelled == []


def test_a_completed_investigation_records_its_result_and_evidence(
    services: FakeServices, tmp_path: Path
) -> None:
    driver = RecordingDriver(
        events=[
            PipelineEvent(kind=PipelineEventKind.EVIDENCE, evidence_id="ev-1"),
            PipelineEvent(kind=PipelineEventKind.EVIDENCE, evidence_id="ev-2"),
        ]
    )
    repl = _repl(ScriptedReader(lines=["checkout is slow"]), driver, services, tmp_path)

    repl.run()

    agent_turn = repl.session.transcript[-1]
    assert agent_turn.speaker == "agent"
    assert agent_turn.text == "the pool was halved"
    assert agent_turn.evidence_ids == ("ev-1", "ev-2")
    assert driver.finished == ["run-0001"]
    assert repl.session.active_run_id == ""


def test_an_unknown_slash_command_suggests_rather_than_raises(
    services: FakeServices, tmp_path: Path
) -> None:
    repl = _repl(ScriptedReader(lines=["/statu", "/exit"]), None, services, tmp_path)

    repl.run()

    written = repl.invocation.out.getvalue()  # type: ignore[union-attr]
    assert "no such command: /statu" in written
    assert "/status" in written


def test_exit_leaves_and_saves(services: FakeServices, tmp_path: Path) -> None:
    repl = _repl(
        ScriptedReader(lines=["something happened", "/exit", "never read"]),
        None,
        services,
        tmp_path,
    )

    repl.run()

    stored = SessionStore(directory=tmp_path / "sessions").load("sess-1")
    assert stored is not None
    assert stored.objective == "something happened"


def test_new_swaps_the_session_and_saves_the_old_one(
    services: FakeServices, tmp_path: Path
) -> None:
    repl = _repl(ScriptedReader(lines=["first thing", "/new", "/exit"]), None, services, tmp_path)
    original = repl.session.session_id

    repl.run()

    assert repl.session.session_id != original
    assert SessionStore(directory=tmp_path / "sessions").load(original) is not None


def test_resume_brings_an_earlier_session_back(services: FakeServices, tmp_path: Path) -> None:
    store = SessionStore(directory=tmp_path / "sessions")
    earlier = ReplSession(session_id="sess-earlier", objective="yesterday's incident")
    earlier.record("human", "yesterday's incident")
    store.save(earlier)

    repl = _repl(ScriptedReader(lines=["/resume sess-earlier", "/exit"]), None, services, tmp_path)
    repl.run()

    assert repl.session.session_id == "sess-earlier"
    assert repl.session.objective == "yesterday's incident"


def test_a_line_with_no_runtime_is_still_recorded(services: FakeServices, tmp_path: Path) -> None:
    # Nothing to investigate with, but the transcript is still the record of
    # what was asked.
    repl = _repl(ScriptedReader(lines=["checkout is slow", "/exit"]), None, services, tmp_path)

    repl.run()

    assert [exchange.text for exchange in repl.session.transcript] == ["checkout is slow"]
    assert "not attached to a runtime" in repl.invocation.out.getvalue()  # type: ignore[union-attr]


def test_cancel_asks_the_runtime_rather_than_killing_anything(
    services: FakeServices, tmp_path: Path
) -> None:
    driver = RecordingDriver()
    repl = _repl(ScriptedReader(lines=["/cancel", "/exit"]), driver, services, tmp_path)
    repl.session.active_run_id = "run-0001"

    repl.run()

    assert driver.cancelled == ["run-0001"]
    assert repl.session.active_run_id == ""


def test_cancel_with_nothing_running_says_so(services: FakeServices, tmp_path: Path) -> None:
    driver = RecordingDriver()
    repl = _repl(ScriptedReader(lines=["/cancel", "/exit"]), driver, services, tmp_path)

    repl.run()

    assert driver.cancelled == []
    assert "nothing is running" in repl.invocation.out.getvalue()  # type: ignore[union-attr]
