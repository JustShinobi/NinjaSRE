"""The closed set of commands an executor may run on a node, and nothing else.

Some Proxmox operations exist only at the CLI, and reaching them means something
holds an SSH identity. Article IV forbids that something being the agent, so the
identity lives in a separate executor and the agent asks it by name — never by
command.

What protects the cluster is not the executor's care. It is this module:

**A command nobody declared cannot run.** There is no entry, so there is nothing
to build an argument vector from. Adding one is an edit somebody reviews, and
each entry carries the sentence saying why the authority was granted.

**An argument cannot become a command.** Every value is checked against its own
pattern before it is placed, and what comes back is a list rather than a string.
There is no shell to interpret a semicolon even if one survived the check, and
no element of the vector is an interpreter that would read the rest as script.

**A write says it is a write.** The autonomy layer decides whether an unattended
agent may run one; it can only decide that if the declaration distinguishes them.
A read mislabelled as a write is an inconvenience. A write mislabelled as a read
runs unattended, which is why the labels are asserted rather than trusted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

#: What a node may be called. Proxmox node names are hostnames, and a hostname
#: is the whole of what this accepts — no spaces, no separators, nothing a
#: transport or a filesystem would read as structure.
NODE_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$", re.IGNORECASE)

#: What each argument kind accepts. Deliberately narrow: an argument is a value
#: this system already holds about the estate, not free text somebody typed.
ARGUMENT_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    "vmid": re.compile(r"^[1-9][0-9]{2,8}$"),
    "unit": re.compile(r"^[a-z0-9@._-]{1,128}\.(service|timer|mount|socket)$", re.IGNORECASE),
    "pool": re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$", re.IGNORECASE),
}


class CommandRefused(ValueError):
    """A command, or one of its arguments, that this module will not build.

    Raised rather than returned, and never with the offending value folded into
    a message that might be echoed somewhere: the refusal names what was asked
    for, not what was smuggled in.
    """


@dataclass(frozen=True, slots=True)
class CommandDeclaration:
    """One command the executor may run, and everything that bounds it."""

    command_id: str
    #: The vector, with ``{node}`` and each argument named in braces. Braces are
    #: substituted per element, never across them, so a value can never add an
    #: element and an element can never be split by one.
    argv: tuple[str, ...]
    #: Which arguments this takes, by name. A name not here is refused rather
    #: than ignored: an argument nobody reads is a caller believing something
    #: about this call that is not true.
    arguments: tuple[str, ...] = ()
    #: Whether running it changes the cluster. Read by the autonomy layer.
    writes: bool = False
    #: Why this authority was granted. An entry nobody can justify in a sentence
    #: is one that should not have been added.
    reason: str = ""
    #: What a caller learns from it, for the catalogue.
    summary: str = ""


#: Everything the executor may be asked for. Reads first, and there are
#: deliberately few writes: each one is an authority that did not exist before.
COMMANDS: Final[tuple[CommandDeclaration, ...]] = (
    CommandDeclaration(
        command_id="failed-units",
        argv=("systemctl", "list-units", "--state=failed", "--no-legend", "--no-pager"),
        reason=(
            "One of the three readings that decided this cluster's only total outage, and "
            "absent from every level of the Proxmox API."
        ),
        summary="The systemd units on a node that are in a failed state.",
    ),
    CommandDeclaration(
        command_id="bridge-state",
        argv=("ip", "-o", "link", "show", "type", "bridge"),
        reason=(
            "A configured bridge that does not exist takes every guest behind it off the "
            "network, and no REST endpoint reports it."
        ),
        summary="Which bridges exist on a node and whether they are up.",
    ),
    CommandDeclaration(
        command_id="thin-pool-metadata",
        argv=("lvs", "--noheadings", "--options", "lv_name,data_percent,metadata_percent"),
        reason=(
            "Thin-pool metadata exhaustion stops writes while the data percentage still "
            "reads comfortable, which is the failure the datastore-level number cannot see."
        ),
        summary="Each thin pool's data and metadata fill.",
    ),
    CommandDeclaration(
        command_id="guest-status",
        argv=("pvesh", "get", "/nodes/{node}/lxc/{vmid}/status/current"),
        arguments=("vmid",),
        reason="The guest's own view of itself, read the same way the API would read it.",
        summary="One container's current status, as its host reports it.",
    ),
    CommandDeclaration(
        command_id="quorum-status",
        argv=("pvecm", "status"),
        reason=(
            "Quorum margin is the difference between a cluster that survives losing a node "
            "and one that goes read-only, and the API reports votes rather than margin."
        ),
        summary="The cluster's membership and how many votes it has spare.",
    ),
    CommandDeclaration(
        command_id="restart-unit",
        argv=("systemctl", "restart", "{unit}"),
        arguments=("unit",),
        writes=True,
        reason=(
            "The narrowest repair there is for a failed unit, and the one a runbook names "
            "most often. A write, so an unattended agent proposes it rather than doing it."
        ),
        summary="Restart one systemd unit on a node.",
    ),
)

_BY_ID: Final[Mapping[str, CommandDeclaration]] = {entry.command_id: entry for entry in COMMANDS}

#: What a brace-delimited placeholder looks like inside one argv element.
_PLACEHOLDER: Final = re.compile(r"\{([a-z_]+)\}")


def declaration_for(command_id: str) -> CommandDeclaration:
    """Return the declaration ``command_id`` names.

    Raises:
        CommandRefused: nothing declares it, which is the same outcome as it
            being forbidden — there is no list this could be missing from.
    """
    found = _BY_ID.get(command_id)
    if found is None:
        raise CommandRefused(f"no command called {command_id!r} is declared")
    return found


def _checked(name: str, value: str) -> str:
    """Return ``value`` if it is what ``name`` accepts, or refuse it."""
    pattern = ARGUMENT_PATTERNS.get(name)
    if pattern is None:
        raise CommandRefused(f"{name!r} is not an argument this executor knows how to check")
    if not pattern.fullmatch(value):
        # The value is not repeated back. A refusal that echoes what it refused
        # is a way for something to reach a log it was never allowed to reach.
        raise CommandRefused(f"the value given for {name!r} is not a valid {name}")
    return value


def argv_for(
    command_id: str,
    *,
    node: str,
    arguments: Mapping[str, str] | None = None,
) -> list[str]:
    """Return the vector to run for ``command_id`` on ``node``.

    Raises:
        CommandRefused: the command is not declared, the node is not a node
            name, an argument is missing, unexpected, or not what it claims.
    """
    declared = declaration_for(command_id)
    given = dict(arguments or {})

    if not NODE_PATTERN.fullmatch(node):
        raise CommandRefused("the node given is not a valid node name")

    unexpected = sorted(set(given) - set(declared.arguments))
    if unexpected:
        raise CommandRefused(f"{command_id!r} takes no argument called {unexpected[0]!r}")
    missing = sorted(set(declared.arguments) - set(given))
    if missing:
        raise CommandRefused(f"{command_id!r} needs {missing[0]!r} and none was given")

    values = {"node": node, **{name: _checked(name, given[name]) for name in declared.arguments}}

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise CommandRefused(f"{command_id!r} names {name!r}, which it does not take")
        return values[name]

    # Element by element, so a value can never add an element and an element can
    # never be split by one.
    return [_PLACEHOLDER.sub(substitute, part) for part in declared.argv]


def catalogue() -> Sequence[Mapping[str, object]]:
    """Return what this executor can be asked for, as an operator reads it."""
    return [
        {
            "command_id": entry.command_id,
            "summary": entry.summary,
            "writes": entry.writes,
            "arguments": list(entry.arguments),
            "reason": entry.reason,
        }
        for entry in COMMANDS
    ]


__all__ = [
    "ARGUMENT_PATTERNS",
    "COMMANDS",
    "NODE_PATTERN",
    "CommandDeclaration",
    "CommandRefused",
    "argv_for",
    "catalogue",
    "declaration_for",
]
