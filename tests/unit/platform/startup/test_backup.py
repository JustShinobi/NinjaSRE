"""SC-004 and FR-017: what a backup says about itself, and what that decides.

Every case here is one an operator hits during an outage, which is the wrong
moment to discover that "incompatible backup" was the whole message. Each
refusal is asserted to name its reason.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from platform.startup.backup import (
    BackupManifest,
    RestoreAction,
    decide_restore,
    row_counts_in,
    verify_row_counts,
)
from platform.startup.errors import BackupIncompatible
from tests.unit.platform.startup.conftest import REVISIONS

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)


def manifest(**overrides: object) -> BackupManifest:
    """Return a manifest for a backup taken at head, with ``overrides`` applied."""
    fields: dict[str, object] = {
        "schema_revision": REVISIONS[-1],
        "taken_at": AT,
        "app_version": "0.1.0",
        "postgres_version": 16,
        "extensions": {"vector": "0.8.6", "age": "1.6.0"},
        "row_counts": {"agent_runs": 12, "episodes": 40},
        "encryption_key_fingerprint": "abc123def456",
    }
    fields.update(overrides)
    return BackupManifest(**fields)  # type: ignore[arg-type]


# -- the decision -------------------------------------------------------------


def test_a_backup_at_the_expected_revision_is_restored() -> None:
    decision = decide_restore(
        manifest(), expected_revision=REVISIONS[-1], ordered_revisions=REVISIONS
    )

    assert decision.action is RestoreAction.RESTORE
    assert decision.permitted
    assert REVISIONS[-1] in decision.reason


def test_an_older_backup_is_restored_and_then_migrated_forward() -> None:
    """FR-017's first branch, which is the ordinary upgrade-across-a-restore."""
    decision = decide_restore(
        manifest(schema_revision=REVISIONS[0]),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
    )

    assert decision.action is RestoreAction.MIGRATE_FORWARD
    assert decision.revisions_to_apply == REVISIONS[1:]
    assert REVISIONS[0] in decision.reason


def test_a_backup_from_a_newer_release_is_refused_with_the_reason() -> None:
    decision = decide_restore(
        manifest(schema_revision="9999_from_the_future"),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
    )

    assert decision.action is RestoreAction.REFUSE
    assert "newer release" in decision.reason
    assert "unknown revision" in decision.reason


def test_a_backup_needing_an_extension_this_server_lacks_is_refused() -> None:
    """A dump that restores without pgvector loses the data that needed it."""
    decision = decide_restore(
        manifest(),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
        available_extensions=("vector",),
    )

    assert decision.action is RestoreAction.REFUSE
    assert "age" in decision.reason
    assert "Install them" in decision.reason


def test_a_backup_encrypted_under_a_different_key_is_refused_before_the_restore() -> None:
    """It would restore perfectly and leave every credential unreadable."""
    decision = decide_restore(
        manifest(),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
        encryption_key_fingerprint="a-different-key",
    )

    assert decision.action is RestoreAction.REFUSE
    assert "different key" in decision.reason
    assert "unreadable" in decision.reason


def test_a_matching_key_fingerprint_permits_the_restore() -> None:
    decision = decide_restore(
        manifest(),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
        encryption_key_fingerprint="abc123def456",
    )

    assert decision.permitted


def test_a_deployment_that_holds_no_key_does_not_block_a_restore() -> None:
    """A fresh host restoring before its key is configured is a legitimate order."""
    decision = decide_restore(
        manifest(),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
        encryption_key_fingerprint="",
    )

    assert decision.permitted


def test_a_refusal_raises_with_its_reason_when_asked_to() -> None:
    decision = decide_restore(
        manifest(schema_revision="9999"),
        expected_revision=REVISIONS[-1],
        ordered_revisions=REVISIONS,
    )

    with pytest.raises(BackupIncompatible) as caught:
        decision.raise_if_refused()

    assert "newer release" in str(caught.value)


# -- the manifest as a file ---------------------------------------------------


def test_a_manifest_round_trips_through_its_file(tmp_path: Path) -> None:
    path = manifest().write(tmp_path / "manifest.json")

    read = BackupManifest.read(path)

    assert read.schema_revision == REVISIONS[-1]
    assert read.row_counts == {"agent_runs": 12, "episodes": 40}
    assert read.encryption_key_fingerprint == "abc123def456"


def test_a_manifest_from_a_future_release_is_refused_rather_than_half_understood(
    tmp_path: Path,
) -> None:
    record = manifest().to_record()
    record["manifest_version"] = 99
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(BackupIncompatible) as caught:
        BackupManifest.read(path)

    assert "version 99" in str(caught.value)


def test_a_missing_manifest_says_why_that_matters(tmp_path: Path) -> None:
    with pytest.raises(BackupIncompatible) as caught:
        BackupManifest.read(tmp_path / "nothing.json")

    assert "cannot be version-checked" in str(caught.value)


def test_a_manifest_with_no_revision_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"manifest_version": 1, "schema_revision": ""}), encoding="utf-8")

    with pytest.raises(BackupIncompatible) as caught:
        BackupManifest.read(path)

    assert "names no schema revision" in str(caught.value)


def test_a_manifest_never_carries_the_key_itself() -> None:
    record = manifest().to_record()

    assert "encryption_key" not in record
    assert len(str(record["encryption_key_fingerprint"])) <= 16


# -- integrity (SC-004) --------------------------------------------------------


def _dump(rows: dict[str, int]) -> str:
    """Return a plain-format dump holding ``rows`` rows per table."""
    blocks = ["-- NinjaSRE test dump", "SET statement_timeout = 0;"]
    for table, count in rows.items():
        blocks.append(f"COPY {table} (id) FROM stdin;")
        blocks.extend(str(index) for index in range(count))
        blocks.append("\\.")
    return "\n".join(blocks) + "\n"


def test_the_row_count_is_read_out_of_the_artefact(tmp_path: Path) -> None:
    dump = tmp_path / "database.sql"
    dump.write_text(_dump({"public.agent_runs": 3, "public.episodes": 5}), encoding="utf-8")

    assert row_counts_in(dump) == {"public.agent_runs": 3, "public.episodes": 5}


def test_an_intact_artefact_reports_no_problems(tmp_path: Path) -> None:
    """SC-004: relational, vector, and graph rows all survive, counted per shape."""
    counts = {"public.agent_runs": 12, "public.episodes": 40, "public.knowledge_chunks": 7}
    dump = tmp_path / "database.sql"
    dump.write_text(_dump(counts), encoding="utf-8")

    assert verify_row_counts(manifest(row_counts=counts), row_counts_in(dump)) == ()


def test_a_truncated_artefact_is_caught_before_it_restores_quietly(tmp_path: Path) -> None:
    recorded = {"public.agent_runs": 12, "public.episodes": 40}
    dump = tmp_path / "database.sql"
    dump.write_text(_dump({"public.agent_runs": 12, "public.episodes": 9}), encoding="utf-8")

    problems = verify_row_counts(manifest(row_counts=recorded), row_counts_in(dump))

    assert len(problems) == 1
    assert "episodes" in problems[0]
    assert "40" in problems[0] and "9" in problems[0]


def test_a_table_missing_from_the_restore_entirely_is_reported_as_zero() -> None:
    problems = verify_row_counts(manifest(row_counts={"public.episodes": 40}), {})

    assert problems and "0" in problems[0]


def test_an_empty_table_is_not_mistaken_for_a_missing_one(tmp_path: Path) -> None:
    dump = tmp_path / "database.sql"
    dump.write_text(_dump({"public.agent_runs": 0}), encoding="utf-8")

    assert row_counts_in(dump) == {"public.agent_runs": 0}
