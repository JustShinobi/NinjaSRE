"""Which cross-vendor capabilities need a source bound before they can answer.

A tool in ``capabilities/tools/system`` requires no integration, so nothing in
the availability narrowing keeps it out of a catalogue. Two of them nevertheless
cannot answer at all until a composition root has bound them something to read:
recall needs an episode corpus, topology needs a graph. Unbound, each returns an
explicit unavailability — which is the right answer to give and the wrong turn
to spend.

Measured on staging: every investigation this deployment ran called both, and
every one of those calls failed. Ten turns across five runs, spent being told
twice per run that a source nobody composed is not composed.

The unavailability is not the defect and this does not remove it. A tool called
without a source must still say so, because the alternative — an empty answer —
teaches an investigation that a team has no history when the truth is that
nobody configured memory. What this removes is the *offering*: a capability the
deployment cannot serve is left out of the catalogue with its reason recorded,
the same way a write nobody can carry out is left out.

Kept beside the tools rather than in the runtime because the fact belongs to
them. A third tool that grows a binding adds a line here and needs no change
anywhere else.
"""

from __future__ import annotations

from collections.abc import Callable

from capabilities.tools.system.memory_search import binding as memory_binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL
from capabilities.tools.system.topology_query import binding as topology_binding
from capabilities.tools.system.topology_query.tool import TOOL_NAME as TOPOLOGY

#: What each capability is waiting on, in the words an operator configures it
#: by. Read by the exclusion so the console can say what to do about it, rather
#: than only that something is missing.
SOURCE_REQUIREMENTS: dict[str, str] = {
    RECALL: "an episode corpus (memory)",
    TOPOLOGY: "a topology graph (knowledge)",
}

#: How to ask, per capability. Held as callables rather than as values because
#: a binding set after import — which is every binding, since composition roots
#: run after the module graph is built — would otherwise be read as absent. Each
#: one reads a ``ContextVar``, so what this answers is what the asking task can
#: see: the runner narrows a catalogue inside the same run that bound the source,
#: and gets that run's answer rather than the process's last one.
_BOUND: dict[str, Callable[[], object | None]] = {
    RECALL: memory_binding.current,
    TOPOLOGY: topology_binding.current,
}


def needs_a_source(name: str) -> bool:
    """Return whether ``name`` is one of the capabilities that must be bound."""
    return name in _BOUND


def has_a_source(name: str) -> bool:
    """Return whether ``name``'s source is bound for the caller's own run.

    ``True`` for every capability that needs none, so a caller can ask this of
    anything in the catalogue without first asking whether the question applies.

    Scoped to the asking context rather than to the process, which is what makes
    the exclusion correct while investigations run side by side: a source one run
    composed makes the capability offered on that run and not on the one beside
    it.
    """
    ask = _BOUND.get(name)
    return True if ask is None else ask() is not None


def unmet_source(name: str) -> str:
    """Return what ``name`` is waiting on, or the empty string when nothing."""
    return "" if has_a_source(name) else SOURCE_REQUIREMENTS.get(name, "")


__all__ = ["SOURCE_REQUIREMENTS", "has_a_source", "needs_a_source", "unmet_source"]
