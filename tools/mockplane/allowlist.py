"""The read-only commands the infrastructure capture may run, and nothing else.

SSH to a cluster node is a far larger authority than a scoped read-only token,
and it is taken deliberately: the layer the reference environment's only total
outage lived in — failed units, thin-pool metadata, the corosync configuration
as written, mount state — is invisible at every API level and obvious at the
shell. The cost is bounded here, by making read-only a property of the tool
rather than of the operator's care.

Two rules and one file.

**A command that is not in the file does not run.** Not "is warned about" — the
capture fails, naming the command, before anything is sent. An ad-hoc query is
held to the same rule, without exception: a convenience escape hatch would make
every other guarantee in this module advisory.

**Extending the list is a change to the file.** Not a flag, not an environment
variable. The point of SSH is that a question nobody anticipated can still be
asked; the point of the allowlist is that answering it stays a decision somebody
made, in a diff somebody read.

Placeholders exist because a node name is a parameter, not a new question.
``{node}`` binds one path segment from a deliberately narrow alphabet, so a
parameter cannot smuggle in a second command.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The declared file. Beside the code that reads it, because a policy file two
#: directories away from its enforcement is a policy file that drifts.
ALLOWLIST_FILENAME: Final = "read_only_commands.json"

#: What a placeholder may bind. Node names, guest ids, storage names and
#: nothing that could end one command and begin another.
PLACEHOLDER_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")

#: Characters that let one command become two. Rejected before matching, so a
#: template can never be tricked into accepting them through a placeholder.
SHELL_METACHARACTERS: Final = frozenset(";&|<>`$\n\r\\\"'()*?[]{}~!#")

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


class CommandRefused(RuntimeError):
    """A command outside the allowlist. Raised instead of running it."""

    def __init__(self, command: str, reason: str) -> None:
        super().__init__(
            f"refusing to run {command!r}: {reason}. "
            f"If this read is one the capture should be able to make, add it to "
            f"{ALLOWLIST_FILENAME} — that is a change a reviewer sees, which is the point."
        )
        self.command = command
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ReadOnlyCommand:
    """One declared read, and what it is for."""

    #: The command, with ``{name}`` where a parameter goes.
    template: str
    #: What this read answers, in one phrase. Written for the reviewer deciding
    #: whether the list should grow, not for the machine.
    reads: str
    #: ``pvesh`` when the cluster's own API could have answered it, ``shell``
    #: when nothing but a shell can. The split is what makes the handover to a
    #: real integration a deletion rather than an archaeology exercise.
    kind: str

    @property
    def placeholders(self) -> tuple[str, ...]:
        """Return the parameter names this command takes, in order."""
        return tuple(_PLACEHOLDER.findall(self.template))

    def bind(self, **arguments: str) -> str:
        """Return the command with its placeholders bound.

        Raises:
            CommandRefused: an argument is missing, or holds something outside
                the narrow alphabet a parameter may use.
        """
        rendered = self.template
        for name in self.placeholders:
            value = arguments.get(name, "")
            if not PLACEHOLDER_PATTERN.fullmatch(value):
                raise CommandRefused(
                    self.template,
                    f"{name}={value!r} is not a value a parameter may take",
                )
            rendered = rendered.replace("{" + name + "}", value)
        return rendered

    def _regex(self) -> re.Pattern[str]:
        parts = _PLACEHOLDER.split(self.template)
        # ``split`` alternates literal, name, literal, name, ...
        pattern = "".join(
            re.escape(part) if index % 2 == 0 else f"(?P<{part}>{PLACEHOLDER_PATTERN.pattern})"
            for index, part in enumerate(parts)
        )
        return re.compile(f"^{pattern}$")

    def match(self, command: str) -> dict[str, str] | None:
        """Return the arguments ``command`` binds in this template, or ``None``."""
        found = self._regex().match(command)
        return dict(found.groupdict()) if found else None


@dataclass(frozen=True, slots=True)
class Allowlist:
    """Every read the capture is permitted to make."""

    commands: tuple[ReadOnlyCommand, ...]
    source: Path | None = None

    def __iter__(self) -> Iterator[ReadOnlyCommand]:
        return iter(self.commands)

    def __len__(self) -> int:
        return len(self.commands)

    @classmethod
    def load(cls, path: Path | None = None) -> Allowlist:
        """Return the declared allowlist.

        Raises:
            CommandRefused: the file is missing or malformed. An unreadable
                allowlist permits nothing, rather than permitting everything.
        """
        source = path if path is not None else Path(__file__).with_name(ALLOWLIST_FILENAME)
        if not source.exists():
            raise CommandRefused("", f"the allowlist {source} does not exist")
        try:
            document: Any = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CommandRefused("", f"the allowlist {source} is not readable: {error}") from error
        entries = document.get("commands") if isinstance(document, dict) else None
        if not isinstance(entries, Sequence) or isinstance(entries, str):
            raise CommandRefused("", f"the allowlist {source} declares no 'commands' list")
        return cls(commands=tuple(_entry(item) for item in entries), source=source)

    def entry_for(self, command: str) -> tuple[ReadOnlyCommand, dict[str, str]] | None:
        """Return the declared command ``command`` is an instance of, and its arguments."""
        for declared in self.commands:
            bound = declared.match(command)
            if bound is not None:
                return declared, bound
        return None

    def check(self, command: str) -> ReadOnlyCommand:
        """Return the declaration permitting ``command``.

        Raises:
            CommandRefused: nothing declares it, or it carries a character that
                could turn one command into two.
        """
        trimmed = command.strip()
        if not trimmed:
            raise CommandRefused(command, "it is empty")
        offending = sorted(SHELL_METACHARACTERS.intersection(trimmed))
        if offending:
            raise CommandRefused(
                command,
                "it carries " + ", ".join(repr(character) for character in offending),
            )
        found = self.entry_for(trimmed)
        if found is None:
            raise CommandRefused(command, "no declared read matches it")
        return found[0]

    def of_kind(self, kind: str) -> tuple[ReadOnlyCommand, ...]:
        """Return the declared commands of one kind."""
        return tuple(declared for declared in self.commands if declared.kind == kind)


def _entry(item: Mapping[str, Any] | Any) -> ReadOnlyCommand:
    if not isinstance(item, Mapping):
        raise CommandRefused("", "an allowlist entry is not an object")
    template = str(item.get("command", ""))
    reads = str(item.get("reads", ""))
    kind = str(item.get("kind", ""))
    if not template:
        raise CommandRefused("", "an allowlist entry declares no command")
    if not reads:
        raise CommandRefused(
            template, "it declares no reason, and an unexplained read is one nobody can review"
        )
    if kind not in {"pvesh", "shell"}:
        raise CommandRefused(template, f"{kind!r} is not a kind of read")
    return ReadOnlyCommand(template=template, reads=reads, kind=kind)


__all__ = [
    "ALLOWLIST_FILENAME",
    "PLACEHOLDER_PATTERN",
    "SHELL_METACHARACTERS",
    "Allowlist",
    "CommandRefused",
    "ReadOnlyCommand",
]
