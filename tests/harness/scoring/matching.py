"""Comparing what the agent did against what an ideal investigation does.

Three modes, because three different questions are worth asking and one
comparison cannot answer them all. ``strict`` asks whether the agent took the
sequence; ``lcs`` asks how far it strayed from it; ``set`` asks only whether it
looked at the right things. An answer key picks the one its author is willing to
defend, and a key that picked ``strict`` for a scenario with three equally valid
orderings would be measuring the author's taste.

**Positions, not calls.** A trajectory is a sequence of *steps*, and a step is
whatever ran in one iteration — one call, or eight dispatched together. The
runtime may schedule a parallel batch in any order it likes, so comparing calls
would make the score depend on which coroutine happened to finish first. A
golden step is satisfied by an actual step that contains it (FR-009).

**Two counts, not one.** An action the golden path does not mention is *extra*;
an action taken twice is *redundant*. They are different defects — wandering and
looping — and the fix for one is not the fix for the other, so a scorer that
added them together would report a number nobody could act on (FR-010).

**Distance is reported in every mode**, including the ones that do not gate on
it. A ``set``-matched scenario whose distance has been climbing for three
releases is a scenario about to fail, and the mode it was scored under should
not be what hides that.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

#: The exact sequence, in order and adjacent.
STRICT: Final = "strict"

#: The order, without demanding adjacency: how many insertions and deletions
#: separate the two sequences.
LCS: Final = "lcs"

#: The actions, ignoring order entirely.
SET: Final = "set"

#: Every mode a caller may ask for.
MATCH_MODES: Final[tuple[str, ...]] = (STRICT, LCS, SET)

#: What the corpus's own answer keys spell ``strict``. The fixture vocabulary
#: shipped with the scenario harness says ``exact`` and the requirement says
#: ``strict``; they name one comparison, so one of them has to be an alias and
#: neither may quietly become a second behaviour.
MATCH_ALIASES: Final[Mapping[str, str]] = {"exact": STRICT}

#: What a key that named no mode is compared under. The forgiving-about-order
#: one, because a key that did not think about matching did not mean to demand
#: adjacency.
DEFAULT_MODE: Final = LCS


class UnknownMatchingMode(ValueError):
    """A trajectory was asked to be compared under a mode nobody defined.

    Raised rather than defaulted. A typo that silently scored under another mode
    would move every trajectory number in the corpus with nothing in the report
    saying why, which is the least attributable kind of change a suite can make.
    """


def normalise_mode(name: str) -> str:
    """Return the canonical mode ``name`` refers to.

    Raises:
        UnknownMatchingMode: ``name`` is neither a mode nor an alias of one.
    """
    wanted = name.strip().lower()
    if not wanted:
        return DEFAULT_MODE
    if wanted in MATCH_MODES:
        return wanted
    if wanted in MATCH_ALIASES:
        return MATCH_ALIASES[wanted]
    raise UnknownMatchingMode(
        f"unknown trajectory matching mode {name!r}; expected one of "
        f"{', '.join(MATCH_MODES)} (or {', '.join(sorted(MATCH_ALIASES))})"
    )


@dataclass(frozen=True, slots=True)
class Step:
    """One position in a trajectory: one action, or several run together.

    A frozenset rather than a tuple, because within a position order is not a
    fact about the investigation — it is a fact about the event loop.
    """

    actions: frozenset[str]

    @classmethod
    def of(cls, *actions: str) -> Step:
        """Return the step made of ``actions``."""
        return cls(actions=frozenset(action for action in actions if action))

    @property
    def is_batch(self) -> bool:
        """Return whether more than one call ran at this position."""
        return len(self.actions) > 1

    def satisfies(self, golden: Step) -> bool:
        """Return whether this step does everything ``golden`` asked for here."""
        return golden.actions <= self.actions

    def __str__(self) -> str:
        ordered = "|".join(sorted(self.actions))
        return f"[{ordered}]" if self.is_batch else ordered


def steps_of(actions: Sequence[str]) -> tuple[Step, ...]:
    """Return a flat action list lifted into one-action steps.

    What an answer key's ``ordered_actions`` means: a sequence of positions, one
    call each. A key that wanted a batch would have to say so, and none can yet.
    """
    return tuple(Step.of(action) for action in actions)


def steps_from_iterations(calls: Iterable[tuple[int, str]]) -> tuple[Step, ...]:
    """Return ``(iteration, capability)`` pairs grouped into steps by iteration.

    This is where FR-009 becomes a fact rather than an intention: whatever the
    loop dispatched in one iteration is one position, however many calls it was
    and whichever of them returned first.
    """
    grouped: dict[int, list[str]] = {}
    order: list[int] = []
    for iteration, capability in calls:
        if iteration not in grouped:
            grouped[iteration] = []
            order.append(iteration)
        grouped[iteration].append(capability)
    return tuple(Step.of(*grouped[iteration]) for iteration in order)


def flatten(steps: Sequence[Step]) -> tuple[str, ...]:
    """Return every action in ``steps``, batches expanded, in position order."""
    return tuple(action for step in steps for action in sorted(step.actions))


@dataclass(frozen=True, slots=True)
class TrajectoryMatch:
    """How far one trajectory was from the golden one, and in what respects."""

    mode: str
    distance: int
    within_distance: bool
    max_edit_distance: int = 0
    matched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    extra_actions: tuple[str, ...] = ()
    redundant_calls: tuple[str, ...] = ()
    golden: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()

    @property
    def deviated(self) -> bool:
        """Return whether the agent took a route other than the golden one.

        A deviation is not a failure and this property is not a verdict (FR-011).
        An investigation that skipped a step and still reached the right cause
        deviated; whether that is acceptable is what ``max_edit_distance`` says,
        and whether it was *right* is the accuracy axis's question.
        """
        return self.distance > 0

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this comparison."""
        return {
            "mode": self.mode,
            "distance": self.distance,
            "max_edit_distance": self.max_edit_distance,
            "within_distance": self.within_distance,
            "deviated": self.deviated,
            "matched": list(self.matched),
            "missing": list(self.missing),
            "extra_actions": list(self.extra_actions),
            "redundant_calls": list(self.redundant_calls),
            "golden": list(self.golden),
            "observed": list(self.observed),
        }


def compare(
    golden: Sequence[Step],
    actual: Sequence[Step],
    *,
    mode: str = DEFAULT_MODE,
    max_edit_distance: int = 0,
) -> TrajectoryMatch:
    """Return how ``actual`` compares to ``golden`` under ``mode``.

    Raises:
        UnknownMatchingMode: ``mode`` is not one this comparator implements.
    """
    resolved = normalise_mode(mode)
    kept = _longest_common_steps(golden, actual)
    distance = (len(golden) - len(kept)) + (len(actual) - len(kept))

    golden_actions = flatten(golden)
    observed_actions = flatten(actual)
    wanted = set(golden_actions)
    taken = set(observed_actions)

    missing = tuple(action for action in golden_actions if action not in taken)
    extra = tuple(_unique(action for action in observed_actions if action not in wanted))
    redundant = _repeats(observed_actions)

    if resolved == STRICT:
        satisfied = _is_prefix(golden, actual)
    elif resolved == SET:
        satisfied = not missing
    else:
        satisfied = distance <= max_edit_distance

    return TrajectoryMatch(
        mode=resolved,
        distance=distance,
        within_distance=satisfied,
        max_edit_distance=max_edit_distance,
        matched=tuple(str(step) for step in kept),
        missing=missing,
        extra_actions=extra,
        redundant_calls=redundant,
        golden=golden_actions,
        observed=observed_actions,
    )


def _is_prefix(golden: Sequence[Step], actual: Sequence[Step]) -> bool:
    """Return whether ``actual`` opens with ``golden``, position for position.

    Trailing steps are allowed and are counted as extra actions instead. An
    investigation that took the golden path and then checked one more thing did
    take the golden path; refusing it here would make ``max_extra_actions``
    unreachable in the one mode where somebody most wants to set it.
    """
    if len(actual) < len(golden):
        return False
    return all(actual[index].satisfies(step) for index, step in enumerate(golden))


def _longest_common_steps(golden: Sequence[Step], actual: Sequence[Step]) -> tuple[Step, ...]:
    """Return the longest ordered run of golden steps ``actual`` satisfied."""
    rows, columns = len(golden), len(actual)
    table = [[0] * (columns + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(columns - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if actual[j].satisfies(golden[i])
                else max(table[i + 1][j], table[i][j + 1])
            )

    kept: list[Step] = []
    i = j = 0
    while i < rows and j < columns:
        if actual[j].satisfies(golden[i]):
            kept.append(golden[i])
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return tuple(kept)


def _unique(actions: Iterable[str]) -> list[str]:
    """Return ``actions`` deduplicated, first occurrence order kept."""
    seen: dict[str, None] = {}
    for action in actions:
        seen.setdefault(action, None)
    return list(seen)


def _repeats(actions: Sequence[str]) -> tuple[str, ...]:
    """Return one entry per call beyond the first of each action.

    The repeats rather than the count, because "``get_events`` twice and
    ``list_pods`` once" and "``get_events`` three times" are the same number and
    different investigations.
    """
    seen: dict[str, int] = {}
    repeated: list[str] = []
    for action in actions:
        seen[action] = seen.get(action, 0) + 1
        if seen[action] > 1:
            repeated.append(action)
    return tuple(repeated)


__all__ = [
    "DEFAULT_MODE",
    "LCS",
    "MATCH_ALIASES",
    "MATCH_MODES",
    "SET",
    "STRICT",
    "Step",
    "TrajectoryMatch",
    "UnknownMatchingMode",
    "compare",
    "flatten",
    "normalise_mode",
    "steps_from_iterations",
    "steps_of",
]
