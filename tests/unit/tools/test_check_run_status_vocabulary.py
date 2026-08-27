"""One vocabulary for a run's status, checked against the store that owns it.

Three spellings compete for one fact: the runtime's own status for how a loop
ended, the persistence store's status for where a run is, and whatever a
fixture happened to be written with. Only the store's is what the gateway
serves (``gateway/http/routes/investigations.py::summary_of`` writes
``status=run.status.value`` verbatim), so it is the one this check enforces —
both against every committed fixture and against the console's own declared
vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.check_run_status_vocabulary import (
    CONSOLE_EXCESS_RULE,
    CONSOLE_MISSING_RULE,
    FIXTURE_VALUE_RULE,
    console_vocabulary,
    domain_values,
    find_violations,
    fixture_statuses,
    main,
)

pytestmark = pytest.mark.unit


def _write(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _runs_document(*statuses: str) -> dict[str, object]:
    return {
        "slug": "runs",
        "responses": [
            {
                "body": {
                    "runs": [
                        {"run_id": f"run-{index}", "status": status}
                        for index, status in enumerate(statuses)
                    ]
                },
                "status": 200,
            }
        ],
    }


def _run_detail_document(status: str) -> dict[str, object]:
    return {
        "slug": "run-detail",
        "responses": [{"body": {"run_id": "run-0001", "status": status}, "status": 200}],
    }


def _status_module(*values: str) -> str:
    body = ",\n  ".join(f"'{value}'" for value in values)
    return (
        "export const RUN_STATUSES = [\n"
        f"  {body},\n"
        "] as const;\n\n"
        "export type RunStatus = (typeof RUN_STATUSES)[number];\n"
    )


# --- The domain enumeration ----------------------------------------------------


def test_the_domain_is_read_from_the_persistence_store_not_a_local_list() -> None:
    """A hand-kept copy here would be a fourth vocabulary to drift from."""
    from platform.persistence.ports.run_trace_store import RunStatus

    assert set(domain_values()) == {status.value for status in RunStatus}


# --- Collecting what a fixture serves -------------------------------------------


def test_collects_every_status_from_a_runs_list_fixture(tmp_path: Path) -> None:
    _write(tmp_path / "populated" / "runs.json", _runs_document("running", "succeeded"))

    found = fixture_statuses(tmp_path)

    assert [entry.value for entry in found] == ["running", "succeeded"]


def test_collects_the_status_from_a_run_detail_fixture(tmp_path: Path) -> None:
    _write(tmp_path / "populated" / "run-detail.json", _run_detail_document("awaiting_approval"))

    found = fixture_statuses(tmp_path)

    assert [entry.value for entry in found] == ["awaiting_approval"]


def test_a_tool_call_status_inside_run_threads_is_not_collected(tmp_path: Path) -> None:
    """The same word, a different fact — `succeeded` is a real `ToolCallStatus`."""
    document = {
        "slug": "run-threads",
        "responses": [
            {
                "body": {
                    "run_id": "run-0001",
                    "turns": [{"calls": [{"call_id": "call-1", "status": "succeeded"}]}],
                },
                "status": 200,
            }
        ],
    }
    _write(tmp_path / "populated" / "run-threads.json", document)

    assert fixture_statuses(tmp_path) == []


def test_a_404_stub_with_no_run_contributes_nothing(tmp_path: Path) -> None:
    document = {
        "slug": "run-detail",
        "responses": [{"body": {"detail": "nothing here yet"}, "status": 404}],
    }
    _write(tmp_path / "empty" / "run-detail.json", document)

    assert fixture_statuses(tmp_path) == []


def test_an_empty_run_list_contributes_nothing(tmp_path: Path) -> None:
    _write(tmp_path / "empty" / "runs.json", _runs_document())

    assert fixture_statuses(tmp_path) == []


def test_scans_every_scenario_directory_under_the_root(tmp_path: Path) -> None:
    _write(tmp_path / "populated" / "runs.json", _runs_document("running"))
    _write(tmp_path / "now-violations" / "runs.json", _runs_document("awaiting_approval"))

    found = {entry.value for entry in fixture_statuses(tmp_path)}

    assert found == {"running", "awaiting_approval"}


def test_a_malformed_fixture_raises_rather_than_reporting_nothing(tmp_path: Path) -> None:
    path = tmp_path / "populated" / "runs.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        fixture_statuses(tmp_path)


# --- Reading the console's declared vocabulary ----------------------------------


def test_reads_the_run_statuses_the_console_declares(tmp_path: Path) -> None:
    path = tmp_path / "status.ts"
    path.write_text(_status_module("running", "suspended", "completed"), encoding="utf-8")

    assert console_vocabulary(path) == ("running", "suspended", "completed")


def test_a_missing_declaration_raises_rather_than_reporting_an_empty_vocabulary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.ts"
    path.write_text("export const SOMETHING_ELSE = ['a'] as const;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="RUN_STATUSES"):
        console_vocabulary(path)


# --- The two-directional comparison ---------------------------------------------


def test_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    _write(fixtures_root / "populated" / "runs.json", _runs_document("running", "completed"))
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*domain_values()), encoding="utf-8")

    assert find_violations(fixtures_root, status_path) == []


def test_an_invented_fixture_value_is_named_by_file_and_value(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    _write(fixtures_root / "populated" / "runs.json", _runs_document("succeeded"))
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*domain_values()), encoding="utf-8")

    violations = find_violations(fixtures_root, status_path)

    assert len(violations) == 1
    assert violations[0].rule == FIXTURE_VALUE_RULE
    assert "succeeded" in violations[0].detail
    assert violations[0].location.endswith("runs.json")


def test_a_console_value_the_gateway_never_serves_is_named(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*domain_values(), "queued"), encoding="utf-8")

    violations = find_violations(fixtures_root, status_path)

    assert len(violations) == 1
    assert violations[0].rule == CONSOLE_EXCESS_RULE
    assert "queued" in violations[0].detail


def test_a_domain_value_the_console_fails_to_declare_is_named(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    without_interrupted = [value for value in domain_values() if value != "interrupted"]
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*without_interrupted), encoding="utf-8")

    violations = find_violations(fixtures_root, status_path)

    assert len(violations) == 1
    assert violations[0].rule == CONSOLE_MISSING_RULE
    assert "interrupted" in violations[0].detail


def test_checks_both_directions_at_once(tmp_path: Path) -> None:
    """Excess and missing are independent failures, not one masking the other."""
    fixtures_root = tmp_path / "fixtures"
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module("running", "completed", "queued"), encoding="utf-8")

    violations = find_violations(fixtures_root, status_path)
    rules = {violation.rule for violation in violations}

    assert CONSOLE_EXCESS_RULE in rules  # 'queued'
    assert CONSOLE_MISSING_RULE in rules  # everything besides running/completed


# --- The CLI entry point --------------------------------------------------------


def test_main_exits_zero_on_a_clean_tree(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    _write(fixtures_root / "populated" / "runs.json", _runs_document("running"))
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*domain_values()), encoding="utf-8")

    assert (
        main(["--fixtures-root", str(fixtures_root), "--console-status-path", str(status_path)])
        == 0
    )


def test_main_exits_one_and_prints_the_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_root = tmp_path / "fixtures"
    _write(fixtures_root / "populated" / "runs.json", _runs_document("succeeded"))
    status_path = tmp_path / "status.ts"
    status_path.write_text(_status_module(*domain_values()), encoding="utf-8")

    exit_code = main(
        ["--fixtures-root", str(fixtures_root), "--console-status-path", str(status_path)]
    )

    assert exit_code == 1
    assert "succeeded" in capsys.readouterr().err


# --- The repository itself: red until the migration lands, green after ---------


@pytest.mark.sweep
def test_the_repository_serves_a_run_status_vocabulary_the_console_fully_knows() -> None:
    """The check exercised against the real tree: fixtures and the console vocabulary."""
    from tools.check_run_status_vocabulary import DEFAULT_CONSOLE_STATUS_PATH, DEFAULT_FIXTURES_ROOT

    violations = find_violations(DEFAULT_FIXTURES_ROOT, DEFAULT_CONSOLE_STATUS_PATH)

    assert violations == [], "\n".join(str(violation) for violation in violations)
