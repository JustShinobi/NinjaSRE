"""The operator's list of real values — the one thing the scan cannot guess.

Anonymisation logic will have holes. A hostname in an error message, a URL
inside a log line, a guest name that is also the name of a piece of software
everybody runs. The defence is not a more careful pipeline; it is an adversarial
pass over the output that *knows the real values* and fails the build on any of
them.

That list cannot live in the repository, for the obvious reason: a file naming
every hostname, address and domain of somebody's infrastructure is exactly the
disclosure the pipeline exists to prevent. So it lives wherever the operator
keeps it, and this module reads it.

The format is a text file, not JSON, because it is maintained by a person under
time pressure who should not have to think about escaping::

    # anything after a hash is a comment
    node: pve-alpha
    ipv4: 10.0.0.7
    domain: example-estate.lan
    person: A Real Name
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from config.constants.fixtures import NINJASRE_IDENTIFIER_FILE_ENV
from tools.mockplane.anonymise.pseudonyms import Kind


class IdentifierFileError(RuntimeError):
    """The list exists and could not be read, which is not the same as absent."""


@dataclass(frozen=True, slots=True)
class RealIdentifier:
    """One value that must never appear in the committed dataset."""

    kind: Kind
    value: str


@dataclass(frozen=True, slots=True)
class IdentifierList:
    """Every real value the operator has told this tooling about."""

    entries: tuple[RealIdentifier, ...] = field(default_factory=tuple)
    source: Path | None = None

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __iter__(self) -> Iterator[RealIdentifier]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def empty(cls) -> IdentifierList:
        """Return a list naming nothing, for a run with no operator file."""
        return cls()

    @classmethod
    def of(cls, entries: Sequence[RealIdentifier]) -> IdentifierList:
        """Return a list holding ``entries``, for a test that seeds one."""
        return cls(entries=tuple(entries))

    @classmethod
    def load(cls, path: Path | None = None) -> IdentifierList:
        """Return the operator's list, or an empty one when nothing names a file.

        Absent is a legitimate answer — a contributor with no access to the
        source deployment has nothing to scan against, and the pattern net still
        runs. Present-and-unreadable is not, and raises.

        Raises:
            IdentifierFileError: the named file cannot be read or holds a line
                naming a kind that does not exist.
        """
        source = path
        if source is None:
            named = os.environ.get(NINJASRE_IDENTIFIER_FILE_ENV, "").strip()
            if not named:
                return cls.empty()
            source = Path(named).expanduser()
        if not source.exists():
            raise IdentifierFileError(f"{source} does not exist")
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as failure:
            raise IdentifierFileError(f"{source} could not be read: {failure}") from failure

        entries: list[RealIdentifier] = []
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.split("#", 1)[0].strip()
            if not stripped:
                continue
            raw_kind, separator, value = stripped.partition(":")
            if not separator or not value.strip():
                raise IdentifierFileError(f"{source}:{number}: {line!r} is not 'kind: value'")
            try:
                kind = Kind(raw_kind.strip().lower())
            except ValueError as error:
                raise IdentifierFileError(
                    f"{source}:{number}: {raw_kind.strip()!r} is not one of "
                    f"{', '.join(sorted(item.value for item in Kind))}"
                ) from error
            entries.append(RealIdentifier(kind=kind, value=value.strip()))
        return cls(entries=tuple(entries), source=source)

    def longest_first(self) -> tuple[RealIdentifier, ...]:
        """Return the entries longest value first.

        Order matters when one real value contains another: replacing the
        shorter one first leaves a fragment of the longer behind, which is a
        leak that looks like a pseudonym.
        """
        return tuple(sorted(self.entries, key=lambda entry: (-len(entry.value), entry.value)))


__all__ = [
    "IdentifierFileError",
    "IdentifierList",
    "RealIdentifier",
]
