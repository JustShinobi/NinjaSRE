"""The exit codes are meaningful, documented, and stable.

A CLI is scriptable when its failures are distinguishable, and that is only true
if the numbers stay put. What is asserted here is the three ways they stop
being: a code that means two things, a code with no documentation, and a
failure path that returns the wrong one.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from typer.testing import CliRunner

from config.constants.surfaces import (
    EXIT_CONFIGURATION,
    EXIT_DENIED,
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_NEEDS_APPROVAL,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    EXIT_USAGE,
)
from surfaces.cli.app import app, use_local_services
from surfaces.cli.errors import (
    EXIT_CODE_MEANINGS,
    ApprovalRequiredError,
    CliError,
    ConfigurationError,
    DeniedError,
    NotFoundError,
    UnavailableError,
    describe_exit_codes,
)
from surfaces.cli.invocation import Invocation, Output, run_command
from surfaces.cli.output.degradation import Terminal
from tests.support.deployment import FakeServices

pytestmark = pytest.mark.contract

ALL_CODES = (
    EXIT_OK,
    EXIT_FAILED,
    EXIT_USAGE,
    EXIT_CONFIGURATION,
    EXIT_NOT_FOUND,
    EXIT_DENIED,
    EXIT_UNAVAILABLE,
    EXIT_NEEDS_APPROVAL,
    EXIT_INTERRUPTED,
)


def _run(services: FakeServices, arguments: Sequence[str]) -> int:
    """Run one command and return its exit code."""
    use_local_services(lambda: services)
    try:
        return CliRunner().invoke(app, list(arguments)).exit_code
    finally:
        use_local_services(None)


def test_no_two_meanings_share_a_code() -> None:
    # The property that makes a script's branch stay correct. Two failure modes
    # sharing a number makes an operator's runbook wrong in a way nothing warns
    # about.
    assert len(set(ALL_CODES)) == len(ALL_CODES)


def test_every_code_is_documented() -> None:
    undocumented = [code for code in ALL_CODES if code not in EXIT_CODE_MEANINGS]

    assert not undocumented, f"these codes have no documented meaning: {undocumented}"


def test_the_documentation_describes_no_code_that_does_not_exist() -> None:
    invented = [code for code in EXIT_CODE_MEANINGS if code not in ALL_CODES]

    assert not invented, f"documented but unused: {invented}"


def test_the_contract_is_printable() -> None:
    printed = describe_exit_codes()

    for code in ALL_CODES:
        assert str(code) in printed


def test_the_cli_prints_the_contract_on_request() -> None:
    result = CliRunner().invoke(app, ["--exit-codes"])

    assert result.exit_code == EXIT_OK
    assert str(EXIT_NEEDS_APPROVAL) in result.output


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CliError("plain"), EXIT_FAILED),
        (ConfigurationError("unset"), EXIT_CONFIGURATION),
        (NotFoundError("gone"), EXIT_NOT_FOUND),
        (DeniedError("no"), EXIT_DENIED),
        (UnavailableError("unreachable"), EXIT_UNAVAILABLE),
        (ApprovalRequiredError("gated"), EXIT_NEEDS_APPROVAL),
    ],
)
def test_each_failure_exits_with_its_own_code(error: CliError, expected: int) -> None:
    invocation = Invocation(terminal=Terminal())

    async def body() -> Output:
        raise error

    assert run_command(invocation, "runs.list", body) == expected


def test_a_successful_command_exits_zero(services: FakeServices) -> None:
    assert _run(services, ["runs", "list"]) == EXIT_OK


def test_naming_a_run_that_does_not_exist_exits_not_found(services: FakeServices) -> None:
    assert _run(services, ["runs", "show", "run-9999"]) == EXIT_NOT_FOUND


def test_removing_a_schedule_that_does_not_exist_exits_not_found(
    services: FakeServices,
) -> None:
    assert _run(services, ["schedule", "remove", "nope"]) == EXIT_NOT_FOUND


def test_no_deployment_to_talk_to_exits_generic_failure() -> None:
    # Nothing registered and no endpoint. Distinguishable from "the deployment
    # said no" and from "you named something that is not there".
    use_local_services(None)
    assert CliRunner().invoke(app, ["runs", "list"]).exit_code == EXIT_FAILED


def test_a_bad_endpoint_is_refused_before_anything_runs() -> None:
    result = CliRunner().invoke(app, ["--endpoint", "not-a-url", "runs", "list"])

    assert result.exit_code == EXIT_FAILED


def test_an_unknown_command_exits_with_the_frameworks_usage_code() -> None:
    # 2 is the framework's, which is why nothing else claims it.
    assert CliRunner().invoke(app, ["nonesuch"]).exit_code == EXIT_USAGE


def test_a_missing_required_argument_exits_with_the_usage_code() -> None:
    assert CliRunner().invoke(app, ["runs", "show"]).exit_code == EXIT_USAGE


def test_an_interrupt_exits_one_hundred_and_thirty() -> None:
    invocation = Invocation(terminal=Terminal())

    async def body() -> Output:
        raise KeyboardInterrupt

    assert run_command(invocation, "investigate", body) == EXIT_INTERRUPTED


def test_an_interrupt_runs_the_declared_cleanup_first() -> None:
    # Cancellation's CLI half: it happens before the process leaves, so a
    # run is asked to stop rather than abandoned mid-flight.
    invocation = Invocation(terminal=Terminal())
    stopped: list[str] = []

    async def body() -> Output:
        raise KeyboardInterrupt

    async def stop() -> None:
        stopped.append("cancelled")

    code = run_command(invocation, "investigate", body, on_interrupt=stop)

    assert code == EXIT_INTERRUPTED
    assert stopped == ["cancelled"]


def test_an_unexpected_exception_is_not_swallowed_into_exit_one() -> None:
    # A defect must not become "it just doesn't work". It propagates.
    invocation = Invocation(terminal=Terminal())

    async def body() -> Output:
        raise ZeroDivisionError("a real bug")

    with pytest.raises(ZeroDivisionError):
        run_command(invocation, "runs.list", body)
