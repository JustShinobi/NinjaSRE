"""One suite at a time, per cluster, because two would score each other's damage.

Two runs injecting faults into one cluster produce a scenario with two causes
and two answer keys naming one each. Both score as misses, neither is a
measurement of anything, and the reason is invisible in the results — which is
why this is a lock and not a convention.

A file, created exclusively, holding who took it and when. Files rather than
anything cleverer because the thing being coordinated is a cluster, the parties
are two shell invocations, and a lock service would be infrastructure this suite
would then also need a lock for.

**Staleness is decided by liveness, not by age alone.** A killed runner leaves
its lock behind; a suite that then refuses forever is a suite people delete lock
files for by hand, and a hand-deleted lock is worse than none because the next
person deletes a live one. So a lock whose holder is not running, or which has
gone untouched past its age, is taken over — and the takeover is recorded in the
new lock so a confused operator can see it happened.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from config.constants.chaos import (
    CHAOS_LOCK_FILENAME,
    CHAOS_LOCK_STALE_SECONDS,
)


class ClusterBusy(RuntimeError):
    """Another run holds this cluster.

    Carries who holds it, because the only useful next action is to find out
    whether that run is still going.
    """


@dataclass(frozen=True, slots=True)
class LockRecord:
    """Who holds one cluster, and since when."""

    cluster: str
    run_id: str
    pid: int
    host: str
    acquired_at: str
    took_over_from: str = ""

    def to_record(self) -> dict[str, object]:
        """Return a JSON-serialisable record of this lock."""
        return {
            "cluster": self.cluster,
            "run_id": self.run_id,
            "pid": self.pid,
            "host": self.host,
            "acquired_at": self.acquired_at,
            "took_over_from": self.took_over_from,
        }

    @classmethod
    def from_record(cls, record: dict[str, object]) -> LockRecord:
        """Return the lock a stored record describes."""
        return cls(
            cluster=str(record.get("cluster", "")),
            run_id=str(record.get("run_id", "")),
            pid=int(record.get("pid", 0) or 0),
            host=str(record.get("host", "")),
            acquired_at=str(record.get("acquired_at", "")),
            took_over_from=str(record.get("took_over_from", "")),
        )

    def age_seconds(self, *, now: datetime | None = None) -> float:
        """Return how long ago this lock was taken, or ``inf`` if it does not say."""
        moment = now if now is not None else datetime.now(UTC)
        try:
            taken = datetime.fromisoformat(self.acquired_at)
        except ValueError:
            return float("inf")
        return (moment - taken).total_seconds()


def _process_alive(pid: int) -> bool:
    """Return whether a process with ``pid`` is running on this machine."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Somebody else's process, which is very much alive.
        return True
    except OSError:
        return False
    return True


def _path_for(cluster: str, root: Path) -> Path:
    """Return where ``cluster``'s lock lives under ``root``."""
    safe = "".join(character if character.isalnum() else "-" for character in cluster)
    return Path(root) / safe / CHAOS_LOCK_FILENAME


def held_by(cluster: str, *, root: Path) -> LockRecord | None:
    """Return who holds ``cluster``'s lock, or ``None`` when nobody does."""
    path = _path_for(cluster, root)
    if not path.exists():
        return None
    try:
        return LockRecord.from_record(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def _stale(record: LockRecord, *, alive: Callable[[int], bool], stale_seconds: float) -> bool:
    """Return whether ``record`` is a lock nobody is holding any more."""
    if record.age_seconds() > stale_seconds:
        return True
    if record.host != socket.gethostname():
        # A lock taken on another machine: age is all this process can judge by,
        # and it has already been judged above.
        return False
    return not alive(record.pid)


@contextmanager
def cluster_lock(
    cluster: str,
    *,
    root: Path,
    run_id: str = "",
    alive: Callable[[int], bool] = _process_alive,
    stale_seconds: float = CHAOS_LOCK_STALE_SECONDS,
) -> Iterator[LockRecord]:
    """Hold ``cluster`` for the duration of the block.

    Raises:
        ClusterBusy: a live run already holds this cluster.
    """
    path = _path_for(cluster, root)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = held_by(cluster, root=root)
    took_over = ""
    if existing is not None:
        if not _stale(existing, alive=alive, stale_seconds=stale_seconds):
            raise ClusterBusy(
                f"{cluster} is held by run {existing.run_id!r} (pid {existing.pid} on "
                f"{existing.host}, since {existing.acquired_at}); two suites injecting faults "
                f"into one cluster would score each other's damage"
            )
        took_over = existing.run_id
        path.unlink(missing_ok=True)

    record = LockRecord(
        cluster=cluster,
        run_id=run_id or f"run-{os.getpid()}",
        pid=os.getpid(),
        host=socket.gethostname(),
        acquired_at=datetime.now(UTC).isoformat(timespec="seconds"),
        took_over_from=took_over,
    )

    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as failure:  # pragma: no cover - lost a race we just checked
        raise ClusterBusy(f"{cluster} was taken while this run was acquiring it") from failure

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record.to_record(), handle, indent=2, sort_keys=True)

    try:
        yield record
    finally:
        held = held_by(cluster, root=root)
        if held is not None and held.run_id == record.run_id:
            path.unlink(missing_ok=True)


__all__ = ["ClusterBusy", "LockRecord", "cluster_lock", "held_by"]
