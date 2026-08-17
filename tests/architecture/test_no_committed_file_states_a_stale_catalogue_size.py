"""A committed file that names a catalogue total names the real one.

The catalogue used to be much larger, and the number was written down — in
prose, in docstrings, in constant comments, in a console component's header.
Every one of those was true when it was written and became a lie the moment
the catalogue changed, silently, in files no test was looking at.

That is the failure this module exists to prevent, and it is worth being
precise about why a sweep by hand does not: the obvious command,
``rg <pattern> $(git ls-files)``, overflows the argument list on a repository
this size and **exits reporting nothing found**. It looks exactly like a clean
result. Two separate manual sweeps of this repository reported "no occurrences"
that way while a dozen were sitting in tracked files, which is the argument for
a gate over a habit.

**Only a stated total is a defect.** A count derived from the catalogue at
runtime is always right and is what the code should do; ``len(catalogue)`` is
not something this sweep can or should see. What it looks for is a literal —
digits or words — sitting next to a catalogue noun, and it compares that
literal against the catalogue as it is right now rather than against a number
frozen in this file.

Three places may still state an old total, for the same reason the vendor sweep
excepts them: a decision record explains what was decided *then* and is
falsified by being edited, and the roadmap carries the record of scope that has
moved. Editing either to match today's tree would destroy the history they
exist to hold.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest
from contract_config import REPO_ROOT

from integrations._catalogue.discovery import vendor_packages

pytestmark = pytest.mark.architecture

#: Where a total that is no longer true is allowed to stay written down.
ALLOWED: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "roadmap.md",
    REPO_ROOT / "docs" / "adr",
    REPO_ROOT / "docs" / "methodology" / "archive",
)

#: Directories that are not this repository's committed source.
EXCLUDED_TOP: frozenset[str] = frozenset(
    {".venv", "node_modules", "_research", ".git", ".codegraph", "__pycache__"}
)

#: Spelled-out numbers a contributor actually writes in prose here. Not a
#: general number parser: the point is to catch a stated catalogue size, and
#: the sizes anybody writes out in words are small multiples of ten plus a
#: unit. A number outside this table is written in digits and caught below.
WORD_NUMBERS: dict[str, int] = {
    "ten": 10,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    **{
        f"{tens}-{unit}": value + digit
        for tens, value in (
            ("twenty", 20),
            ("thirty", 30),
            ("forty", 40),
            ("fifty", 50),
            ("sixty", 60),
            ("seventy", 70),
            ("eighty", 80),
            ("ninety", 90),
        )
        for unit, digit in (
            ("one", 1),
            ("two", 2),
            ("three", 3),
            ("four", 4),
            ("five", 5),
            ("six", 6),
            ("seven", 7),
            ("eight", 8),
            ("nine", 9),
        )
    },
}

#: How a catalogue total is actually written: the number, then at most a couple
#: of adjectives, then the noun. Deliberately narrow.
#:
#: "vendor" and "package" are **not** in the noun position, and that is a
#: decision rather than an oversight. This repository says "401 from vendor",
#: "twenty-four packages pending" about an apt upgrade, and "Alpine 3.23
#: packages Python 3.12" — all numbers beside one of those words, none of them
#: a catalogue size. A gate that flags them is a gate somebody switches off,
#: and a switched-off gate is worth less than the narrow one that stays on.
_COUNTED = r"(?:\s+[a-z-]+){0,2}\s+integrations?\b"

_DIGITS = re.compile(rf"~?\b(\d{{1,4}}){_COUNTED}", re.IGNORECASE)
_WORDS = re.compile(rf"\b([a-z]+(?:-[a-z]+)?){_COUNTED}", re.IGNORECASE)
_DIGITS_OF = re.compile(r"catalogue of ~?\b(\d{1,4})\b", re.IGNORECASE)
_WORDS_OF = re.compile(r"catalogue of \b([a-z]+(?:-[a-z]+)?)\b", re.IGNORECASE)

#: A number this small is a sample, an example or an arity ("three vendors
#: today", "the two that are not", "one package at a time"), never somebody
#: asserting how large the catalogue is.
NOT_A_TOTAL_BELOW = 10

#: A (file, number) pair where "<n> integrations" counts something that is not
#: the catalogue. A pair rather than a whole-file exception, so the file stays
#: swept for every other number.
NOT_THE_CATALOGUE: frozenset[tuple[str, int]] = frozenset(
    {
        # The synthetic configuration a resolution benchmark merges — declared
        # in the same sentence as "more than any real deployment carries".
        # It counts configured integrations in a fixture, not shipped ones.
        ("tests/benchmarks/test_config_resolution.py", 20),
    }
)


@cache
def _catalogue_size() -> int:
    """Return how many vendor packages the tree actually ships."""
    return len(vendor_packages())


@cache
def _tracked_text_files() -> tuple[Path, ...]:
    """Return every tracked file that is worth reading as text."""
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    found: list[Path] = []
    for name in output.split("\0"):
        if not name.strip():
            continue
        path = REPO_ROOT / name
        relative = path.relative_to(REPO_ROOT)
        if set(relative.parts) & EXCLUDED_TOP:
            continue
        if path.suffix in {".png", ".jpg", ".ico", ".woff", ".woff2", ".zip"}:
            continue
        if not path.is_file():
            continue
        found.append(path)
    return tuple(found)


def _is_allowed(path: Path) -> bool:
    return any(path == allowed or allowed in path.parents for allowed in ALLOWED)


def _stated_totals(line: str) -> list[int]:
    """Return every catalogue size this line asserts as a literal."""
    stated: list[int] = []
    for pattern in (_DIGITS, _DIGITS_OF):
        for match in pattern.finditer(line):
            stated.append(int(match.group(1)))
    for pattern in (_WORDS, _WORDS_OF):
        for match in pattern.finditer(line):
            value = WORD_NUMBERS.get(match.group(1).lower())
            if value is not None:
                stated.append(value)
    return [value for value in stated if value >= NOT_A_TOTAL_BELOW]


def test_no_committed_file_states_a_catalogue_size_that_is_not_the_real_one() -> None:
    size = _catalogue_size()
    offenders: dict[str, list[str]] = {}

    for path in _tracked_text_files():
        if _is_allowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            relative = path.relative_to(REPO_ROOT).as_posix()
            wrong = [
                stated
                for stated in _stated_totals(line)
                if stated != size and (relative, stated) not in NOT_THE_CATALOGUE
            ]
            if wrong:
                offenders.setdefault(relative, []).append(f"line {number}: {line.strip()}")

    assert not offenders, (
        f"a committed file states a catalogue size other than the {size} integrations "
        "the tree actually ships. Derive the count from the catalogue, or drop the "
        "number — only the roadmap and the decision records may keep an old one:\n"
        + "\n".join(
            f"  {file}:\n" + "\n".join(f"    {hit}" for hit in hits)
            for file, hits in sorted(offenders.items())
        )
    )
