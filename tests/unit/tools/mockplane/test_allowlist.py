"""The read-only allowlist: what runs, what does not, and how it says no.

SSH to a cluster node is a much larger authority than a read-only token. It is
taken deliberately and it is bounded here, so these assertions are the bound
rather than a description of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mockplane.allowlist import (
    ALLOWLIST_FILENAME,
    Allowlist,
    CommandRefused,
    ReadOnlyCommand,
)

pytestmark = pytest.mark.unit


def _file(tmp_path: Path, *entries: dict[str, str]) -> Path:
    path = tmp_path / ALLOWLIST_FILENAME
    path.write_text(json.dumps({"commands": list(entries)}), encoding="utf-8")
    return path


def test_the_shipped_allowlist_loads_and_declares_both_kinds() -> None:
    allowlist = Allowlist.load()
    assert allowlist.of_kind("pvesh"), "nothing is declared as answerable by the cluster API"
    assert allowlist.of_kind("shell"), "nothing is declared as needing a shell"
    assert all(declared.reads for declared in allowlist), "a read with no stated reason"


def test_a_command_outside_the_allowlist_is_refused_by_name() -> None:
    allowlist = Allowlist.load()
    with pytest.raises(CommandRefused) as refusal:
        allowlist.check("rm -rf /var/lib/vz")
    assert "rm -rf /var/lib/vz" in str(refusal.value)
    assert ALLOWLIST_FILENAME in str(refusal.value), "the refusal does not say how to extend it"


def test_a_declared_command_is_permitted() -> None:
    allowlist = Allowlist.load()
    assert allowlist.check("systemctl list-units --failed --no-legend --plain --no-pager")


def test_a_parameter_binds_and_the_bound_command_is_permitted() -> None:
    allowlist = Allowlist.load()
    declared = next(
        entry for entry in allowlist if "{node}" in entry.template and "status" in entry.template
    )
    bound = declared.bind(node="node01")
    assert "{node}" not in bound
    assert allowlist.check(bound) == declared


def test_a_parameter_cannot_carry_a_second_command() -> None:
    allowlist = Allowlist.load()
    declared = next(entry for entry in allowlist if "{node}" in entry.template)
    with pytest.raises(CommandRefused):
        declared.bind(node="node01; rm -rf /")


def test_a_shell_metacharacter_is_refused_before_anything_is_matched(tmp_path: Path) -> None:
    # Declared with the metacharacter in it, so the only thing that can refuse
    # this is the metacharacter rule itself.
    allowlist = Allowlist.load(
        _file(tmp_path, {"command": "uname -r && id", "reads": "two things", "kind": "shell"})
    )
    with pytest.raises(CommandRefused) as refusal:
        allowlist.check("uname -r && id")
    assert "'&'" in str(refusal.value)


def test_an_empty_command_is_refused() -> None:
    with pytest.raises(CommandRefused):
        Allowlist.load().check("   ")


def test_a_missing_allowlist_permits_nothing(tmp_path: Path) -> None:
    with pytest.raises(CommandRefused) as refusal:
        Allowlist.load(tmp_path / "not-here.json")
    assert "does not exist" in str(refusal.value)


def test_an_entry_with_no_stated_reason_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CommandRefused) as refusal:
        Allowlist.load(_file(tmp_path, {"command": "uname -r", "reads": "", "kind": "shell"}))
    assert "reason" in str(refusal.value)


def test_an_entry_of_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CommandRefused):
        Allowlist.load(_file(tmp_path, {"command": "uname -r", "reads": "why", "kind": "magic"}))


def test_a_template_matches_only_a_whole_command() -> None:
    declared = ReadOnlyCommand(template="uname -r", reads="the kernel", kind="shell")
    assert declared.match("uname -r") == {}
    assert declared.match("uname -rv") is None
    assert declared.match("sudo uname -r") is None


def test_nothing_declared_writes_restarts_migrates_or_alters_state() -> None:
    forbidden = (
        "set",
        "create",
        "delete",
        "start",
        "stop",
        "restart",
        "migrate",
        "reboot",
        "shutdown",
        "rm ",
        "mv ",
        "dd ",
        "install",
        "upgrade ",
        "apply",
        "write",
    )
    offending = [
        declared.template
        for declared in Allowlist.load()
        for word in forbidden
        if word in declared.template.lower()
    ]
    assert not offending, f"the allowlist declares something that is not a read: {offending}"
