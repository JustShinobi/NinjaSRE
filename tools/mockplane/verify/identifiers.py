"""The adversarial scan: does anything real survive in what is about to be committed?

Two nets, and the second one is why this runs in the gate rather than on the
operator's machine only.

**The operator's list.** Every real hostname, address, domain, guest name,
storage name, person and team, held in a file outside this repository, hunted
for literally. This is the strong net and it is the one a contributor cloning
the repository does not have.

**The pattern net.** Private address ranges, private domain suffixes, and
anything shaped like a credential. Weaker, because it cannot know what a real
guest is called — and it runs everywhere, on every clone, on every commit, with
no configuration at all. A dataset that passes only the strong net is a dataset
whose safety depends on one person having a file.

A leak names the file, the line and what matched. "Something leaked" is not a
finding anybody can act on.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tools.mockplane.anonymise.pseudonyms import PSEUDONYM_DOMAIN
from tools.mockplane.anonymise.redaction import CREDENTIAL_VALUE_PATTERNS
from tools.mockplane.identifiers import IdentifierList

#: Address ranges that belong to somebody's estate. The documentation ranges the
#: pseudonyms are drawn from are deliberately absent.
PRIVATE_ADDRESS_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b10\.(?:\d{1,3}\.){2}\d{1,3}\b"),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\bfd[0-9a-f]{2}:(?:[0-9a-f]{0,4}:){1,6}[0-9a-f]{0,4}\b", re.IGNORECASE),
)

#: Suffixes nobody registers, which means a name under one is a private naming
#: scheme and therefore somebody's.
PRIVATE_DOMAIN_PATTERN: Final = re.compile(
    r"\b[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)*"
    r"\.(?:lan|local|internal|home|corp|intranet)\b",
    re.IGNORECASE,
)

#: A MAC address that is not locally administered belongs to a manufacturer, and
#: a manufacturer's address in a fixture came off real hardware.
REAL_MAC_PATTERN: Final = re.compile(
    r"\b(?!02:)[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b",
)

#: An e-mail address outside the fictional deployment's own domain.
FOREIGN_EMAIL_PATTERN: Final = re.compile(
    r"\b[A-Za-z0-9._%+-]+@(?!" + re.escape(PSEUDONYM_DOMAIN) + r"\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


@dataclass(frozen=True, slots=True)
class Leak:
    """One real value found in something about to be committed."""

    path: Path
    line: int
    rule: str
    matched: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.matched!r}"


def scan_text(
    text: str,
    identifiers: IdentifierList,
    *,
    path: Path,
) -> tuple[Leak, ...]:
    """Return every leak in ``text``, with the line each was found on."""
    return tuple(_leaks(text, identifiers, path))


def scan_tree(
    root: Path,
    identifiers: IdentifierList,
    *,
    suffixes: Sequence[str] = (".json", ".md", ".txt"),
) -> tuple[Leak, ...]:
    """Return every leak anywhere under ``root``.

    Reads the files rather than the parsed documents on purpose: a leak in a key
    name, in a comment, or in a field the loader would have dropped is still a
    leak, and a scan over the parsed form would not see it.
    """
    found: list[Leak] = []
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file() or candidate.suffix not in suffixes:
            continue
        found.extend(scan_text(candidate.read_text(encoding="utf-8"), identifiers, path=candidate))
    return tuple(found)


def _leaks(text: str, identifiers: IdentifierList, path: Path) -> Iterator[Leak]:
    known = identifiers.longest_first()
    for number, line in enumerate(text.splitlines(), start=1):
        for entry in known:
            if entry.value and entry.value in line:
                yield Leak(path, number, f"the operator's {entry.kind.value} list", entry.value)
        for pattern in PRIVATE_ADDRESS_PATTERNS:
            for found in pattern.finditer(line):
                yield Leak(path, number, "private address range", found.group(0))
        for found in PRIVATE_DOMAIN_PATTERN.finditer(line):
            yield Leak(path, number, "private domain suffix", found.group(0))
        for found in REAL_MAC_PATTERN.finditer(line):
            yield Leak(path, number, "manufacturer MAC address", found.group(0))
        for found in FOREIGN_EMAIL_PATTERN.finditer(line):
            yield Leak(path, number, "e-mail address outside the fictional domain", found.group(0))
        for pattern in CREDENTIAL_VALUE_PATTERNS:
            for found in pattern.finditer(line):
                yield Leak(path, number, "credential-shaped value", found.group(0)[:24])


__all__ = [
    "FOREIGN_EMAIL_PATTERN",
    "PRIVATE_ADDRESS_PATTERNS",
    "PRIVATE_DOMAIN_PATTERN",
    "REAL_MAC_PATTERN",
    "Leak",
    "scan_text",
    "scan_tree",
]
