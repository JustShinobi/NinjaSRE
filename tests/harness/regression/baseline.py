"""A known point, stored under a name, so a comparison has something to be against.

FR-021 is one sentence and it removes a whole class of argument: without a stored
baseline, "the suite got worse" is a claim about somebody's memory of last week's
terminal output. With one, it is a subtraction, and the thing being subtracted
from is a file anybody can read.

Files rather than a database, per Article XI. A baseline is a small JSON document
in a directory; the directory is the store; the identifier is the filename. That
makes a baseline something a release can commit, a bisect can check out, and a
maintainer can delete without a migration.

Every baseline carries the corpus version it was measured over. That is the plan's
own risk mitigation, made mechanical: a scenario added, retired, or re-keyed moves
the version, and the comparison refuses rather than reporting a fixture change as
an agent regression.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.constants.evaluation import (
    BASELINE_FILE_SUFFIX,
    NINJASRE_EVALUATION_BASELINES_ENV,
)
from tests.harness.scoring.report import SuiteScore


class UnknownBaseline(LookupError):
    """A baseline was asked for by a name nothing is stored under.

    Lists what *is* stored, because the person seeing this is choosing an
    identifier and the useful half of the message is the set to choose from.
    """

    def __init__(self, identifier: str, available: tuple[str, ...]) -> None:
        self.identifier = identifier
        self.available = available
        known = ", ".join(available) if available else "nothing is stored yet"
        super().__init__(f"no baseline called {identifier!r}; stored baselines: {known}")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Baseline:
    """One stored suite run, and everything needed to know what it measured."""

    identifier: str
    suite: SuiteScore = field(default_factory=SuiteScore)
    recorded_at: str = ""
    note: str = ""
    provider_id: str = ""
    model_id: str = ""

    def __post_init__(self) -> None:
        # Stamped here rather than when it is written, so a baseline held in
        # memory and the file it becomes carry the same instant. Stamping at
        # write time makes ``from_record(to_record(x)) == x`` false, which is the
        # one property a stored comparison point has to have.
        if not self.recorded_at:
            object.__setattr__(self, "recorded_at", _now())

    @property
    def corpus_version(self) -> str:
        """Return the corpus this baseline was measured over."""
        return self.suite.corpus_version

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this baseline."""
        return {
            "identifier": self.identifier,
            "recorded_at": self.recorded_at,
            "note": self.note,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "corpus_version": self.corpus_version,
            "suite": self.suite.to_record(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Baseline:
        """Return the baseline a stored record describes."""
        return cls(
            identifier=str(record["identifier"]),
            suite=SuiteScore.from_record(record.get("suite") or {}),
            recorded_at=str(record.get("recorded_at", "")),
            note=str(record.get("note", "")),
            provider_id=str(record.get("provider_id", "")),
            model_id=str(record.get("model_id", "")),
        )


@dataclass(frozen=True, slots=True)
class BaselineStore:
    """A directory of stored baselines, keyed by identifier."""

    root: Path

    def path_for(self, identifier: str) -> Path:
        """Return where the baseline called ``identifier`` is stored."""
        return Path(self.root) / f"{identifier}{BASELINE_FILE_SUFFIX}"

    def save(self, baseline: Baseline) -> Path:
        """Write ``baseline`` and return where it landed.

        Overwrites. Re-recording a baseline under a name that already exists is a
        deliberate act — usually because the corpus changed — and refusing it here
        would only move the decision into a filename with a suffix on it.
        """
        path = self.path_for(baseline.identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = baseline.to_record()
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def load(self, identifier: str) -> Baseline:
        """Return the baseline called ``identifier``.

        Raises:
            UnknownBaseline: nothing is stored under that name.
        """
        path = self.path_for(identifier)
        if not path.exists():
            raise UnknownBaseline(identifier, self.identifiers())
        return Baseline.from_record(json.loads(path.read_text(encoding="utf-8")))

    def identifiers(self) -> tuple[str, ...]:
        """Return every stored baseline's identifier, in name order."""
        root = Path(self.root)
        if not root.exists():
            return ()
        return tuple(
            sorted(
                found.name[: -len(BASELINE_FILE_SUFFIX)]
                for found in root.glob(f"*{BASELINE_FILE_SUFFIX}")
            )
        )

    def latest(self) -> Baseline | None:
        """Return the most recently recorded baseline, or ``None`` for an empty store.

        By recorded timestamp rather than by file modification time: a checkout
        rewrites every mtime in the tree, and a baseline that changed identity
        because somebody cloned the repository would be the worst kind of subtle.
        """
        stored = [self.load(identifier) for identifier in self.identifiers()]
        if not stored:
            return None
        return max(stored, key=lambda found: (found.recorded_at, found.identifier))


def store_from_environment(default: Path | None = None) -> BaselineStore:
    """Return the baseline store the environment names, or one under ``default``."""
    configured = os.environ.get(NINJASRE_EVALUATION_BASELINES_ENV, "").strip()
    if configured:
        return BaselineStore(root=Path(configured))
    return BaselineStore(root=default if default is not None else Path("baselines"))


__all__ = [
    "Baseline",
    "BaselineStore",
    "UnknownBaseline",
    "store_from_environment",
]
