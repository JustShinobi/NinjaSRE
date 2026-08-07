"""The reference implementation of the benchmark port, over a JSONL case file.

Cloud-OpsBench is the benchmark this port was shaped around, so it is the one
that proves the shape is right. The adapter is deliberately thin — read rows,
turn each into a ``BenchmarkCase``, refuse the ones that cannot be scored — and
that thinness is the claim being made: adapting a second benchmark should be this
file with different field names, not a second harness.

The dataset itself is not vendored. A benchmark's cases are its authors' work and
belong wherever the operator downloaded them to; the adapter takes a path. That
also keeps the repository's test suite from depending on a file it cannot
distribute, which is why the tests write their own dataset and read it back.

A malformed row names the file and the line. Somebody seeing this failure is
editing a dataset, and "row 41 has no identifier" is the difference between a
minute and an afternoon.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.evaluation import (
    CLOUD_OPS_BENCH,
    SCENARIO_DIFFICULTY_MAX,
    SCENARIO_DIFFICULTY_MIN,
)
from tests.benchmarks.adapter import BenchmarkCase, UnusableBenchmarkCase

#: The dataset field names this adapter reads, and the aliases it accepts. Two
#: spellings for most, because a benchmark that has been through three papers has
#: been through three schemas and refusing the older one buys nothing.
IDENTIFIER_FIELDS: tuple[str, ...] = ("id", "case_id", "task_id")
OBJECTIVE_FIELDS: tuple[str, ...] = ("prompt", "objective", "question")
CATEGORY_FIELDS: tuple[str, ...] = ("root_cause_category", "category", "label")
KEYWORD_FIELDS: tuple[str, ...] = ("keywords", "required_keywords")
DIFFICULTY_FIELDS: tuple[str, ...] = ("level", "difficulty")


def _first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    """Return the first of ``names`` present in ``row``, or ``None``."""
    for name in names:
        if name in row:
            return row[name]
    return None


def case_of_row(row: Any, *, source: str, line: int) -> BenchmarkCase:
    """Return the case one dataset row describes.

    Raises:
        UnusableBenchmarkCase: naming the file and the row.
    """
    where = f"{source}: row {line}"
    if not isinstance(row, Mapping):
        raise UnusableBenchmarkCase(f"{where}: a benchmark case is a mapping of fields")

    identifier = _first(row, IDENTIFIER_FIELDS)
    objective = _first(row, OBJECTIVE_FIELDS)
    category = _first(row, CATEGORY_FIELDS)

    if not isinstance(identifier, str) or not identifier.strip():
        raise UnusableBenchmarkCase(
            f"{where}: no identifier in any of {list(IDENTIFIER_FIELDS)}, so a failure on "
            f"this case could not be named"
        )
    if not isinstance(objective, str) or not objective.strip():
        raise UnusableBenchmarkCase(f"{where}: no objective in any of {list(OBJECTIVE_FIELDS)}")
    if not isinstance(category, str) or not category.strip():
        raise UnusableBenchmarkCase(
            f"{where}: no expected category in any of {list(CATEGORY_FIELDS)}; a case nobody "
            f"can score moves the published number without measuring anything"
        )

    raw_keywords = _first(row, KEYWORD_FIELDS) or ()
    if isinstance(raw_keywords, str) or not isinstance(raw_keywords, Sequence):
        raise UnusableBenchmarkCase(f"{where}: keywords must be a list of strings")

    raw_level = _first(row, DIFFICULTY_FIELDS)
    level = int(raw_level) if isinstance(raw_level, int) else SCENARIO_DIFFICULTY_MIN
    level = max(SCENARIO_DIFFICULTY_MIN, min(SCENARIO_DIFFICULTY_MAX, level))

    return BenchmarkCase(
        case_id=identifier.strip(),
        objective=objective.strip(),
        expected_category=category.strip(),
        required_keywords=tuple(str(word).strip() for word in raw_keywords if str(word).strip()),
        difficulty=level,
        metadata=dict(row),
    )


def load_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    """Return every case in the JSONL dataset at ``path``.

    Raises:
        UnusableBenchmarkCase: the file is missing, or a row cannot be scored.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise UnusableBenchmarkCase(f"{path}: could not be read: {error}") from error

    cases: list[BenchmarkCase] = []
    for line, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as error:
            raise UnusableBenchmarkCase(
                f"{path}: row {line}: is not valid JSON: {error}"
            ) from error
        cases.append(case_of_row(document, source=str(path), line=line))
    return tuple(cases)


def write_dataset(rows: Iterable[Mapping[str, Any]], path: Path) -> Path:
    """Write ``rows`` as a JSONL dataset and return the path.

    Present so a test can build the dataset it reads. The benchmark's own cases
    are its authors' work and are not vendored here.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    return path


@dataclass(frozen=True, slots=True)
class CloudOpsBenchAdapter:
    """The reference adapter: a JSONL dataset, read once, named for its benchmark."""

    dataset: Path

    @property
    def name(self) -> str:
        """Return which benchmark this is, so a published number carries its label."""
        return CLOUD_OPS_BENCH

    def cases(self) -> tuple[BenchmarkCase, ...]:
        """Return every case in the configured dataset."""
        return load_cases(self.dataset)


__all__ = [
    "CATEGORY_FIELDS",
    "DIFFICULTY_FIELDS",
    "IDENTIFIER_FIELDS",
    "KEYWORD_FIELDS",
    "OBJECTIVE_FIELDS",
    "CloudOpsBenchAdapter",
    "case_of_row",
    "load_cases",
    "write_dataset",
]
