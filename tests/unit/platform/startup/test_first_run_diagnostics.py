"""Bring-up failures that survive the terminal, and a bundle with no secrets in it.

Two things, and they share a module because they share the one property that
matters: both are read by somebody who was not watching when it happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.constants.first_run import (
    BRING_UP_FAILURE_FILENAME,
    NINJASRE_STATE_DIR_ENV,
)
from platform.observability.diagnostics import REDACTED
from platform.startup.diagnostics import (
    BringUpFailure,
    forget_failure,
    last_failure,
    record_failure,
    support_bundle,
)
from platform.startup.errors import ConfigurationInvalid, SchemaIncompatible
from platform.startup.selfcheck import SelfCheckReport

pytestmark = pytest.mark.unit


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    return {NINJASRE_STATE_DIR_ENV: str(tmp_path / "state")}


# --- Failures that outlive the terminal --------------------------------------------


def test_a_failure_states_what_failed_why_and_what_to_do(environ: dict[str, str]) -> None:
    """FR-022. All three, or it is not a bring-up failure message."""
    failure = record_failure(
        SchemaIncompatible(applied="abc123", expected="def456", ahead=True),
        stage="migrations",
        environ=environ,
    )

    assert failure.stage == "migrations"
    assert failure.problem
    assert failure.action
    assert "abc123" in failure.problem or "abc123" in failure.detail


def test_a_failure_is_readable_afterwards_by_something_that_was_not_watching(
    environ: dict[str, str],
) -> None:
    """FR-022's second half: the console and the CLI reach the same message the
    terminal showed, which is the difference between a diagnosis and a rumour."""
    record_failure(
        ConfigurationInvalid(
            "NINJASRE_DATABASE_URL is not set", settings=["NINJASRE_DATABASE_URL"]
        ),
        stage="validation",
        environ=environ,
    )

    read_back = last_failure(environ)

    assert read_back is not None
    assert "NINJASRE_DATABASE_URL" in read_back.problem
    assert read_back.action


def test_there_is_no_failure_to_read_on_a_deployment_that_started(
    environ: dict[str, str],
) -> None:
    assert last_failure(environ) is None


def test_a_successful_start_clears_the_last_failure(environ: dict[str, str]) -> None:
    """Otherwise the console shows yesterday's problem to somebody whose
    deployment is working, which is worse than showing nothing."""
    record_failure(RuntimeError("the database went away"), stage="boot", environ=environ)

    forget_failure(environ)

    assert last_failure(environ) is None


def test_a_failure_that_names_a_setting_says_which_one(environ: dict[str, str]) -> None:
    failure = record_failure(
        ConfigurationInvalid(
            "NINJASRE_DATABASE_ENCRYPTION_KEY is not 32 bytes",
            settings=["NINJASRE_DATABASE_ENCRYPTION_KEY"],
        ),
        stage="validation",
        environ=environ,
    )

    assert "NINJASRE_DATABASE_ENCRYPTION_KEY" in failure.settings


def test_an_unexpected_failure_still_carries_an_action(environ: dict[str, str]) -> None:
    """The interesting case. A known startup error has a remedy written for it;
    an arbitrary exception does not, and reporting it without one would be
    exactly the bare failure FR-022 exists to rule out."""
    failure = record_failure(ZeroDivisionError("division by zero"), stage="boot", environ=environ)

    assert failure.problem
    assert failure.action
    assert "support bundle" in failure.action or "self-check" in failure.action


def test_a_failure_round_trips_through_its_record() -> None:
    failure = BringUpFailure(
        stage="boot",
        problem="it broke",
        action="fix it",
        detail="ZeroDivisionError",
        settings=("X",),
        occurred_at="2026-08-08T12:00:00+00:00",
    )

    assert BringUpFailure.from_record(failure.to_record()) == failure


# --- The support bundle ------------------------------------------------------------


def test_a_setting_that_carries_a_secret_is_reported_as_redacted(
    environ: dict[str, str],
) -> None:
    """T-030's half that matters, asserted through the bundle this feature ships
    rather than through a second redaction it does not."""
    bundle = support_bundle(
        environ={
            **environ,
            "NINJASRE_DEPLOYMENT_PROFILE": "standard",
            "ANTHROPIC_API_KEY": "sk-ant-do-not-print-this",
            "NINJASRE_ADMIN_TOKEN": "nsr_secret",
            "NINJASRE_CREDENTIAL_PROXY_TOKEN": "proxy-secret",
        },
        self_check=SelfCheckReport(),
        logs=(),
        schema_revision="",
    )
    settings = bundle.settings

    assert settings["NINJASRE_DEPLOYMENT_PROFILE"] == "standard"
    assert settings["ANTHROPIC_API_KEY"] == REDACTED
    assert settings["NINJASRE_ADMIN_TOKEN"] == REDACTED
    assert settings["NINJASRE_CREDENTIAL_PROXY_TOKEN"] == REDACTED


def test_a_setting_nobody_documented_is_absent_rather_than_filtered(
    environ: dict[str, str],
) -> None:
    """The allow-list is the stronger of the two controls, and it is the one
    that keeps holding when somebody exports a cloud credential into the same
    shell tomorrow."""
    bundle = support_bundle(
        environ={**environ, "SOME_OTHER_CLOUD_TOKEN": "not-ours-and-not-documented"},
        self_check=SelfCheckReport(),
        logs=(),
        schema_revision="",
    )

    assert "SOME_OTHER_CLOUD_TOKEN" not in bundle.settings


def test_no_secret_value_survives_the_whole_bundle(environ: dict[str, str]) -> None:
    """Swept over the serialised bundle rather than over the settings map: a
    secret copied into a log line or an error message is still a secret in the
    file the operator is about to email somebody."""
    secret = "sk-ant-0123456789abcdef"
    bundle = support_bundle(
        environ={**environ, "ANTHROPIC_API_KEY": secret},
        self_check=SelfCheckReport(),
        logs=(f"provider call failed with key {secret}",),
        schema_revision="abc123",
    )

    assert secret not in json.dumps(bundle.to_record())


def test_the_bundle_carries_what_somebody_debugging_actually_needs(
    environ: dict[str, str],
) -> None:
    bundle = support_bundle(
        environ=environ,
        self_check=SelfCheckReport(),
        logs=("started", "ready"),
        schema_revision="abc123",
    )
    record = bundle.to_record()

    assert record["version"]
    assert record["schema_revision"] == "abc123"
    assert record["self_check"] is not None
    assert record["logs"] == ["started", "ready"]
    assert record["settings"]


def test_the_bundle_bounds_how_much_log_it_carries(environ: dict[str, str]) -> None:
    """A bundle an operator cannot read before sharing is one they share
    unread."""
    from config.constants.first_run import SUPPORT_BUNDLE_LOG_LINES

    bundle = support_bundle(
        environ=environ,
        self_check=SelfCheckReport(),
        logs=tuple(f"line {index}" for index in range(SUPPORT_BUNDLE_LOG_LINES * 3)),
        schema_revision="abc123",
    )

    assert len(bundle.logs) == SUPPORT_BUNDLE_LOG_LINES
    # The last lines, not the first: what happened before the failure is what
    # matters, and the first 500 lines of a container's life are the same
    # every time.
    assert bundle.logs[-1] == f"line {SUPPORT_BUNDLE_LOG_LINES * 3 - 1}"


def test_the_bundle_carries_the_last_bring_up_failure_when_there_was_one(
    environ: dict[str, str],
) -> None:
    record_failure(RuntimeError("the database went away"), stage="boot", environ=environ)

    bundle = support_bundle(
        environ=environ, self_check=SelfCheckReport(), logs=(), schema_revision=""
    )

    assert bundle.failure is not None
    assert bundle.failure.stage == "boot"


def test_writing_the_bundle_puts_it_where_the_operator_was_told(
    environ: dict[str, str], tmp_path: Path
) -> None:
    bundle = support_bundle(
        environ=environ, self_check=SelfCheckReport(), logs=(), schema_revision=""
    )

    path = bundle.write(tmp_path / "bundle.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["version"]


def test_the_bundle_is_written_owner_only(environ: dict[str, str], tmp_path: Path) -> None:
    """Redacted is not the same as harmless: it still carries a node inventory
    and whatever a vendor put in an error message."""
    bundle = support_bundle(
        environ=environ, self_check=SelfCheckReport(), logs=(), schema_revision=""
    )

    path = bundle.write(tmp_path / "bundle.json")

    assert path.stat().st_mode & 0o777 == 0o600


def test_the_bundle_is_a_local_file_and_nothing_transmits_it(
    environ: dict[str, str], tmp_path: Path
) -> None:
    """Article X, stated as a test because the obvious next feature is to add an
    upload."""
    bundle = support_bundle(
        environ=environ, self_check=SelfCheckReport(), logs=(), schema_revision=""
    )

    assert not hasattr(bundle, "upload")
    assert not hasattr(bundle, "send")
    assert isinstance(bundle.write(tmp_path / "b.json"), Path)


def test_a_bundle_reports_the_self_check_it_was_given(environ: dict[str, str]) -> None:
    from config.constants.first_run import BLOCKS_EVERYTHING, CHECK_DATABASE
    from platform.startup.selfcheck import Finding

    report = SelfCheckReport(
        findings=(
            Finding(
                check=CHECK_DATABASE,
                problem="the database did not answer",
                action="start PostgreSQL",
                blocks=BLOCKS_EVERYTHING,
            ),
        )
    )

    bundle = support_bundle(environ=environ, self_check=report, logs=(), schema_revision="")

    assert bundle.to_record()["self_check"]["findings"][0]["action"] == "start PostgreSQL"


def test_the_failure_file_lands_in_the_state_directory(environ: dict[str, str]) -> None:
    record_failure(RuntimeError("boom"), stage="boot", environ=environ)

    path = Path(environ[NINJASRE_STATE_DIR_ENV]) / BRING_UP_FAILURE_FILENAME
    assert path.exists()
