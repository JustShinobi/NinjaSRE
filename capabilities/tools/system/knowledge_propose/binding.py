"""How the proposal capability reaches a run-scoped review queue.

The same arrangement the other two system capabilities use, with one addition
that matters: the bound protocol exposes ``propose`` and nothing else. There is
no ``apply`` on it, no ``approve``, and nothing that writes a document — so even
a deployment that bound the wrong object could not give this capability a path
into the knowledge base.

That is belt and braces over the check ``ProposalQueue.apply`` already makes
against the approval store. The store is what makes the rule true; this is what
makes it obvious.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from platform.knowledge.proposals import KnowledgeProposal


@runtime_checkable
class ProposalSink(Protocol):
    """Whatever accepts a proposal for review.

    One method. ``ProposalQueue`` satisfies it structurally, and the narrowness
    is the point: this protocol is the whole surface the agent's capability can
    reach, and nothing on it takes effect.
    """

    async def propose(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        """Queue ``proposal`` for human review, writing nothing to the corpus."""


_BOUND: ProposalSink | None = None


def bind(sink: ProposalSink | None) -> ProposalSink | None:
    """Bind ``sink`` as the process's review queue and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = sink
    return previous


def restore(previous: ProposalSink | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind the queue, so the tool reports review as unconfigured again."""
    restore(None)


def current() -> ProposalSink | None:
    """Return the bound review queue, or ``None`` when none is configured."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "ProposalSink",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
