"""Which cross-vendor capabilities need a source bound before they can answer.

A tool in ``capabilities/tools/system`` requires no integration, so nothing in
the availability narrowing keeps it out of a catalogue. Three of them
nevertheless cannot answer at all until a composition root has bound them
something to read: recall needs an episode corpus, topology needs a graph, and
the knowledge search needs a document store. Unbound, each returns an explicit
unavailability — which is the right answer to give and the wrong turn to spend.

Measured on staging: every investigation this deployment ran called them, and
every one of those calls failed. Ten turns across five runs, spent being told
that a source nobody composed is not composed.

The knowledge search is the one this list was missing, and it was the most
expensive one to miss. Its evidence source is ``knowledge_base``, which is one
of the sources the selection reserve is defined over — so it was not merely
surviving the ranking on merit, it was holding a slot the reserve guarantees it,
on every turn of every run, in order to report its own absence.

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

from capabilities.tools.system.knowledge_search import binding as knowledge_binding
from capabilities.tools.system.knowledge_search.tool import TOOL_NAME as KNOWLEDGE
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
    KNOWLEDGE: "a document store (knowledge base)",
}

#: How to ask, per capability. Held as callables rather than as values because
#: a binding set after import — which is every binding, since composition roots
#: run after the module graph is built — would otherwise be read as absent.
#:
#: Each entry is the capability's *own* ``current``, which is the property that
#: matters: this answers exactly what the tool body will find when it is called,
#: so the exclusion and the unavailability can never disagree. Recall and
#: topology read a ``ContextVar``, so their answer is the asking run's own —
#: the runner narrows a catalogue inside the same run that bound the source. The
#: knowledge store is still a module-level binding, so its answer is the
#: process's; that is a difference in how widely a binding is shared, and not
#: one this list is free to paper over, because the tool has the same one.
_BOUND: dict[str, Callable[[], object | None]] = {
    RECALL: memory_binding.current,
    TOPOLOGY: topology_binding.current,
    KNOWLEDGE: knowledge_binding.current,
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
