"""What this package refuses, and why refusing is better than the alternative.

Two refusals, and both are about a caller having asked for something that would
produce a plausible wrong answer rather than an obvious failure.
"""

from __future__ import annotations


class ChangeWindowInvalid(ValueError):
    """The window asked for is not one a change source will answer.

    Raised rather than clamped. A query silently narrowed from a fortnight to a
    week returns a *shorter* history than the caller believes it has, and the
    negative claim built on it — "nothing changed in the last fortnight" — is
    then wrong in the one direction that matters.
    """


class ChangeStateInvalid(ValueError):
    """A repository's change state cannot be read as one, with every problem named.

    Reported together rather than one at a time, for the same reason the
    declared inventory does it: somebody fixing a state directory wants one pass
    through it, and a reader that reveals the second problem only once the first
    is fixed is one people stop running.
    """

    def __init__(self, problems: tuple[str, ...] | list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            f"the change state has {len(self.problems)} problem(s): " + "; ".join(self.problems)
        )


__all__ = ["ChangeStateInvalid", "ChangeWindowInvalid"]
