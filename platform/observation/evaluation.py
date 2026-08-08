"""One tick: read the windows, evaluate every detector, report what was found.

The tick is the only part of observation that touches a store, and it is
deliberately thin. It reads signals in bulk, builds windows, and calls the pure
evaluator once per detector per series. Everything that decides anything is in
``detectors/conditions.py``, which has no clock and no transaction — so a tick
can be replayed against stored history by handing the same windows to the same
functions.

**Reads are per signal, not per detector.** A hundred detectors over ten
thousand resources is a million evaluations and would be a million queries if
each detector fetched its own window. One query per distinct signal name, once,
is what makes the budget in ``config.constants.observation`` reachable — and it
is why the tick holds the windows rather than the detectors holding them.

**Nothing is remembered between ticks.** There is no "pending since" table, no
last-verdict cache, and no in-memory state that survives a restart. A condition
has held for ten minutes when the last ten minutes of samples say so. That is
what makes a restart mid-tick harmless and two replicas agree: neither is
remembering anything, so there is nothing for them to remember differently.

**A detector that throws is a finding about the detector.** It is not skipped
and it is not logged and forgotten. The worst failure mode of any monitoring
system is looking healthy because it stopped looking, so an evaluation failure
comes back in the outcome as its own attention item and the caller raises an
incident about it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.observation import MAX_SIGNAL_PAGE_SIZE
from platform.observability.logging import get_logger
from platform.observation.detectors.conditions import Observation, Verdict, evaluate
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.signals import SeriesKey, SignalWindow, windows
from platform.observation.suppression import Suppression, Suppressor
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.signal_store import Signal, SignalQuery, SignalStore

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DetectorFailure:
    """A detector that could not be evaluated, and why.

    An attention item in its own right. A monitoring system that reports health
    because it stopped looking is the failure this record exists to make
    impossible to miss — which is why it travels in the outcome beside the
    findings rather than in a log line.
    """

    detector_id: str
    reason: str
    failed_at: datetime
    resource_id: str = ""

    @property
    def summary(self) -> str:
        """Return the sentence an incident about this failure carries."""
        return (
            f"detector {self.detector_id!r} could not be evaluated: {self.reason}. "
            f"Until it can be, nothing is watching for what it watches for."
        )


@dataclass(frozen=True, slots=True)
class TickOutcome:
    """Everything one evaluation pass concluded.

    ``evaluated`` is every verdict including the quiet ones, because "we looked
    and it was fine" is what makes a detector's coverage countable. ``findings``
    is the subset that opens or sustains an incident.
    """

    started_at: datetime
    finished_at: datetime
    detectors: int = 0
    subjects: int = 0
    evaluated: tuple[Observation, ...] = ()
    failures: tuple[DetectorFailure, ...] = ()
    #: Findings that were not raised, each naming the rule that covered it.
    #: Recorded rather than dropped: an operator asking "why did nothing happen"
    #: has to get an answer, and a rule that is too broad has to be countable.
    suppressed: tuple[Suppression, ...] = ()
    #: Whether the whole deployment was paused for this tick, and why. On the
    #: outcome so a tick that found nothing can say which kind of nothing.
    paused: bool = False
    pause_reason: str = ""

    @property
    def findings(self) -> tuple[Observation, ...]:
        """Return the observations that open or sustain an incident.

        Suppressed ones are excluded here and present in ``suppressed``. They
        are not lost: the intake raises them as suppressed incidents, which is
        what makes "nothing happened because of this rule" a countable fact.
        """
        covered = {(entry.detector_id, entry.resource_id) for entry in self.suppressed}
        return tuple(
            entry
            for entry in self.evaluated
            if entry.is_finding and (entry.detector_id, entry.resource_id) not in covered
        )

    @property
    def cleared(self) -> tuple[Observation, ...]:
        """Return the observations that would close an incident."""
        return tuple(entry for entry in self.evaluated if entry.verdict is Verdict.CLEAR)

    @property
    def seconds(self) -> float:
        """Return how long the pass took."""
        return (self.finished_at - self.started_at).total_seconds()


def evaluate_all(
    detectors: Sequence[DetectorDeclaration],
    windows_by_series: dict[SeriesKey, SignalWindow],
    *,
    kinds: dict[str, str],
    now: datetime,
) -> tuple[tuple[Observation, ...], tuple[DetectorFailure, ...]]:
    """Return every verdict these detectors reach, and every one that could not be reached.

    The pure core of the tick, and the function a replay calls. It reads no
    clock, opens no transaction, and given the same windows returns the same
    observations — which is what makes "this detector would have fired at 03:14
    last Tuesday" a statement somebody can check.
    """
    observations: list[Observation] = []
    failures: list[DetectorFailure] = []

    # Grouped once rather than filtered per detector. Ten detectors sharing a
    # signal is the ordinary case, and scanning every series ten times is the
    # difference between a hundred thousand comparisons and a million.
    by_signal: dict[str, list[SignalWindow]] = {}
    for (name, _), window in windows_by_series.items():
        by_signal.setdefault(name, []).append(window)

    for detector in detectors:
        for window in by_signal.get(detector.signal, ()):
            resource_id = window.resource_id
            if not detector.applies_to(kinds.get(resource_id, "")):
                continue
            try:
                observations.append(evaluate(detector, window, now=now))
            except Exception as broken:  # noqa: BLE001 - see DetectorFailure
                # Deliberately broad. Whatever a detector managed to raise, the
                # one outcome that must not follow is the deployment quietly
                # continuing as though nothing watches this resource.
                failures.append(
                    DetectorFailure(
                        detector_id=detector.detector_id,
                        reason=f"{type(broken).__name__}: {broken}",
                        failed_at=now,
                        resource_id=resource_id,
                    )
                )
                logger.error(
                    "observation.detector_failed",
                    detector_id=detector.detector_id,
                    resource_id=resource_id,
                    reason=str(broken),
                )

    return tuple(observations), tuple(failures)


@dataclass(frozen=True, slots=True)
class EvaluationTick:
    """One pass over the estate with one set of detectors."""

    detectors: tuple[DetectorDeclaration, ...] = ()
    #: What stops a finding being raised. Applied after evaluation rather than
    #: before it, so a suppressed detector is still *evaluated* — which is what
    #: keeps "we looked and it was covered" distinguishable from "we did not
    #: look", and what makes the suppression itself recordable.
    suppressor: Suppressor | None = None
    #: Series to read in one page. Bounded by the store's own limit, which is
    #: what stops a tick asking for more history than a window can hold.
    page_size: int = MAX_SIGNAL_PAGE_SIZE

    async def run(
        self,
        signals: SignalStore,
        *,
        resources: Sequence[Resource],
        now: datetime,
    ) -> TickOutcome:
        """Evaluate every detector over ``resources`` and return what was concluded."""
        started_at = now
        kinds = {resource.resource_id: resource.kind for resource in resources}
        subjects = tuple(kinds)

        by_series = await self._windows(signals, subjects=subjects, now=now)
        observations, failures = evaluate_all(self.detectors, by_series, kinds=kinds, now=now)

        outcome = TickOutcome(
            started_at=started_at,
            finished_at=now,
            detectors=len(self.detectors),
            subjects=len(subjects),
            evaluated=observations,
            failures=failures,
            suppressed=self._suppressions(observations, now=now),
            paused=bool(self.suppressor and self.suppressor.paused),
            pause_reason=self.suppressor.pause_reason if self.suppressor else "",
        )
        logger.info(
            "observation.tick",
            detectors=outcome.detectors,
            subjects=outcome.subjects,
            findings=len(outcome.findings),
            suppressed=len(outcome.suppressed),
            failures=len(outcome.failures),
        )
        return outcome

    def _suppressions(
        self, observations: Sequence[Observation], *, now: datetime
    ) -> tuple[Suppression, ...]:
        """Return one suppression per finding something covered."""
        if self.suppressor is None:
            return ()
        by_id = {detector.detector_id: detector for detector in self.detectors}
        covered: list[Suppression] = []
        for observation in observations:
            if not observation.is_finding:
                continue
            detector = by_id.get(observation.detector_id)
            if detector is None:  # pragma: no cover — the tick owns both lists
                continue
            verdict = self.suppressor.verdict(
                detector=detector, resource_id=observation.resource_id, at=now
            )
            if verdict is not None:
                covered.append(verdict)
        return tuple(covered)

    async def _windows(
        self,
        signals: SignalStore,
        *,
        subjects: tuple[str, ...],
        now: datetime,
    ) -> dict[SeriesKey, SignalWindow]:
        """Return one window per series, read one query per signal name.

        Per name rather than per detector: several detectors routinely watch the
        same signal at different thresholds, and fetching the window once is the
        difference between a hundred queries and the ten there are signals.
        """
        built: dict[SeriesKey, SignalWindow] = {}

        for name, horizon in _horizons(self.detectors).items():
            opened_at = now - timedelta(seconds=horizon)
            samples = await signals.window(
                SignalQuery(
                    names=(name,),
                    resource_ids=subjects,
                    since=opened_at,
                    until=now,
                    limit=self.page_size,
                )
            )
            latest = await signals.latest(names=(name,), resource_ids=subjects)
            for window in windows(samples, opened_at=opened_at, closed_at=now, latest=latest):
                built[window.key] = window

        return built


def replay(
    detectors: Sequence[DetectorDeclaration],
    history: Iterable[Signal],
    *,
    at: datetime,
    kinds: dict[str, str] | None = None,
) -> tuple[Observation, ...]:
    """Return what these detectors would have concluded at ``at``, from ``history``.

    The whole of replayability. Nothing is read, nothing is written, and the
    result depends only on the samples and the instant — so a detector can be
    held to "reproduce exactly the firings that happened" as a unit test rather
    than as an integration one.
    """
    samples = tuple(history)
    horizons = _horizons(detectors)
    resolved = kinds or {}
    built: dict[SeriesKey, SignalWindow] = {}

    for name, horizon in horizons.items():
        opened_at = at - timedelta(seconds=horizon)
        inside = tuple(
            sample
            for sample in samples
            if sample.name == name and opened_at <= sample.observed_at <= at
        )
        before = tuple(
            sample for sample in samples if sample.name == name and sample.observed_at <= at
        )
        for window in windows(inside, opened_at=opened_at, closed_at=at, latest=before):
            built[window.key] = window

    observations, _ = evaluate_all(detectors, built, kinds=resolved, now=at)
    return observations


def _horizons(detectors: Iterable[DetectorDeclaration]) -> dict[str, int]:
    """Return the longest window each signal is read over.

    One horizon per signal rather than per detector, so two detectors over the
    same signal share a read. The longer of the two wins, because a window that
    is too long costs samples and a window that is too short costs a verdict.
    """
    horizons: dict[str, int] = {}
    for detector in detectors:
        current = horizons.get(detector.signal, 0)
        horizons[detector.signal] = max(current, detector.longest_window_seconds)
    return horizons


__all__ = [
    "DetectorFailure",
    "EvaluationTick",
    "TickOutcome",
    "evaluate_all",
    "replay",
]
