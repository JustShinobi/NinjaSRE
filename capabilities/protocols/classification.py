"""What a bridged tool is allowed to do, decided here and nowhere else.

Article III says a capability with no declared side effect is a write. For a
capability written in this repository that is a build failure — the declaration
is required and the type refuses to be constructed without it. For one arriving
from a server nobody here controls the same rule has to survive a *hostile*
answer, not just a missing one, and that is a different problem: the server does
declare something, and what it declares cannot be trusted.

So the server's declaration is kept, shown to the operator, and never used. A
``Classification`` carries both halves — what the server said and what the
operator decided — and only the second one has any effect. A server declaring
its ``delete_everything`` tool read-only gets a suggestion in the console and
nothing else.

**Unclassified means write, and a write nobody authorised does not run.** The
fail-safe level is deliberately ``write_reversible`` rather than
``destructive``: the point is that the tool is gated, and picking the top of the
scale would tell an operator reading the console that we know something about
the tool that we do not. What stops it executing is ``refusal_for``, not the
level — the level is what makes the gate apply if anything ever routes around
that refusal.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from core.capability.metadata import SideEffectLevel

#: What a bridged tool is until an operator says otherwise. A write, because
#: absence is never permission, and the *reversible* write specifically because
#: claiming to know it is destructive would be inventing information.
UNCLASSIFIED_LEVEL: Final[SideEffectLevel] = SideEffectLevel.WRITE_REVERSIBLE

#: What the model is told when it calls a tool nobody has classified. It names
#: the remedy, because a refusal the operator cannot act on is a dead end.
UNCLASSIFIED_REFUSAL: Final = (
    "{name} comes from a bridged server and has no operator classification, so it is "
    "treated as a write and cannot run. An operator must classify its side effect "
    "before it becomes available."
)


class UnclassifiedTool(ValueError):
    """A classification was asked for in terms nobody defined."""


def _level_or_none(declared: str) -> SideEffectLevel | None:
    """Return the level ``declared`` names, or ``None`` when it names none."""
    try:
        return SideEffectLevel(declared.strip().lower())
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Classification:
    """One bridged tool's side-effect level: what was declared, and what was decided.

    Both fields, one authority. ``suggested_level`` exists so the console can
    show an operator what the server claims and pre-select it in the form;
    ``level`` is what the catalogue and the approval gate read, and it is unset
    until somebody with an account decides.
    """

    qualified_name: str
    level: SideEffectLevel | None = None
    suggested_level: SideEffectLevel = UNCLASSIFIED_LEVEL
    declared: str = ""

    @classmethod
    def suggested(cls, qualified_name: str, *, declared: str) -> Classification:
        """Return the unclassified record for a tool whose server declared ``declared``.

        A declaration nobody recognises suggests the fail-safe level rather than
        being discarded, so an operator opening the form sees the conservative
        answer pre-selected instead of a blank.
        """
        return cls(
            qualified_name=qualified_name,
            level=None,
            suggested_level=_level_or_none(declared) or UNCLASSIFIED_LEVEL,
            declared=declared,
        )

    @classmethod
    def decided(
        cls, qualified_name: str, *, level: SideEffectLevel, declared: str = ""
    ) -> Classification:
        """Return the record for a tool an operator has classified."""
        return cls(
            qualified_name=qualified_name,
            level=level,
            suggested_level=_level_or_none(declared) or level,
            declared=declared,
        )

    @property
    def classified(self) -> bool:
        """Return whether an operator has decided about this tool."""
        return self.level is not None

    @property
    def effective_level(self) -> SideEffectLevel:
        """Return the level the catalogue and the approval gate act on."""
        return self.level if self.level is not None else UNCLASSIFIED_LEVEL

    @property
    def contradicts_declaration(self) -> bool:
        """Return whether the operator disagreed with the server about this tool.

        Worth surfacing: a server that consistently under-declares is a server
        an operator may want to stop trusting for anything.
        """
        return self.classified and self.level is not self.suggested_level


@dataclass(frozen=True, slots=True)
class ClassificationTable:
    """Every classification one team has made, keyed by qualified name.

    Keyed by ``<server>.<tool>`` rather than by the catalogue name because the
    catalogue name is derived — it can change when the cleaning rules change,
    and an operator's decision must not evaporate when it does.
    """

    entries: Mapping[str, Classification] = field(default_factory=dict)

    @classmethod
    def of(cls, decisions: Mapping[str, str]) -> ClassificationTable:
        """Return the table ``decisions`` describes, or raise naming the bad value.

        Raises rather than defaulting an unreadable level to the fail-safe one.
        A typo in a stored classification is an operator's decision that never
        took effect, and quietly gating the tool would look exactly like the
        operator never having classified it.
        """
        built: dict[str, Classification] = {}
        for name, value in decisions.items():
            level = _level_or_none(value)
            if level is None:
                raise UnclassifiedTool(
                    f"{value!r} is not a side-effect level, so the classification of "
                    f"{name!r} says nothing; expected one of "
                    f"{', '.join(member.value for member in SideEffectLevel)}"
                )
            built[name] = Classification.decided(name, level=level)
        return cls(entries=built)

    def entry(self, qualified_name: str) -> Classification | None:
        """Return what is known about ``qualified_name``, or ``None``."""
        return self.entries.get(qualified_name)

    def is_classified(self, qualified_name: str) -> bool:
        """Return whether an operator has decided about ``qualified_name``."""
        found = self.entries.get(qualified_name)
        return found is not None and found.classified

    def level_for(self, qualified_name: str) -> SideEffectLevel:
        """Return the level this tool is gated at, fail-safe when unclassified."""
        found = self.entries.get(qualified_name)
        return found.effective_level if found is not None else UNCLASSIFIED_LEVEL

    def refusal_for(self, qualified_name: str) -> str | None:
        """Return why ``qualified_name`` may not execute, or ``None`` if it may."""
        if self.is_classified(qualified_name):
            return None
        return UNCLASSIFIED_REFUSAL.format(name=qualified_name)

    def awaiting(self, qualified_names: Iterable[str]) -> tuple[str, ...]:
        """Return the names in ``qualified_names`` still waiting on an operator.

        What the console lists. Order is the caller's, because that is discovery
        order and an operator working through a new server's tools should see
        them the way the server lists them.
        """
        return tuple(name for name in qualified_names if not self.is_classified(name))

    def restricted_to(self, qualified_names: Sequence[str]) -> ClassificationTable:
        """Return this table with every classification for a tool no longer offered dropped.

        Called on refresh. A tool a server removed must not leave a live
        classification behind: a server that removes ``rollout`` and later adds a
        different tool by the same name would otherwise inherit the old verdict.
        """
        kept = set(qualified_names)
        return ClassificationTable(
            entries={name: entry for name, entry in self.entries.items() if name in kept}
        )

    def with_suggestions(self, suggestions: Iterable[Classification]) -> ClassificationTable:
        """Return this table with ``suggestions`` filled in where nothing is decided.

        Decisions win. A suggestion never overwrites a classification, whatever
        the server has started declaring since the operator made it.
        """
        merged = dict(self.entries)
        for suggestion in suggestions:
            existing = merged.get(suggestion.qualified_name)
            if existing is not None and existing.classified:
                merged[suggestion.qualified_name] = Classification(
                    qualified_name=existing.qualified_name,
                    level=existing.level,
                    suggested_level=suggestion.suggested_level,
                    declared=suggestion.declared,
                )
            else:
                merged[suggestion.qualified_name] = suggestion
        return ClassificationTable(entries=merged)


__all__ = [
    "UNCLASSIFIED_LEVEL",
    "UNCLASSIFIED_REFUSAL",
    "Classification",
    "ClassificationTable",
    "UnclassifiedTool",
]
