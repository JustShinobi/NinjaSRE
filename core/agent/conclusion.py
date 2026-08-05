"""When an answer is allowed to end the run.

The default is permissive: the model said it was done, so it is done. That is
the right behaviour for an open-ended question, and it is what every run gets
unless somebody asked for something stricter.

The stricter policy exists because of a specific failure. A planning stage
shortlists the capabilities an incident needs, the model answers from the first
two, and the run reads as a completed investigation that never looked at the
change history. Refusing the early stop turns that from a quiet quality problem
into one more iteration.

Pluggable rather than configurable: the two policies here are different code
paths, not the same code path with a flag, and a third one — "refuse until at
least one hypothesis was recorded", say — is a class rather than another branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.agent.session import Session


@dataclass(frozen=True, slots=True)
class Acceptance:
    """Whether an answer ends the run, and what to tell the model if not.

    ``reason`` is sent back to the model on a refusal, so it has to say what is
    missing rather than that something is. "Not yet" produces another answer
    with the same gap.
    """

    accepted: bool
    reason: str = ""


@runtime_checkable
class ConclusionPolicy(Protocol):
    """Decides whether a text answer is allowed to end the investigation."""

    def accepts(self, session: Session, answer: str) -> Acceptance:
        """Return whether ``answer`` concludes ``session``, and why not if it does not."""


@dataclass(frozen=True, slots=True)
class AcceptAnyAnswer:
    """The default: a text answer with no tool calls concludes the run."""

    def accepts(self, session: Session, answer: str) -> Acceptance:
        """Return acceptance, always."""
        return Acceptance(accepted=True)


@dataclass(frozen=True, slots=True)
class RequirePlannedCapabilities:
    """Refuses an early stop until every planned capability has been called.

    "Called" rather than "succeeded": a capability that was tried and timed out
    was looked at, and holding the run open until an unavailable vendor comes
    back would trade one failure mode for a worse one.
    """

    planned: tuple[str, ...] = ()

    def accepts(self, session: Session, answer: str) -> Acceptance:
        """Return acceptance once every planned capability has been attempted."""
        attempted = {
            execution.capability for turn in session.turns for execution in turn.executions
        }
        outstanding = tuple(name for name in self.planned if name not in attempted)
        if not outstanding:
            return Acceptance(accepted=True)
        return Acceptance(
            accepted=False,
            reason=(
                "Before concluding, use the capabilities this investigation was planned "
                f"around that you have not called yet: {', '.join(outstanding)}. If one of "
                "them cannot help here, call it and say so, or say why it does not apply."
            ),
        )


__all__ = [
    "Acceptance",
    "AcceptAnyAnswer",
    "ConclusionPolicy",
    "RequirePlannedCapabilities",
]
