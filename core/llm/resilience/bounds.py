"""How many times a model may be corrected before the run stops trying.

A correction is a model call. Left unbounded, a model that gets its arguments
wrong every turn would spend the whole iteration budget being told so, and the
run would end at the iteration ceiling reporting "the ceiling was reached" —
true, and useless to the operator deciding whether to change model.

So there are two bounds and they answer different questions. The **per-turn**
bound asks whether this model can act on being told; two attempts is enough to
find out, because the first names the problem and the second proves it cannot be
acted on. The **per-run** bound asks whether the run is worth continuing, and it
sits well below the iteration ceiling so that the run ends on this bound, with a
failure that names the model's behaviour, rather than on the ceiling.

Both live inside the existing ceilings rather than raising them. A repair is
spent from the same budget the investigation was already held to.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.llm import (
    MAX_TOOL_CALL_REPAIRS_PER_RUN,
    MAX_TOOL_CALL_REPAIRS_PER_TURN,
)


@dataclass(slots=True)
class RepairBudget:
    """The corrections one run may spend, per turn and in total."""

    per_turn: int = MAX_TOOL_CALL_REPAIRS_PER_TURN
    per_run: int = MAX_TOOL_CALL_REPAIRS_PER_RUN
    spent_this_turn: int = 0
    spent_this_run: int = 0

    def __post_init__(self) -> None:
        if self.per_turn < 0 or self.per_run < 0:
            raise ValueError("a repair bound must not be negative")

    @property
    def turn_remaining(self) -> int:
        """Return how many corrections this turn may still send."""
        return max(min(self.per_turn - self.spent_this_turn, self.per_run - self.spent_this_run), 0)

    def spend(self) -> bool:
        """Spend one correction, returning whether there was one to spend."""
        if self.turn_remaining <= 0:
            return False
        self.spent_this_turn += 1
        self.spent_this_run += 1
        return True

    def next_turn(self) -> None:
        """Reset the per-turn count, leaving the run total alone."""
        self.spent_this_turn = 0


__all__ = ["RepairBudget"]
