"""Did the fault actually bite? The question that keeps this suite's number honest.

Without this module every chaos failure looks the same. The agent named the
wrong cause and the injection never took effect both produce a run that scores
badly, and a suite that cannot tell them apart reports a flaky cluster as an
agent regression — which is the specific way an expensive suite stops being
believed and then stops being run.

Three verdicts, not two. ``VALID`` means the declared symptom was observed and
the agent's answer is a measurement. ``INVALID`` means the fault demonstrably did
not produce it, and the run is reported rather than scored. ``UNKNOWN`` means the
probe itself could not be read — a third thing, because calling that invalid
would retire a working experiment and calling it valid would score the agent
against telemetry nobody confirmed.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from config.constants.chaos import CHAOS_VALIDITY_POLL_SECONDS
from tests.chaos.framework.catalogue import Expectation
from tests.chaos.framework.cluster import SymptomSource
from tests.harness.realruns import RunValidity

#: One vocabulary for both suites. A chaos experiment that did not bite and an
#: otel-demo flag that did not propagate are the same kind of non-event, and two
#: enums saying so would eventually disagree about what "unknown" means.
Validity = RunValidity


@dataclass(frozen=True, slots=True)
class ValidityVerdict:
    """What the probe saw, and what that means for whether the run may be scored."""

    validity: Validity
    probe: str
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    detail: str = ""
    looks: int = 0

    @property
    def valid(self) -> bool:
        """Return whether this run may be scored as a measurement of the agent."""
        return self.validity is Validity.VALID

    def to_record(self) -> dict[str, object]:
        """Return a JSON-serialisable record of this verdict."""
        return {
            "validity": self.validity.value,
            "probe": self.probe,
            "expected": list(self.expected),
            "observed": list(self.observed),
            "missing": list(self.missing),
            "detail": self.detail,
            "looks": self.looks,
        }


def probe_validity(
    source: SymptomSource,
    expectation: Expectation,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    poll_seconds: float = CHAOS_VALIDITY_POLL_SECONDS,
) -> ValidityVerdict:
    """Return whether ``expectation``'s fault produced its declared symptom.

    Polls rather than looking once. A fault takes a moment to show up in
    telemetry — a probe that read the cluster the instant after applying the
    manifest would report every experiment invalid, which is the failure mode
    that makes a validity gate worse than none.
    """
    probe = expectation.validity_probe
    expected = expectation.expected_symptom
    deadline = clock() + probe.timeout_seconds
    observed: tuple[str, ...] = ()
    looks = 0
    answered = False

    while True:
        reading = source.observe(probe.check, namespace=probe.namespace)
        looks += 1
        if reading.observed:
            answered = True
            observed = tuple(dict.fromkeys((*observed, *reading.observed)))
        missing = tuple(symptom for symptom in expected if symptom not in observed)
        if not missing:
            return ValidityVerdict(
                validity=Validity.VALID,
                probe=probe.check,
                expected=expected,
                observed=observed,
                detail=f"every declared symptom was observed after {looks} looks",
                looks=looks,
            )
        if clock() >= deadline:
            break
        sleep(poll_seconds)

    missing = tuple(symptom for symptom in expected if symptom not in observed)
    if not answered:
        return ValidityVerdict(
            validity=Validity.UNKNOWN,
            probe=probe.check,
            expected=expected,
            missing=missing,
            detail=(
                f"the probe {probe.check!r} returned nothing in {probe.timeout_seconds:g}s, so "
                f"whether the fault took effect is not known; this run is reported, not scored"
            ),
            looks=looks,
        )
    return ValidityVerdict(
        validity=Validity.INVALID,
        probe=probe.check,
        expected=expected,
        observed=observed,
        missing=missing,
        detail=(
            f"the injection did not produce {list(missing)} within {probe.timeout_seconds:g}s; "
            f"the experiment failed, not the agent"
        ),
        looks=looks,
    )


__all__ = ["Validity", "ValidityVerdict", "probe_validity"]
