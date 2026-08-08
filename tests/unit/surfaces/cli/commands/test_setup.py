"""``ninjasre setup`` — the CLI half of FR-010 and FR-022.

Driven through typer's own runner against the real command group, so what is
asserted is what an operator types and sees, not a function called directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from config.constants.first_run import NINJASRE_STATE_DIR_ENV
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.transaction import TenantScope
from platform.startup.bootstrap import bring_up
from platform.startup.diagnostics import record_failure
from platform.startup.errors import ConfigurationInvalid
from surfaces.cli import app as cli_app
from surfaces.cli.commands import setup as setup_commands
from surfaces.cli.output.schemas import COMMAND_SCHEMAS, validate
from tools.mockplane.seed import DEMONSTRATION_ORGANISATION

pytestmark = pytest.mark.unit


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePersistence]:
    """Point the command group at an in-memory deployment."""
    gateway = FakePersistence()
    monkeypatch.setattr(setup_commands, "store_factory", lambda: gateway)
    yield gateway


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "state"
    monkeypatch.setenv(NINJASRE_STATE_DIR_ENV, str(directory))
    return directory


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, *arguments: str):
    return runner.invoke(cli_app.app, list(arguments))


def _text(result: object) -> str:
    """Return everything the command wrote, whichever stream it chose.

    A failure goes to stderr and a success to stdout, and a test that read only
    one of them would pass by not looking at the half it was asserting about.
    """
    written = getattr(result, "stdout", "") or ""
    with contextlib.suppress(ValueError):  # the runner may have merged the two
        written += getattr(result, "stderr", "") or ""
    return written


# --- The published ``--json`` contract -------------------------------------------
#
# ``tests/contract/cli/test_json_output_contract.py`` exempts these six from its
# own runner, because ``FakeServices`` is a façade over a deployment and has no
# gateway to lend them. This is where that exemption is paid for: every one of
# them is driven through the real typer application and its emitted ``data`` is
# validated against the published schema, which is exactly what the contract
# suite would have done.


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("setup.self-check", ("setup", "self-check")),
        ("setup.load-demo", ("setup", "load-demo")),
        ("setup.remove-demo", ("setup", "remove-demo")),
    ],
)
def test_the_emitted_document_matches_its_published_schema(
    runner: CliRunner,
    store: FakePersistence,
    state_dir: Path,
    command: str,
    arguments: tuple[str, ...],
) -> None:
    result = _invoke(runner, "--json", *arguments)
    document = json.loads(result.stdout)

    assert document["command"] == command
    validate(document["data"], COMMAND_SCHEMAS[command])


def test_the_diagnose_document_matches_its_published_schema(
    runner: CliRunner, state_dir: Path
) -> None:
    """Driven with a failure recorded, because the payload with none is the
    empty case and validating that would leave the shape that matters
    unasserted."""
    record_failure(
        ConfigurationInvalid(
            "NINJASRE_DATABASE_URL is not set", settings=["NINJASRE_DATABASE_URL"]
        ),
        stage="validation",
    )

    result = _invoke(runner, "--json", "setup", "diagnose")
    document = json.loads(result.stdout)

    assert document["command"] == "setup.diagnose"
    validate(document["data"], COMMAND_SCHEMAS["setup.diagnose"])


def test_the_bundle_document_matches_its_published_schema(
    runner: CliRunner, store: FakePersistence, state_dir: Path, tmp_path: Path
) -> None:
    result = _invoke(runner, "--json", "setup", "bundle", "--out", str(tmp_path / "b.json"))
    document = json.loads(result.stdout)

    assert document["command"] == "setup.bundle"
    validate(document["data"], COMMAND_SCHEMAS["setup.bundle"])


def test_the_credential_document_matches_its_published_schema(
    runner: CliRunner, state_dir: Path
) -> None:
    gateway = FakePersistence()
    asyncio.run(bring_up(gateway, TokenService(gateway=gateway)))

    result = _invoke(runner, "--json", "setup", "credential")
    document = json.loads(result.stdout)

    assert document["command"] == "setup.credential"
    validate(document["data"], COMMAND_SCHEMAS["setup.credential"])


# --- The self-check ------------------------------------------------------------


def test_the_self_check_runs_from_the_command_line(
    runner: CliRunner, store: FakePersistence
) -> None:
    """FR-010's CLI entry point."""
    result = _invoke(runner, "setup", "self-check")

    assert "problem" in _text(result) or "nothing to report" in _text(result)


def test_the_self_check_reports_every_finding_with_what_to_do(
    runner: CliRunner, store: FakePersistence
) -> None:
    result = _invoke(runner, "--json", "setup", "self-check")

    payload = json.loads(result.stdout)["data"]
    assert payload["findings"]
    for finding in payload["findings"]:
        assert finding["problem"]
        assert finding["action"]


def test_a_deployment_with_a_blocking_problem_exits_non_zero(
    runner: CliRunner, store: FakePersistence
) -> None:
    """So a script that runs this before starting work actually stops."""
    result = _invoke(runner, "setup", "self-check")

    assert result.exit_code != 0


# --- Reading the credential again -------------------------------------------------


def test_the_credential_is_printed_again_without_a_restart(
    runner: CliRunner, state_dir: Path
) -> None:
    """FR-002. The operator who closed the terminal."""
    gateway = FakePersistence()
    result = asyncio.run(bring_up(gateway, TokenService(gateway=gateway)))

    printed = _invoke(runner, "setup", "credential")

    assert result.credential.secret in _text(printed)
    assert result.credential.expires_at.isoformat() in _text(printed)


def test_asking_for_a_credential_that_is_gone_says_why(runner: CliRunner, state_dir: Path) -> None:
    result = _invoke(runner, "setup", "credential")

    assert result.exit_code != 0
    assert "exchanged" in _text(result) or "brought up" in _text(result)


# --- The last bring-up failure -------------------------------------------------------


def test_the_last_bring_up_failure_is_reachable_from_the_command_line(
    runner: CliRunner, state_dir: Path
) -> None:
    """FR-022. The same message the terminal showed, an hour later."""
    record_failure(
        ConfigurationInvalid(
            "NINJASRE_DATABASE_URL is not set", settings=["NINJASRE_DATABASE_URL"]
        ),
        stage="validation",
    )

    result = _invoke(runner, "setup", "diagnose")

    assert "NINJASRE_DATABASE_URL" in _text(result)
    assert "do:" in _text(result)
    assert result.exit_code != 0


def test_a_deployment_that_started_reports_no_failure(runner: CliRunner, state_dir: Path) -> None:
    result = _invoke(runner, "setup", "diagnose")

    assert result.exit_code == 0
    assert "no bring-up failure" in _text(result)


# --- The support bundle ----------------------------------------------------------------


def test_the_bundle_is_produced_in_one_command(
    runner: CliRunner, store: FakePersistence, state_dir: Path, tmp_path: Path
) -> None:
    """T-030. One command, and the path is what it reports."""
    out = tmp_path / "bundle.json"

    result = _invoke(runner, "setup", "bundle", "--out", str(out))

    assert result.exit_code == 0
    assert out.exists()
    document = json.loads(out.read_text(encoding="utf-8"))
    assert "self_check" in document
    assert "schema_revision" in document


def test_the_bundle_command_says_nothing_was_transmitted(
    runner: CliRunner, store: FakePersistence, state_dir: Path, tmp_path: Path
) -> None:
    """Article X, said out loud where the operator is looking."""
    result = _invoke(runner, "setup", "bundle", "--out", str(tmp_path / "b.json"))

    assert "Nothing was transmitted" in _text(result)


def test_a_secret_in_the_environment_does_not_reach_the_bundle(
    runner: CliRunner,
    store: FakePersistence,
    state_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "bundle.json"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-appear")

    _invoke(runner, "setup", "bundle", "--out", str(out))

    assert "sk-ant-should-not-appear" not in out.read_text(encoding="utf-8")


# --- The demonstration -------------------------------------------------------------------


def test_the_demonstration_loads_and_removes_from_the_command_line(
    runner: CliRunner, store: FakePersistence
) -> None:
    loaded = _invoke(runner, "setup", "load-demo")
    assert loaded.exit_code == 0
    assert "demonstration data loaded" in _text(loaded)

    removed = _invoke(runner, "setup", "remove-demo")
    assert removed.exit_code == 0
    assert "removed" in _text(removed)


def test_removing_a_demonstration_that_was_never_loaded_is_not_an_error(
    runner: CliRunner, store: FakePersistence
) -> None:
    result = _invoke(runner, "setup", "remove-demo")

    assert result.exit_code == 0
    assert "nothing to remove" in _text(result)


def test_the_command_refuses_to_seed_over_real_data_and_says_how_to_override(
    runner: CliRunner, store: FakePersistence
) -> None:
    async def put_real_data() -> None:
        async with store.begin_system() as system:
            await system.orgs.create_organisation(DEMONSTRATION_ORGANISATION, "Northwind")
        async with store.begin(TenantScope(org_id=DEMONSTRATION_ORGANISATION)) as uow:
            await uow.estate.upsert(
                Resource(resource_id="real-1", kind="node", source="k8s", native_id="real-1")
            )

    asyncio.run(put_real_data())

    result = _invoke(runner, "setup", "load-demo")

    assert result.exit_code != 0
    assert "--force" in _text(result)


def test_forcing_it_seeds_anyway(runner: CliRunner, store: FakePersistence) -> None:
    async def put_real_data() -> None:
        async with store.begin_system() as system:
            await system.orgs.create_organisation(DEMONSTRATION_ORGANISATION, "Northwind")
        async with store.begin(TenantScope(org_id=DEMONSTRATION_ORGANISATION)) as uow:
            await uow.estate.upsert(
                Resource(resource_id="real-1", kind="node", source="k8s", native_id="real-1")
            )

    asyncio.run(put_real_data())

    result = _invoke(runner, "setup", "load-demo", "--force")

    assert result.exit_code == 0
