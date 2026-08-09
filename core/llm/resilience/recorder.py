"""Where a repair goes once it has happened.

Counting is not decoration. A model that needs three corrections a turn and one
that needs none produce the same investigations at very different cost, and
without a count the operator has no way to learn that changing model would
double their throughput. So every repair and every degradation is offered to a
recorder, per model, and what a deployment does with them is the observability
tier's business rather than this layer's.

The default records nothing and is not a branch. A layer that asked "is
telemetry on" before each repair would be a layer somebody eventually forgot to
ask in, which is the failure this shape exists to make impossible.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.llm.types import Repair


@runtime_checkable
class RepairRecorder(Protocol):
    """Somewhere a repair can be counted, per model."""

    def record_repair(self, repair: Repair, *, provider_id: str, model_id: str) -> None:
        """Count one repair against the model that made it necessary."""

    def record_degradation(self, cause: str, *, provider_id: str, model_id: str) -> None:
        """Count one run that degraded because of the model's behaviour."""


class NullRecorder:
    """Accepts everything and keeps nothing."""

    def record_repair(self, repair: Repair, *, provider_id: str, model_id: str) -> None:
        """Discard ``repair``."""

    def record_degradation(self, cause: str, *, provider_id: str, model_id: str) -> None:
        """Discard ``cause``."""


#: What a layer nobody configured a recorder for writes to.
NO_RECORDER: RepairRecorder = NullRecorder()


__all__ = ["NO_RECORDER", "NullRecorder", "RepairRecorder"]
