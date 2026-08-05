"""The contract that keeps an alternative runtime from becoming load-bearing.

Article V allows other runtimes to exist and allows exactly one of them to
produce a number. The port is where that distinction is written down, so the
guard in front of the evaluation suite reads a declared property rather than
matching class names.
"""

from __future__ import annotations

import pytest

from core.agent.runtime_port import RunRequest, RunResult, RunStatus, Runtime
from core.agent.session import Session, SessionStatus

pytestmark = pytest.mark.unit


class _StubRuntime:
    """The smallest thing that satisfies the port, used to prove it is structural."""

    name = "stub"
    is_canonical = False

    async def run(self, request: RunRequest) -> RunResult:
        session = Session(id=request.session_id or "stub-run", objective=request.objective)
        session.status = SessionStatus.COMPLETED
        return RunResult(session=session, status=RunStatus.COMPLETED, answer="nothing to report")

    async def resume(self, session: Session) -> RunResult:
        return RunResult(session=session, status=RunStatus.COMPLETED)

    async def cancel(self, session_id: str) -> None:
        return None


def test_the_port_is_structural_rather_than_inherited() -> None:
    """Three declaration styles, one contract — an adapter never subclasses."""
    assert isinstance(_StubRuntime(), Runtime)


async def test_a_run_result_exposes_the_session_it_came_from() -> None:
    result = await _StubRuntime().run(RunRequest(objective="Why is checkout failing?"))

    assert result.session.objective == "Why is checkout failing?"
    assert result.status is RunStatus.COMPLETED
    assert result.iterations == 0
    assert result.evidence == ()


def test_a_partial_result_is_the_degraded_one() -> None:
    session = Session(id="run-1")

    assert RunResult(session=session, status=RunStatus.PARTIAL).degraded
    assert not RunResult(session=session, status=RunStatus.COMPLETED).degraded


def test_a_run_request_defaults_to_the_configured_iteration_ceiling() -> None:
    from config.constants.investigation import MAX_INVESTIGATION_LOOPS

    assert RunRequest(objective="x").max_iterations == MAX_INVESTIGATION_LOOPS


def test_a_run_request_refuses_an_iteration_ceiling_above_the_constant() -> None:
    """Article II is a ceiling, not a default. A caller may ask for less."""
    with pytest.raises(ValueError, match="max_iterations"):
        RunRequest(objective="x", max_iterations=10_000)
