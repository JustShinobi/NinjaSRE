"""What a capability says about how anybody would know its change worked.

Feature 017 gave every remediation capability four components. This adds the
fifth thing it has to declare, and the declaration is the whole of the closed
loop's honesty: which signals the effect appears in, and how long to wait before
they mean anything.

**The declaration is required, including the declaration that there is none.**
``VerificationDeclaration.unverifiable(reason)`` is how a capability says its
effect has no signal, and the reason is not optional. An optional declaration
would be omitted first, and by exactly the capabilities whose effect is hardest
to measure — which is the opposite of where the effort belongs.

**The settle period is on the capability, not on the deployment.** How long a
filesystem takes to reflect a reclaim and how long a scheduler takes to place a
pod are facts about those operations, not preferences an operator holds. A
global wait would be too short for one and too long for the other.

**A move smaller than the noise floor is ``inconclusive``.** The available
simplification here is to treat "did not clearly get worse" as success. That
produces a system with a high reported success rate and an operator who stops
believing it, so the verdict a sub-threshold move reaches is the honest one.

**A clearing value is what makes ``ineffective`` distinguishable.** With one,
"the condition still holds" is a fact and the verdict is ``ineffective``.
Without one, all that is known is how far the signal moved, and a small move can
only be ``inconclusive`` — which is why declaring a clearing value is worth the
thought it costs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from config.constants.closed_loop import (
    DEFAULT_SETTLE_SECONDS,
    MAX_SETTLE_SECONDS,
    MIN_SETTLE_SECONDS,
    VERIFICATION_MINIMUM_CHANGE,
)
from platform.persistence.ports.remediation_ledger import VerificationVerdict
from platform.remediation.errors import UndeclaredVerification, UnknownVerificationSignal


class SignalDirection(StrEnum):
    """Which way a signal moves when the action worked.

    Declared rather than inferred from the values, because a signal that
    happened to fall on one occasion tells you nothing about which direction is
    the good one — and a system that guessed would credit itself for a metrics
    pipeline hiccup.
    """

    #: Smaller is better: disk usage, error rate, restart count.
    DOWN = "down"
    #: Larger is better: ready replicas, available memory, healthy nodes.
    UP = "up"


#: How the four verdicts a comparison can reach rank against each other when
#: several signals disagree. Worst first: one signal getting worse is not offset
#: by another getting better, and a verdict that averaged them would be a
#: verdict nobody could act on.
_SEVERITY: tuple[VerificationVerdict, ...] = (
    VerificationVerdict.WORSENED,
    VerificationVerdict.INEFFECTIVE,
    VerificationVerdict.INCONCLUSIVE,
    VerificationVerdict.EFFECTIVE,
)


@dataclass(frozen=True, slots=True)
class VerificationSignal:
    """One signal the effect of an action should be visible in.

    ``clears_at`` is the value at which the condition the action was taken
    against no longer holds — the detector's own clearing threshold, restated
    here because a capability may be used against several detectors and this is
    the one that decides whether *this* action worked.
    """

    name: str
    direction: SignalDirection = SignalDirection.DOWN
    #: The smallest relative move that is evidence of anything, as a fraction of
    #: the value before the action. Below it, the verdict is ``inconclusive``.
    minimum_change: float = VERIFICATION_MINIMUM_CHANGE
    #: The value at which the condition is cleared, when the capability can name
    #: one. ``None`` means it cannot, and the cost is that a small move is
    #: ``inconclusive`` rather than ``ineffective``.
    clears_at: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A verification signal needs the name it is read back by.")
        if not 0.0 < self.minimum_change < 1.0:
            raise ValueError(
                f"{self.name}: a minimum change of {self.minimum_change} is not a fraction "
                f"of the value before the action. Zero would make every fluctuation an "
                f"effect, and one would make nothing an effect."
            )

    def cleared(self, value: float) -> bool:
        """Return whether ``value`` is on the side of ``clears_at`` that means fixed."""
        if self.clears_at is None:
            return False
        if self.direction is SignalDirection.DOWN:
            return value <= self.clears_at
        return value >= self.clears_at

    def verdict_for(self, *, before: float | None, after: float | None) -> VerificationVerdict:
        """Return what this signal's before-and-after values say about the action.

        ``None`` on either side is ``inconclusive`` and never anything else: a
        resource that went away between the action and the check did not have
        its condition cleared, and reporting the absence as success is FR-022's
        whole subject.
        """
        if before is None or after is None:
            return VerificationVerdict.INCONCLUSIVE

        if self.cleared(after):
            return VerificationVerdict.EFFECTIVE

        moved = after - before
        # Relative to the value the action started from, so a threshold means
        # the same thing on a disk at 96% and an error rate of 0.4.
        scale = abs(before) if before else 1.0
        if abs(moved) / scale < self.minimum_change:
            # Not enough movement to conclude anything from — unless a clearing
            # value was declared, in which case the condition demonstrably still
            # holds and "it did not work" is a fact rather than a guess.
            if self.clears_at is None:
                return VerificationVerdict.INCONCLUSIVE
            return VerificationVerdict.INEFFECTIVE

        improved = moved < 0 if self.direction is SignalDirection.DOWN else moved > 0
        if not improved:
            return VerificationVerdict.WORSENED
        if self.clears_at is None:
            return VerificationVerdict.EFFECTIVE
        return VerificationVerdict.INEFFECTIVE


@dataclass(frozen=True, slots=True)
class VerificationDeclaration:
    """Which signals one capability's effect appears in, and when to read them.

    Construct it with signals, or with ``unverifiable(reason)``. There is no
    third state: a declaration with neither signals nor a reason is a capability
    nobody finished, and it is refused here rather than discovered as a run of
    ``inconclusive`` verdicts nobody could explain.
    """

    signals: tuple[VerificationSignal, ...] = ()
    settle_seconds: int = DEFAULT_SETTLE_SECONDS
    #: Why this capability has no verifiable effect. Required when, and only
    #: when, there are no signals.
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.signals:
            if not self.reason.strip():
                raise UndeclaredVerification()
            return
        if self.reason.strip():
            raise ValueError(
                "A capability that declares signals is verifiable, so a reason it cannot "
                "be verified describes something that is not the case. Declare one or "
                "the other."
            )
        if not MIN_SETTLE_SECONDS <= self.settle_seconds <= MAX_SETTLE_SECONDS:
            raise ValueError(
                f"A settle period of {self.settle_seconds}s is outside "
                f"[{MIN_SETTLE_SECONDS}, {MAX_SETTLE_SECONDS}]. Below the floor the "
                f"verification reads the sample the detector already fired on; above the "
                f"ceiling nobody connects the verdict to the action that earned it."
            )

    @classmethod
    def unverifiable(cls, reason: str) -> VerificationDeclaration:
        """Return the declaration that this capability's effect has no signal.

        A named constructor rather than an empty tuple at each call site,
        because the reason is the whole value of the declaration and a
        positional empty tuple is what "nobody got round to it" looks like.
        """
        if not reason.strip():
            raise UndeclaredVerification()
        return cls(signals=(), settle_seconds=0, reason=reason)

    @property
    def verifiable(self) -> bool:
        """Return whether anything here could tell you the action worked."""
        return bool(self.signals)

    @property
    def names(self) -> tuple[str, ...]:
        """Return the signal names this declaration reads, in declared order."""
        return tuple(signal.name for signal in self.signals)

    def validate_against(self, known: Sequence[str]) -> None:
        """Raise when a declared signal is not one this deployment produces.

        Checked at registration rather than at verification time. A capability
        naming a signal no source emits verifies against nothing forever, and
        reports ``inconclusive`` every time — which reads exactly like a system
        that is genuinely hard to measure, and is not.
        """
        if not self.verifiable:
            return
        available = set(known)
        for signal in self.signals:
            if signal.name not in available:
                raise UnknownVerificationSignal(signal.name, known=tuple(sorted(available)))

    def verdict_for(
        self,
        *,
        before: Mapping[str, float],
        after: Mapping[str, float],
    ) -> VerificationVerdict:
        """Return the worst verdict this declaration's signals reach.

        Worst rather than an average or a majority. Two signals disagreeing is
        information, and the one that got worse is the one somebody has to look
        at — an averaged verdict would hide it behind the one that improved.
        """
        if not self.verifiable:
            return VerificationVerdict.UNVERIFIABLE

        reached = [
            signal.verdict_for(before=before.get(signal.name), after=after.get(signal.name))
            for signal in self.signals
        ]
        for verdict in _SEVERITY:
            if verdict in reached:
                return verdict
        return VerificationVerdict.INCONCLUSIVE

    def describe(self) -> str:
        """Return the sentence an operator reads about how this is checked."""
        if not self.verifiable:
            return f"Not verifiable: {self.reason}"
        listed = ", ".join(
            f"{signal.name} {signal.direction.value}"
            + (f" to {signal.clears_at:g}" if signal.clears_at is not None else "")
            for signal in self.signals
        )
        return f"Verified after {self.settle_seconds}s by reading {listed}."

    def to_record(self) -> dict[str, object]:
        """Return the stored form the ledger row and the API response carry."""
        return {
            "verifiable": self.verifiable,
            "settle_seconds": self.settle_seconds,
            "reason": self.reason,
            "signals": [
                {
                    "name": signal.name,
                    "direction": signal.direction.value,
                    "minimum_change": signal.minimum_change,
                    "clears_at": signal.clears_at,
                }
                for signal in self.signals
            ],
        }


#: The declaration a registry hands back when nothing was declared at all. Not a
#: default a capability may inherit — ``RemediationComponents`` requires the
#: field — but the honest answer for a capability this deployment has no
#: components for, which is a question the gate can be asked.
NOTHING_DECLARED: VerificationDeclaration = VerificationDeclaration(
    signals=(),
    settle_seconds=0,
    reason="this deployment has no remediation components registered for that capability",
)


def signals_of(declarations: Sequence[VerificationDeclaration]) -> tuple[str, ...]:
    """Return every signal name ``declarations`` between them read, deduplicated."""
    found: set[str] = set()
    for declaration in declarations:
        found.update(declaration.names)
    return tuple(sorted(found))


__all__ = [
    "NOTHING_DECLARED",
    "SignalDirection",
    "VerificationDeclaration",
    "VerificationSignal",
    "signals_of",
]
