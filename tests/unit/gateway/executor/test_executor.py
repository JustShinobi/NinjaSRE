"""The service that holds the SSH identity the agent is forbidden to hold.

Article IV keeps credentials out of the agent's process. An SSH key is a
credential and SSH is not an HTTP request the credential proxy can inject into,
so the key lives here, in a process the agent reaches by name over HTTP and
never by command.

That relocation is worth nothing on its own — an executor that ran whatever it
was asked would be the same authority in a different process. What makes it a
boundary is that every request is resolved against the declared command list
before anything runs, and the transport is handed a vector rather than a string.

So the properties under test are the refusals, and one more that is easy to lose:
**a failed command is a result, not an exception.** A unit that would not restart
is a finding an investigation reasons about; a transport that could not connect
is a different one; and collapsing either into a stack trace loses which happened.
"""

from __future__ import annotations

import pytest

from gateway.executor.service import ExecutionRequest, Executor

pytestmark = pytest.mark.unit


class _Runner:
    """A transport that records the vector it was handed."""

    def __init__(self, *, code: int = 0, out: str = "ok", err: str = "") -> None:
        self.code = code
        self.out = out
        self.err = err
        self.ran: list[tuple[str, list[str]]] = []

    async def run(
        self, *, node: str, argv: list[str], timeout_seconds: float
    ) -> tuple[int, str, str]:
        del timeout_seconds
        self.ran.append((node, argv))
        return self.code, self.out, self.err


async def test_a_declared_read_reaches_the_transport_as_a_vector() -> None:
    runner = _Runner(out="nginx.service failed")

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="failed-units")
    )

    assert result.succeeded
    assert result.stdout == "nginx.service failed"
    node, argv = runner.ran[0]
    assert node == "pve01"
    assert argv[0] == "systemctl"


async def test_a_command_nobody_declared_never_reaches_the_transport() -> None:
    """The refusal has to happen before the transport, or the boundary is the
    transport's own judgement rather than the declared list."""
    runner = _Runner()

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="curl-something")
    )

    assert not result.succeeded
    assert result.refused
    assert runner.ran == []


async def test_an_argument_carrying_a_shell_never_reaches_the_transport() -> None:
    runner = _Runner()

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="guest-status", arguments={"vmid": "1; id"})
    )

    assert result.refused
    assert runner.ran == []


async def test_a_write_is_refused_unless_the_caller_asked_for_one() -> None:
    """A caller that did not say it was making a change does not get to make one
    by naming a command that happens to be a write."""
    runner = _Runner()

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(
            node="pve01", command_id="restart-unit", arguments={"unit": "pve-cluster.service"}
        )
    )

    assert result.refused
    assert runner.ran == []


async def test_a_write_runs_when_the_caller_declared_it_intends_one() -> None:
    runner = _Runner()

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(
            node="pve01",
            command_id="restart-unit",
            arguments={"unit": "pve-cluster.service"},
            intends_write=True,
        )
    )

    assert result.succeeded
    assert runner.ran[0][1] == ["systemctl", "restart", "pve-cluster.service"]


async def test_declaring_a_write_does_not_turn_a_read_into_one() -> None:
    """The flag is permission, not instruction: it must not widen what a read does."""
    runner = _Runner()

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="failed-units", intends_write=True)
    )

    assert result.succeeded
    assert runner.ran[0][1][0] == "systemctl"


async def test_a_command_that_exits_non_zero_is_a_result_rather_than_a_raise() -> None:
    """A unit that would not restart is a finding, and a finding is something an
    investigation reads rather than something that ends it."""
    runner = _Runner(code=1, out="", err="Job for nginx.service failed")

    result = await Executor(runner=runner).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="failed-units")
    )

    assert not result.succeeded
    assert not result.refused
    assert result.exit_code == 1
    assert "failed" in result.stderr


async def test_a_transport_that_could_not_connect_is_told_apart_from_a_failure() -> None:
    """Two different findings: the node said no, and nobody could ask the node."""

    class _Broken:
        async def run(
            self, *, node: str, argv: list[str], timeout_seconds: float
        ) -> tuple[int, str, str]:
            raise OSError("no route to host")

    result = await Executor(runner=_Broken()).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="failed-units")
    )

    assert not result.succeeded
    assert result.unreachable
    assert not result.refused


async def test_the_result_names_what_was_run_so_a_report_can_cite_it() -> None:
    result = await Executor(runner=_Runner()).perform(  # type: ignore[arg-type]
        ExecutionRequest(node="pve01", command_id="quorum-status")
    )

    assert result.command_id == "quorum-status"
    assert result.node == "pve01"
