"""Evaluating one detector against one window, and nothing else.

Every function here is pure. It takes a declaration, a window, and an instant,
and returns a verdict. It reads no clock, opens no transaction, and holds no
state between calls — which is what makes a detector replayable against stored
history and therefore testable at all.

**State lives in the signals, not in the detector.** There is no "pending since"
counter anywhere in this package. A condition has held for ten minutes when
*every sample in the last ten minutes* satisfies it and the samples actually
span ten minutes. That is why a restart mid-evaluation cannot double-fire and
two replicas cannot disagree: neither is remembering anything, so there is
nothing for them to remember differently.

**"Not yet" is a verdict, not an absence of one.** ``PENDING`` says the
condition is true and has not held long enough; ``INSUFFICIENT`` says we have
not been watching long enough to know. Collapsing either into "nothing wrong" is
how a deployment reports health it has not established.

**Flapping outranks firing.** A signal that crossed its threshold three times
inside the flap window produces ``FLAPPING`` rather than an incident, because
the useful thing to tell somebody is that the signal is unstable — three
incidents about the same oscillation are three interruptions and one fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from config.constants.observation import FLAP_CROSSING_THRESHOLD, FLAP_WINDOW_SECONDS
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
)
from platform.observation.signals import SignalWindow


class Verdict(StrEnum):
    """What one evaluation of one detector against one subject concluded."""

    #: The condition has held for its declared duration.
    FIRING = "firing"
    #: The condition is true and has not held long enough yet.
    PENDING = "pending"
    #: Neither the condition nor the recovery condition is satisfied — the signal
    #: is between the two thresholds, which is what hysteresis is for.
    HOLDING = "holding"
    #: The recovery condition has held for its declared duration.
    CLEAR = "clear"
    #: The signal crossed too often to call either way.
    FLAPPING = "flapping"
    #: There is not enough history to say anything. Not the same as clear.
    INSUFFICIENT = "insufficient"

    @property
    def opens_an_incident(self) -> bool:
        """Return whether this verdict is one that raises."""
        return self in {Verdict.FIRING, Verdict.FLAPPING}


@dataclass(frozen=True, slots=True)
class Observation:
    """One evaluation, with the values it was reached from.

    Article I: a conclusion carries the observations that support it. ``values``
    and ``detail`` are not decoration — an incident is constructed from them,
    and an incident that could not say what it saw would be an assertion.
    """

    detector_id: str
    resource_id: str
    verdict: Verdict
    observed_at: datetime
    detail: str = ""
    #: The samples that decided it, as name-to-value. Bounded by the window.
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def is_finding(self) -> bool:
        """Return whether this observation is one that opens or sustains an incident."""
        return self.verdict.opens_an_incident


def evaluate(
    detector: DetectorDeclaration,
    window: SignalWindow,
    *,
    now: datetime,
) -> Observation:
    """Return what ``detector`` concludes about ``window`` at ``now``.

    Pure with respect to its inputs, so the same window replayed a month later
    reproduces the same verdict. That property is what makes a detector testable
    against history rather than only against a live estate.
    """
    if detector.condition.kind is ConditionKind.ABSENCE:
        return _absence(detector, window, now=now)

    if window.is_empty:
        return _observation(
            detector,
            window,
            Verdict.INSUFFICIENT,
            now,
            detail=f"no {detector.signal} samples inside the window",
        )

    crossings = _crossings(detector.condition, window)
    if _is_flapping(crossings, window, now=now):
        return _observation(
            detector,
            window,
            Verdict.FLAPPING,
            now,
            detail=(
                f"{detector.signal} crossed its threshold {len(crossings)} times in the "
                f"last {FLAP_WINDOW_SECONDS // 60} minutes"
            ),
            evidence={"crossings": str(len(crossings))},
        )

    judged = _judged_indices(detector.condition, window)
    if not judged:
        return _observation(
            detector,
            window,
            Verdict.INSUFFICIENT,
            now,
            detail=f"one {detector.signal} sample is not a rate of change",
        )

    firing = [_fires(detector.condition, window, index) for index in judged]
    clearing = [_clears(detector.condition, window, index) for index in judged]

    if all(firing):
        if not window.covers(detector.for_seconds):
            return _observation(
                detector,
                window,
                Verdict.PENDING,
                now,
                detail=(
                    f"{detector.signal} satisfies the condition and has not held it for "
                    f"{detector.for_seconds}s yet"
                ),
            )
        return _observation(detector, window, Verdict.FIRING, now, detail=_why(detector, window))

    if all(clearing) and window.covers(detector.recovery_seconds):
        return _observation(
            detector,
            window,
            Verdict.CLEAR,
            now,
            detail=f"{detector.signal} has been within its clear value for the recovery window",
        )

    if firing[-1]:
        return _observation(
            detector,
            window,
            Verdict.PENDING,
            now,
            detail=f"{detector.signal} has only just crossed",
        )

    return _observation(
        detector,
        window,
        Verdict.HOLDING,
        now,
        detail=f"{detector.signal} is between its firing and clearing values",
    )


def _absence(detector: DetectorDeclaration, window: SignalWindow, *, now: datetime) -> Observation:
    """Return the verdict for a series that may have stopped arriving.

    A series nobody has ever measured is ``INSUFFICIENT`` rather than firing.
    "It stopped" and "it never started" are different facts, and a detector that
    conflated them would fire on every resource an integration does not cover —
    which is most of an estate on the day a second integration is added.
    """
    silence = window.silence(now)
    if silence is None:
        return _observation(
            detector,
            window,
            Verdict.INSUFFICIENT,
            now,
            detail=f"{detector.signal} has never been reported for this resource",
        )

    tolerance = detector.condition.silent_after_seconds
    if window.is_silent(now, tolerance_seconds=tolerance):
        if silence < timedelta(seconds=detector.for_seconds):
            return _observation(
                detector,
                window,
                Verdict.PENDING,
                now,
                detail=f"{detector.signal} has been quiet for {int(silence.total_seconds())}s",
            )
        return _observation(
            detector,
            window,
            Verdict.FIRING,
            now,
            detail=(f"{detector.signal} has not been reported for {int(silence.total_seconds())}s"),
            evidence={"silent_seconds": str(int(silence.total_seconds()))},
        )

    return _observation(
        detector,
        window,
        Verdict.CLEAR,
        now,
        detail=f"{detector.signal} is arriving",
    )


def _judged_indices(condition: Condition, window: SignalWindow) -> tuple[int, ...]:
    """Return the samples this condition has an opinion about.

    A rate of change has none about the first sample in a window: a change needs
    two readings, and counting the first as "not firing" would mean a window
    could never be entirely firing — so a signal climbing steadily would sit at
    pending for ever.
    """
    if condition.kind is ConditionKind.RATE_OF_CHANGE:
        return tuple(range(1, len(window.samples)))
    return tuple(range(len(window.samples)))


def _fires(condition: Condition, window: SignalWindow, index: int) -> bool:
    """Return whether the sample at ``index`` satisfies the firing condition."""
    sample = window.samples[index]
    match condition.kind:
        case ConditionKind.THRESHOLD:
            return _compares(sample.value, condition.fire_value, condition.comparison)
        case ConditionKind.RATE_OF_CHANGE:
            rate = _rate_at(window, index)
            return rate is not None and _compares(rate, condition.fire_value, condition.comparison)
        case ConditionKind.STATE_TRANSITION:
            if sample.state != condition.to_state:
                return False
            if not condition.from_state:
                return True
            previous = window.samples[index - 1].state if index else ""
            return previous == condition.from_state
        case ConditionKind.ABSENCE:  # pragma: no cover — handled before this point
            return False


def _clears(condition: Condition, window: SignalWindow, index: int) -> bool:
    """Return whether the sample at ``index`` satisfies the recovery condition.

    The recovery condition is the *opposite* comparison against ``clear_value``,
    which is the whole of hysteresis: a signal between the two values is neither
    firing nor clearing, so it holds whatever state it was already in.
    """
    sample = window.samples[index]
    match condition.kind:
        case ConditionKind.THRESHOLD:
            return not _compares(sample.value, condition.clear_value, condition.comparison)
        case ConditionKind.RATE_OF_CHANGE:
            rate = _rate_at(window, index)
            return rate is None or not _compares(rate, condition.clear_value, condition.comparison)
        case ConditionKind.STATE_TRANSITION:
            return sample.state != condition.to_state
        case ConditionKind.ABSENCE:  # pragma: no cover — handled before this point
            return False


def _compares(value: float, against: float, comparison: Comparison) -> bool:
    """Return whether ``value`` is on the firing side of ``against``."""
    return value > against if comparison is Comparison.ABOVE else value < against


def _rate_at(window: SignalWindow, index: int) -> float | None:
    """Return the change per minute between this sample and the one before it.

    ``None`` for the first sample, which has nothing to be a change from. Per
    minute rather than per second because that is the unit an operator declares
    a rate in — "three per cent an hour" is a sentence and "0.00083 per second"
    is a typo waiting to happen.
    """
    if index == 0:
        return None
    previous, current = window.samples[index - 1], window.samples[index]
    elapsed = (current.observed_at - previous.observed_at).total_seconds()
    if elapsed <= 0:
        return None
    return (current.value - previous.value) / elapsed * 60.0


def _crossings(condition: Condition, window: SignalWindow) -> tuple[datetime, ...]:
    """Return the instants at which the signal entered the firing side.

    Entries only. A signal that went over, came back, and went over again
    crossed twice, and counting the returns as well would double every count and
    halve the flap threshold without anybody deciding to.
    """
    if condition.kind is ConditionKind.RATE_OF_CHANGE:
        return ()
    crossed: list[datetime] = []
    previously = False
    for index in range(len(window.samples)):
        now_firing = _fires(condition, window, index)
        if now_firing and not previously:
            crossed.append(window.samples[index].observed_at)
        previously = now_firing
    return tuple(crossed)


def _is_flapping(crossings: tuple[datetime, ...], window: SignalWindow, *, now: datetime) -> bool:
    """Return whether the signal crossed too often to call either way.

    Counted inside the flap window rather than inside the detector's own, so a
    detector with a twelve-hour window does not report a morning and an evening
    crossing as instability.
    """
    del window
    since = now - timedelta(seconds=FLAP_WINDOW_SECONDS)
    recent = [instant for instant in crossings if instant >= since]
    return len(recent) >= FLAP_CROSSING_THRESHOLD


def _why(detector: DetectorDeclaration, window: SignalWindow) -> str:
    """Return the sentence an incident carries about why this fired."""
    newest = window.newest
    if newest is None:  # pragma: no cover — callers check emptiness first
        return f"{detector.signal} satisfied {detector.condition.kind.value}"
    observed = newest.state or f"{newest.value:g}"
    return (
        f"{detector.signal} is {observed} and has satisfied "
        f"{detector.condition.kind.value} for {detector.for_seconds}s"
    )


def _observation(
    detector: DetectorDeclaration,
    window: SignalWindow,
    verdict: Verdict,
    now: datetime,
    *,
    detail: str = "",
    evidence: dict[str, str] | None = None,
) -> Observation:
    """Return one observation, with the newest sample attached as evidence."""
    carried = dict(evidence or {})
    newest = window.newest or window.last_seen
    if newest is not None:
        carried.setdefault(newest.name, newest.state or f"{newest.value:g}")
        carried.setdefault("observed_at", newest.observed_at.isoformat())
    return Observation(
        detector_id=detector.detector_id,
        resource_id=window.resource_id,
        verdict=verdict,
        observed_at=now,
        detail=detail,
        evidence=carried,
    )


__all__ = ["Observation", "Verdict", "evaluate"]
