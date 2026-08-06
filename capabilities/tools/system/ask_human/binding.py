"""How the declared question capability reaches the run that is asking.

A capability is a plain function. Discovery finds it by walking a package, the
model calls it by name, and there is no constructor to hand a run's handoff desk
to — which is what makes the catalogue addable one package at a time and is not
worth giving up for this tool.

So the desk is *bound* rather than injected: the composition root sets it around
the run, the tool reads it, and an unbound tool says there is nobody to ask
instead of pretending. The cost of that global is single-run-per-process
fidelity, which is why ``bind`` returns what it replaced and ``restore`` puts it
back — a caller driving two runs scopes the binding around each rather than
leaving it set.

What is deliberately not here is a fallback. An unbound tool does not construct
a desk from ambient configuration: a tool that invented its own surface routing
would put an incident's question in a channel nobody chose.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from core.agent.handoff import HandoffAnswer


@runtime_checkable
class QuestionDesk(Protocol):
    """Whatever puts a question to a person and waits for one answer.

    ``HumanHandoff`` satisfies this structurally. The tool cannot tell a desk
    wired to Slack from one wired to a CLI prompt, and does not need to: routing
    is the desk's business and refusing to ask for a credential is the boundary's.
    """

    async def ask(
        self,
        text: str,
        *,
        why: str = "",
        options: Sequence[str] = (),
    ) -> HandoffAnswer:
        """Return the answer to ``text``, or the fact that nobody gave one."""


_BOUND: QuestionDesk | None = None


def bind(desk: QuestionDesk | None) -> QuestionDesk | None:
    """Bind ``desk`` as the process's handoff path and return what it replaced."""
    global _BOUND
    previous = _BOUND
    _BOUND = desk
    return previous


def restore(previous: QuestionDesk | None) -> None:
    """Put back a binding ``bind`` replaced."""
    global _BOUND
    _BOUND = previous


def clear() -> None:
    """Unbind the desk, so the tool reports that nobody is attached."""
    restore(None)


def current() -> QuestionDesk | None:
    """Return the bound desk, or ``None`` when no human is reachable."""
    return _BOUND


def bound_names() -> Sequence[str]:
    """Return a one-line description of what is bound, for a health report."""
    return () if _BOUND is None else (type(_BOUND).__name__,)


__all__ = [
    "QuestionDesk",
    "bind",
    "bound_names",
    "clear",
    "current",
    "restore",
]
