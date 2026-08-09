"""What the model costs an operator in attempts, counted per model.

The cost ledger next door measures what the *endpoint* charges. This measures
what the *weights* cost, which on a self-hosted deployment is the number that
can actually be acted on: an operator who can see that one model needs three
corrections a turn and another needs none can change model, and an operator who
cannot see it will conclude the platform is slow.

Two entry points, because repairs arrive at two different times.
:class:`ModelBehaviourRecorder` satisfies the resilience layer's recorder port
and is written to as each repair happens. :func:`record_turn` reads a finished
turn's guardrail actions, which is where compaction and result truncation are
recorded — those happen in the runtime rather than in the layer, and a metric
that only counted half of what the feature does would be worse than none.

Both are safe to call on a deployment with telemetry off. The registry accepts
every write and keeps nothing, which is why neither of these asks whether
telemetry is on: a call site with that branch on it is a call site somebody
eventually forgets to put the branch in.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.agent.turn import GuardrailActionKind, Turn
from core.llm.types import Repair, RepairKind
from platform.observability.metrics.definitions import MetricRegistry

#: Repair kinds that get an instrument of their own as well as a labelled slot
#: on ``model.repairs``. The spec names loop breaks, compactions and truncations
#: separately from repairs at large, and an operator looking at a dashboard row
#: wants each of those as a line rather than as one series among fifteen.
_OWN_INSTRUMENT: dict[RepairKind, str] = {
    RepairKind.REPETITION_BROKEN: "model.loop_breaks",
    RepairKind.TRANSCRIPT_COMPACTED: "model.compactions",
    RepairKind.RESULT_TRUNCATED: "model.truncations",
}

#: Guardrail actions the runtime records that mean the same thing as a repair.
_FROM_GUARDRAIL: dict[GuardrailActionKind, RepairKind] = {
    GuardrailActionKind.TRANSCRIPT_COMPACTED: RepairKind.TRANSCRIPT_COMPACTED,
    GuardrailActionKind.RESULT_TRUNCATED: RepairKind.RESULT_TRUNCATED,
}


@dataclass(slots=True)
class ModelBehaviourRecorder:
    """Counts repairs and degradations against the model that needed them."""

    metrics: MetricRegistry

    def record_repair(self, repair: Repair, *, provider_id: str, model_id: str) -> None:
        """Count one repair, on the general instrument and on its own if it has one."""
        self.metrics.counter("model.repairs").add(
            1, model=model_id, provider=provider_id, kind=repair.kind.value
        )
        own = _OWN_INSTRUMENT.get(repair.kind)
        if own is not None:
            self.metrics.counter(own).add(1, model=model_id, provider=provider_id)

    def record_degradation(self, cause: str, *, provider_id: str, model_id: str) -> None:
        """Count one run that degraded because of how the model behaved."""
        self.metrics.counter("model.degradations").add(
            1, model=model_id, provider=provider_id, kind=cause
        )


def _repair_kind_of(reason: str) -> RepairKind | None:
    """Return the repair kind a recorded reason opens with, if it is one.

    The runtime writes ``"<kind>: <detail>"`` into the guardrail action's reason
    because the trace is prose an operator reads. Reading the kind back out
    keeps the metric and the trace one fact rather than two that can disagree.
    """
    head = reason.split(":", 1)[0].strip()
    try:
        return RepairKind(head)
    except ValueError:
        return None


def record_turn(metrics: MetricRegistry, turn: Turn) -> None:
    """Count everything one finished turn had to do to the model's output.

    Reads the turn rather than being told, so a mechanism that starts recording
    a guardrail action is counted without a second call site being added — and
    a turn that needed nothing writes nothing at all, which is what keeps a
    well-behaved model's dashboard empty rather than full of zeroes.
    """
    recorder = ModelBehaviourRecorder(metrics=metrics)
    for action in turn.guardrail_actions:
        kind = _FROM_GUARDRAIL.get(action.kind)
        if kind is None and action.kind is GuardrailActionKind.MODEL_OUTPUT_REPAIRED:
            kind = _repair_kind_of(action.reason)
        if kind is None:
            continue
        recorder.record_repair(
            Repair(kind=kind, capability=action.target),
            provider_id=turn.provider_id,
            model_id=turn.model_id,
        )


__all__ = ["ModelBehaviourRecorder", "record_turn"]
