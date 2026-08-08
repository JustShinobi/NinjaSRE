"""What this package raises, and the one moment it is allowed to.

There is exactly one exception here and it is raised at *save* time. A malformed
policy must fail when an operator writes it, with a name and a path, never when
a decision is being made — a policy engine that raised mid-incident would refuse
an action for a reason that has nothing to do with the action.

Everything else this package decides is returned as a value. A refusal is not an
exceptional condition: most actions are refused, that is the default posture,
and an exception path for the common case is how a caller ends up with a bare
``except`` around the safety control.
"""

from __future__ import annotations


class MalformedPolicy(ValueError):
    """A policy document says something the engine cannot act on.

    Carries the path it was found at, because "one of your rules is wrong" sends
    an operator to read a document they have already read.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


__all__ = [
    "MalformedPolicy",
]
