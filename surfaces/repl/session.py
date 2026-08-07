"""The state one interactive session holds, and what survives leaving it.

A session is a transcript, an accounting, and whatever the run is currently
waiting on. A resumed one has to match its pre-suspension state exactly,
which is a property of *what is saved* rather than of the restore code: anything
held only in the loop's local variables is gone when the process is, so
everything that has to come back lives here and travels as one record.

``compact`` is the interesting operation. It shortens the transcript and keeps
every evidence reference, because a compacted session that lost its evidence
identifiers would produce a conclusion the trace cannot support — which is the
one thing a transcript is not allowed to do to make itself smaller.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.constants.surfaces import SURFACE_REPL
from platform.observability.logging import get_logger
from surfaces.cli.models import CostReport, SessionSummary

logger = get_logger(__name__)


def _now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Exchange:
    """One thing said, by the person or by the agent."""

    speaker: str
    text: str
    at: datetime = field(default_factory=_now)
    run_id: str = ""
    #: Evidence this exchange rests on. Kept on the exchange rather than only on
    #: the run, so compaction can drop the words and keep the references.
    evidence_ids: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return this exchange as a JSON-serialisable document."""
        return {
            "speaker": self.speaker,
            "text": self.text,
            "at": self.at.isoformat(),
            "run_id": self.run_id,
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Exchange:
        """Return the exchange a stored record describes."""
        return cls(
            speaker=str(record.get("speaker", "")),
            text=str(record.get("text", "")),
            at=datetime.fromisoformat(str(record["at"])),
            run_id=str(record.get("run_id", "")),
            evidence_ids=tuple(str(found) for found in record.get("evidence_ids") or ()),
        )


@dataclass(slots=True)
class ReplSession:
    """One stateful interactive session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    objective: str = ""
    team_node_id: str = ""
    started_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    transcript: list[Exchange] = field(default_factory=list)
    cost: CostReport = field(default_factory=CostReport)
    active_run_id: str = ""
    model_id: str = ""
    effort: str = ""
    #: Everything the session has ever referenced. Preserved across compaction,
    #: because it is the set a conclusion is allowed to rest on.
    evidence_ids: tuple[str, ...] = ()
    #: What the run is waiting on, by interaction identifier. Restored with the
    #: session so a resumed one still knows which question is open.
    awaiting: tuple[str, ...] = ()

    # -- changing -------------------------------------------------------------

    def record(
        self, speaker: str, text: str, *, run_id: str = "", evidence: Sequence[str] = ()
    ) -> Exchange:
        """Append one exchange and return it."""
        exchange = Exchange(speaker=speaker, text=text, run_id=run_id, evidence_ids=tuple(evidence))
        self.transcript.append(exchange)
        self.evidence_ids = tuple(dict.fromkeys((*self.evidence_ids, *exchange.evidence_ids)))
        self.updated_at = exchange.at
        if not self.objective and speaker == "human":
            # The first thing somebody said is what a listing shows, because
            # "session 4f2a" is not something anybody recognises tomorrow.
            self.objective = text
        return exchange

    def spend(self, cost: CostReport) -> None:
        """Add ``cost`` to this session's running total."""
        self.cost = CostReport(
            runs=self.cost.runs + cost.runs,
            turns=self.cost.turns + cost.turns,
            prompt_tokens=self.cost.prompt_tokens + cost.prompt_tokens,
            completion_tokens=self.cost.completion_tokens + cost.completion_tokens,
            cost=self.cost.cost + cost.cost,
            unpriced_runs=self.cost.unpriced_runs + cost.unpriced_runs,
        )
        self.updated_at = _now()

    def compact(self, *, keep: int = 10) -> int:
        """Shorten the transcript to its last ``keep`` exchanges, and say how many went.

        Evidence references survive whatever is dropped. A compaction that lost
        them would leave the agent able to state a conclusion it can no longer
        show the basis for, which is the one economy a transcript may not make.
        """
        if len(self.transcript) <= keep:
            return 0

        dropped = self.transcript[:-keep]
        carried = tuple(found for exchange in dropped for found in exchange.evidence_ids)
        self.transcript = self.transcript[-keep:]
        self.evidence_ids = tuple(dict.fromkeys((*self.evidence_ids, *carried)))
        self.updated_at = _now()
        logger.info(
            "repl.session_compacted",
            session_id=self.session_id,
            dropped=len(dropped),
            evidence_kept=len(self.evidence_ids),
        )
        return len(dropped)

    # -- reading --------------------------------------------------------------

    def summary(self) -> SessionSummary:
        """Return this session as a listing shows it."""
        return SessionSummary(
            session_id=self.session_id,
            objective=self.objective,
            started_at=self.started_at,
            updated_at=self.updated_at,
            turns=len(self.transcript),
            evidence=len(self.evidence_ids),
            awaiting=", ".join(self.awaiting),
        )

    # -- persistence ----------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Return everything that has to come back after a restart."""
        return {
            "session_id": self.session_id,
            "surface": SURFACE_REPL,
            "objective": self.objective,
            "team_node_id": self.team_node_id,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "transcript": [exchange.to_record() for exchange in self.transcript],
            "cost": self.cost.to_record(),
            "active_run_id": self.active_run_id,
            "model_id": self.model_id,
            "effort": self.effort,
            "evidence_ids": list(self.evidence_ids),
            "awaiting": list(self.awaiting),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ReplSession:
        """Return the session a stored record describes.

        Every field the record carries is restored, including the accounting and
        what the run was waiting on. Fidelity is this method agreeing with
        ``to_record`` about the whole set — a field written and not read is a
        field that silently resets on resume.
        """
        cost = record.get("cost") or {}
        return cls(
            session_id=str(record["session_id"]),
            objective=str(record.get("objective", "")),
            team_node_id=str(record.get("team_node_id", "")),
            started_at=datetime.fromisoformat(str(record["started_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
            transcript=[Exchange.from_record(entry) for entry in record.get("transcript") or ()],
            cost=CostReport(
                runs=int(cost.get("runs", 0)),
                turns=int(cost.get("turns", 0)),
                prompt_tokens=int(cost.get("prompt_tokens", 0)),
                completion_tokens=int(cost.get("completion_tokens", 0)),
                cost=float(cost.get("cost", 0.0)),
                unpriced_runs=int(cost.get("unpriced_runs", 0)),
            ),
            active_run_id=str(record.get("active_run_id", "")),
            model_id=str(record.get("model_id", "")),
            effort=str(record.get("effort", "")),
            evidence_ids=tuple(str(found) for found in record.get("evidence_ids") or ()),
            awaiting=tuple(str(found) for found in record.get("awaiting") or ()),
        )


@dataclass(slots=True)
class SessionStore:
    """Where sessions are kept between one invocation and the next.

    An in-memory implementation plus a file-backed one would be two things to
    keep in step, so this is the file-backed one and a test points it at a
    temporary directory. Sessions are the operator's own data on the operator's
    own host, which is the whole reason they are not somewhere else.
    """

    directory: Path

    def _path(self, session_id: str) -> Path:
        """Return where ``session_id`` is stored."""
        return self.directory / f"{session_id}.json"

    def save(self, session: ReplSession) -> None:
        """Write ``session`` so a later invocation can resume it."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(session.session_id).write_text(
            json.dumps(session.to_record(), indent=2, sort_keys=True), encoding="utf-8"
        )

    def load(self, session_id: str) -> ReplSession | None:
        """Return the stored session, or ``None`` when there is not one."""
        path = self._path(session_id)
        if not path.is_file():
            return None
        return ReplSession.from_record(json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self, *, limit: int = 20) -> tuple[ReplSession, ...]:
        """Return the stored sessions, most recently updated first."""
        if not self.directory.is_dir():
            return ()
        found: list[ReplSession] = []
        for path in self.directory.glob("*.json"):
            try:
                found.append(ReplSession.from_record(json.loads(path.read_text(encoding="utf-8"))))
            except (KeyError, ValueError, OSError) as failure:
                # One unreadable session file does not make the others
                # unlistable. It is reported and skipped, because "no sessions"
                # would be a lie about the eleven that are fine.
                logger.warning("repl.unreadable_session", path=str(path), error=str(failure))
        return tuple(sorted(found, key=lambda held: held.updated_at, reverse=True))[:limit]

    def delete(self, session_id: str) -> bool:
        """Remove one stored session, reporting whether one went."""
        path = self._path(session_id)
        if not path.is_file():
            return False
        path.unlink()
        return True


def resumed(session: ReplSession) -> ReplSession:
    """Return ``session`` marked as picked up again.

    A new object rather than a mutation, so the caller comparing a restored
    session against what was saved — which is what the fidelity test does — is
    comparing against something nothing has touched.
    """
    return replace(session, updated_at=_now())


__all__ = [
    "Exchange",
    "ReplSession",
    "SessionStore",
    "resumed",
]
