"""What every Proxmox investigation tool owes its reader, written once.

Three obligations run through all of them, and each is the kind that decays into
a comment if it is not a function.

**Say what you could not determine.** A tool that read four endpoints and got
three is not a tool that read three endpoints. The fourth is a hole in the
answer, and a report that omits it invites a conclusion drawn from a reading
that never happened. ``Undetermined`` carries the question, why it went
unanswered, and — where anything would have published it — what. Every result
below carries the list, empty when there is nothing missing, so a reader never
has to know whether a particular tool bothered.

**Stay bounded, by ranking rather than by truncation.** A cluster with a
thousand snapshots must not produce a thousand-entry payload; a small local
model's whole context is smaller than that. Cutting the list at twenty is only
safe if the twenty are the twenty that matter, so ``bounded`` sorts before it
cuts and returns a note saying it was bounded, by how much, and by what — which
is the part a truncating tool never says and the part that tells a reader to ask
a narrower question.

**Answer, do not dump.** The consequence is part of the answer. "Not quorate" is
a fact an operator still has to interpret; "not quorate, so ``/etc/pve`` is
read-only, so nothing can be started or migrated, and running guests are
unaffected" is the same fact with the three inferences that always follow it.
Encoding them here means they are right every time rather than rediscovered by
the model on each run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from core.capability.metadata import EvidenceType
from core.capability.result import CapabilityResult, Evidence
from integrations.proxmox.models import Reading
from integrations.proxmox.schema import INTEGRATION

#: How many entries any one list in a result may carry. Twenty is roughly what
#: an operator reads before scrolling and comfortably inside a small model's
#: context, and the number matters far less than the ranking that precedes it.
MAX_REPORTED_ITEMS: Final = 20

#: Above this proportion of capacity, a ZFS pool's allocator starts working from
#: best-fit rather than first-fit and write latency degrades sharply. The pool is
#: still healthy by every state it reports; this is the number that is not in it.
ZFS_CAPACITY_DEGRADED_PERCENT: Final = 80.0

#: What corosync's token protocol tolerates between members before membership
#: itself becomes unstable. Small, and far smaller than anything an operator
#: would notice by looking at two clocks.
CLOCK_SKEW_TOLERANCE_SECONDS: Final = 1.0

#: How many days a scrub may go unrun before the pool's error detection is
#: stale. A pool that has never scrubbed has never checked its own data.
SCRUB_STALE_DAYS: Final = 35

#: The SMART attributes that predict a failure rather than describe a drive.
#: A disk whose verdict still says ``PASSED`` while these climb is the ordinary
#: way a disk fails, and the verdict is the last thing to change.
PREDICTIVE_SMART_ATTRIBUTES: Final[tuple[str, ...]] = (
    "Reallocated_Sector_Ct",
    "Reported_Uncorrect",
    "Command_Timeout",
    "Current_Pending_Sector",
    "Offline_Uncorrectable",
    "Reallocated_Event_Count",
    "Media_Wearout_Indicator",
    "Percent_Lifetime_Remain",
    "Wear_Leveling_Count",
)

#: How many down-and-up transitions inside the log window make a link *flapping*
#: rather than lost. One is an event; several is a fault that is still happening,
#: and the two have completely different remedies.
LINK_FLAP_TRANSITIONS: Final = 2


#: The instant readings are taken as of, when something has pinned one. ``None``
#: is the live case and is what every deployment runs with.
_OBSERVED_AT: datetime | None = None


def observed_now() -> datetime:
    """Return the instant this reading is taken as of.

    A fourth obligation, and the one that is easiest to lose: every age,
    exposure and staleness figure in this package measures from *here* rather
    than from the clock at the point it is needed. Two tools reading the same
    cluster a second apart would otherwise disagree about how old the same task
    is, and a reading replayed over recorded responses — which carry absolute
    timestamps — would produce a different number every second it was replayed.

    Live, this is the clock. There is no configuration that moves it.
    """
    return _OBSERVED_AT if _OBSERVED_AT is not None else datetime.now(UTC)


@contextmanager
def reading_as_of(moment: datetime) -> Iterator[None]:
    """Read as of ``moment`` for the duration of the block.

    For replaying recorded responses, which is the only case where "now" is a
    fact about the recording rather than about the machine. Restores whatever
    was pinned before, so one replay cannot leak its instant into the next.
    """
    global _OBSERVED_AT  # noqa: PLW0603 - one pinned instant per process, restored on exit
    previous = _OBSERVED_AT
    _OBSERVED_AT = moment
    try:
        yield
    finally:
        _OBSERVED_AT = previous


@dataclass(frozen=True, slots=True)
class Undetermined:
    """One question a tool asked and could not answer, with why.

    Not an omission and not a zero. "Nothing publishes this" and "the value is
    nothing" are different sentences, and an estate that collapses them reports
    a fire as fine.
    """

    question: str
    reason: str
    published_by: str = ""

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a result carries."""
        return {
            "question": self.question,
            "reason": self.reason,
            "published_by": self.published_by,
        }


def gap(reading: Reading[Any], question: str) -> Undetermined | None:
    """Return what ``reading`` failed to answer, or ``None`` when it answered.

    The bridge between the client's absent readings and a tool's own account of
    its holes, so a tool never has to decide how to phrase one.
    """
    if reading.available:
        return None
    return Undetermined(
        question=question,
        reason=reading.unavailable_reason or "the reading is not available",
        published_by=reading.published_by,
    )


@dataclass(frozen=True, slots=True)
class Bound:
    """What a bounded list left out, and on what ranking.

    Returned even when nothing was cut. A reader who has to infer from a list of
    exactly twenty whether there were twenty-one is a reader who will sometimes
    infer wrong, and the cost of saying so is one field.
    """

    ranked_by: str
    shown: int
    total: int
    limit: int = MAX_REPORTED_ITEMS

    @property
    def bounded(self) -> bool:
        """Return whether anything was left out."""
        return self.total > self.shown

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a result carries."""
        return {
            "bounded": self.bounded,
            "ranked_by": self.ranked_by,
            "shown": self.shown,
            "total": self.total,
            "limit": self.limit,
        }


def bounded[Item](
    items: Iterable[Item],
    *,
    ranked_by: str,
    key: Callable[[Item], Any],
    limit: int = MAX_REPORTED_ITEMS,
) -> tuple[tuple[Item, ...], Bound]:
    """Return the highest-ranking ``limit`` of ``items``, and what that left out.

    Ranked and then cut, never cut and then ranked. A thousand snapshots
    truncated at twenty is twenty arbitrary snapshots; a thousand snapshots
    ranked by size and cut at twenty is the twenty that would free the space.
    """
    ordered = sorted(items, key=key, reverse=True)
    kept = tuple(ordered[:limit])
    return kept, Bound(ranked_by=ranked_by, shown=len(kept), total=len(ordered), limit=limit)


def report(
    capability: str,
    *,
    value: dict[str, Any],
    summary: str,
    reference: str,
    evidence_type: EvidenceType = EvidenceType.METRIC,
    undetermined: Sequence[Undetermined | None] = (),
    bounds: Sequence[tuple[str, Bound]] = (),
) -> CapabilityResult:
    """Return one investigation answer, with its holes and its bounds attached.

    Every tool in this package ends here, which is what makes "states what it
    could not determine" a property of the package rather than a habit of
    whoever wrote each tool. ``undetermined`` accepts ``None`` entries so a
    caller can pass ``gap(reading, "...")`` directly for a reading that may well
    have been fine.
    """
    holes = [entry for entry in undetermined if entry is not None]
    payload = dict(value)
    payload["undetermined"] = [entry.to_record() for entry in holes]
    if bounds:
        payload["bounds"] = {name: bound.to_record() for name, bound in bounds}

    line = summary
    if holes:
        line = f"{summary}. Not determined: {'; '.join(entry.question for entry in holes)}"

    return CapabilityResult.ok(
        capability,
        value=payload,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=evidence_type,
                summary=line,
                reference=reference,
            ),
        ),
    )


def scrub_finished_at(scan: str) -> datetime | None:
    """Return when the last scrub finished, from the line ``zpool status`` prints.

    ZFS reports this as prose and nowhere else, so it is parsed rather than read:
    ``... with 0 errors on Sun Jun  8 04:12:31 2025``. Returning ``None`` rather
    than guessing is the point — a scrub age nobody can establish is reported as
    undetermined, and an invented one would be indistinguishable from a fresh
    scrub that never happened.
    """
    marker = " on "
    if marker not in scan:
        return None
    stamp = " ".join(scan.rsplit(marker, 1)[1].split())
    try:
        return datetime.strptime(stamp, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def age_in_days(moment: datetime, *, now: datetime) -> float:
    """Return how many days ago ``moment`` was."""
    return (now - moment).total_seconds() / 86_400.0


def seconds_as_phrase(seconds: float) -> str:
    """Return a duration an operator reads rather than converts.

    Recovery-point exposure is the number this exists for. "604800" and "7 days"
    are the same fact and only one of them is read as a week of lost work.
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3_600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86_400:
        return f"{seconds / 3_600:.1f}h"
    return f"{seconds / 86_400:.1f} days"


__all__ = [
    "CLOCK_SKEW_TOLERANCE_SECONDS",
    "LINK_FLAP_TRANSITIONS",
    "MAX_REPORTED_ITEMS",
    "PREDICTIVE_SMART_ATTRIBUTES",
    "SCRUB_STALE_DAYS",
    "ZFS_CAPACITY_DEGRADED_PERCENT",
    "Bound",
    "Undetermined",
    "age_in_days",
    "bounded",
    "gap",
    "observed_now",
    "reading_as_of",
    "report",
    "scrub_finished_at",
    "seconds_as_phrase",
]
