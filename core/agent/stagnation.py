"""Noticing that a loop has stopped learning, before its ceiling notices.

The iteration ceiling bounds the worst case and nothing else. A run that has
spent four iterations re-reading the same log query will spend the remaining
sixteen the same way, and every one of them costs a model call and an operator's
patience.

So the loop counts iterations that produced no fresh evidence. Each one gets a
nudge naming what happened and how much rope is left. At the threshold, tool
access is withdrawn and the model gets one text-only turn to answer from what it
has — which it always can, because a run that gathered nothing new for three
iterations was not about to gather anything on the fourth.

"No fresh evidence" is a precise claim, and ``Turn.produced_fresh_evidence``
owns it: a replayed call did not produce evidence, and neither did a failed one,
however much prose the model wrote around them.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.investigation import MAX_STAGNANT_ITERATIONS
from config.prompts.investigation import FINAL_TURN_WITHOUT_TOOLS, STAGNATION_NUDGE


@dataclass(frozen=True, slots=True)
class StagnationVerdict:
    """What one iteration's productivity means for the next one."""

    count: int
    stagnant: bool
    strip_tools: bool
    nudge: str = ""


def observe(
    stagnant_iterations: int,
    *,
    produced_fresh_evidence: bool,
    threshold: int = MAX_STAGNANT_ITERATIONS,
) -> StagnationVerdict:
    """Return what to do after an iteration, given the count so far.

    Pure, and reading the running count rather than holding it: the count lives
    on the session so a resumed run does not forget that it was already three
    sterile iterations into the same dead end.
    """
    if not 1 <= threshold <= MAX_STAGNANT_ITERATIONS:
        raise ValueError(
            f"threshold must be between 1 and {MAX_STAGNANT_ITERATIONS}, got {threshold}"
        )

    if produced_fresh_evidence:
        return StagnationVerdict(count=0, stagnant=False, strip_tools=False)

    count = stagnant_iterations + 1
    strip_tools = count >= threshold
    return StagnationVerdict(
        count=count,
        stagnant=True,
        strip_tools=strip_tools,
        nudge=STAGNATION_NUDGE.format(remaining=max(threshold - count, 0)),
    )


def final_turn_instruction() -> str:
    """Return the instruction sent on the text-only turn after tools are withdrawn."""
    return FINAL_TURN_WITHOUT_TOOLS


__all__ = [
    "StagnationVerdict",
    "final_turn_instruction",
    "observe",
]
