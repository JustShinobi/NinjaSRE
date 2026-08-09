"""What one run of one scenario did, in the shape the scorer reads.

A recorded run rather than a live one, and the distinction is worth being
explicit about. The *readings* in this suite are produced by the shipped
investigation tools running for real against recorded API responses, so a change
to a tool changes them. The *response* — the conclusion and the proposal — is
recorded, per model and per ablation arm, because reproducing it would need a
model and the whole point of the pull-request path is that it needs nothing.

That split is what NFR-003 asks for. Scoring is deterministic given a
transcript; the transcript is what a model produced; and the same transcript
scores the same on every machine, forever.

``completed`` is the field that keeps a small model's failure legible. A model
that ran out of context before reaching a conclusion did not conclude wrongly,
and a suite that recorded the two the same way would report a capability problem
where there is a capacity one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants.hypervisor_scenarios import (
    ARM_FULL,
    MODEL_HOSTED,
    SCENARIO_ABLATION_ARMS,
    SCENARIO_MODEL_PROFILES,
)
from tests.harness.proxmox.verdicts import ResponseKind


@dataclass(frozen=True, slots=True)
class ProposedAction:
    """What the run proposed doing about the situation.

    ``kind`` and not merely a capability name, because "escalate" and "propose
    nothing" are different responses and a scheme that recorded both as an empty
    capability could not tell them apart — which is precisely the distinction
    FR-008 turns on.
    """

    kind: ResponseKind
    capability: str = ""

    def __post_init__(self) -> None:
        if self.kind is ResponseKind.ACT and not self.capability:
            raise ValueError("a run that acted has to say which capability it proposed")
        if self.kind is not ResponseKind.ACT and self.capability:
            raise ValueError(
                f"a run recorded as {self.kind.value!r} names {self.capability!r}; a run either "
                f"proposed an action or it did not"
            )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form a score record carries."""
        return {"kind": self.kind.value, "capability": self.capability}


@dataclass(frozen=True, slots=True)
class RecordedRun:
    """One model's attempt at one scenario, under one ablation arm.

    Everything a score needs and nothing it does not. The full prose is kept in
    ``transcript`` rather than summarised, because FR-019 asks for the transcript
    to be retrievable from the scored run and a summary written at recording time
    is a summary nobody can go behind.
    """

    model: str = MODEL_HOSTED
    arm: str = ARM_FULL
    completed: bool = True
    diagnosis: str = ""
    #: What the conclusion cited, in the run's own words. Compared against the
    #: scenario's declared evidence by substring, so a run that named the tool
    #: without quoting anything it said does not pass the evidence axis.
    cited: tuple[str, ...] = ()
    said_insufficient: bool = False
    action: ProposedAction = ProposedAction(kind=ResponseKind.NONE)
    #: The planted confounders this run took the bait on, by the scenario's own
    #: names for them. Declared by the recording rather than inferred from prose,
    #: because inferring it would make the penalty depend on how a run phrased
    #: something rather than on what it did.
    took: tuple[str, ...] = ()
    transcript: str = ""
    #: Why the run stopped short, when it did. Required for an incomplete run:
    #: "the model could not finish" is only actionable with the reason attached.
    incomplete_reason: str = ""

    def __post_init__(self) -> None:
        if self.model not in SCENARIO_MODEL_PROFILES:
            raise ValueError(
                f"{self.model!r} is not a recorded model profile; the corpus records "
                f"{', '.join(SCENARIO_MODEL_PROFILES)}"
            )
        if self.arm not in SCENARIO_ABLATION_ARMS:
            raise ValueError(
                f"{self.arm!r} is not an ablation arm; the suite runs "
                f"{', '.join(SCENARIO_ABLATION_ARMS)}"
            )
        if not self.completed and not self.incomplete_reason.strip():
            raise ValueError(
                "a run that did not complete has to say why; 'the model could not finish' is "
                "only useful with the reason beside it"
            )
        if self.completed and self.incomplete_reason.strip():
            raise ValueError("a run that completed cannot also carry a reason it did not")

    @property
    def cell(self) -> str:
        """Return the ``model/arm`` cell this run occupies in the matrix."""
        return f"{self.model}/{self.arm}"

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record of what this run did (FR-019)."""
        return {
            "model": self.model,
            "arm": self.arm,
            "completed": self.completed,
            "diagnosis": self.diagnosis,
            "cited": list(self.cited),
            "said_insufficient": self.said_insufficient,
            "action": self.action.to_record(),
            "took": list(self.took),
            "transcript": self.transcript,
            "incomplete_reason": self.incomplete_reason,
        }


__all__ = ["ProposedAction", "RecordedRun"]
