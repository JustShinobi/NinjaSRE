"""Asking every configured source what changed, and saying what came back.

The composition, and the one place the negative is manufactured. Everything
below it is a source or a rule; this is what turns "three sources answered" into
a sentence a report can carry.

**The negative is the reason this exists.** An empty list is indistinguishable
from a list nobody built, from a source nobody configured, and from a query that
failed quietly — and an investigation that treats all four the same eventually
reports "nothing changed" about a deployment with no change source at all. So an
answer carries what was consulted, over what window, how many changes were in
that window in total, and which sources could not answer. Three genuinely
different statements come out of that:

- nothing was consulted, so whether anything changed is **unknown**;
- something was consulted and the window held nothing, so **nothing changed**;
- the window held changes and none of them reached this resource, so **the
  changes were real and none is the cause here**.

The third is the sentence that makes somebody stop looking at deploys, and it is
the one nobody believes unless it shows its working.

**A source that fails does not stop the answer, and does not go quiet either.**
It is named in ``degraded`` and the answer stops claiming to be a negative,
because a window nobody could read is not a window nothing happened in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.changes import MAX_CHANGES_PER_WINDOW
from config.prompts.changes import (
    CHANGES_FOUND,
    NO_CHANGE_AT_ALL,
    NO_CHANGE_SOURCE,
    NO_CHANGE_TOUCHED,
)
from platform.changes.correlation import (
    ComponentMap,
    CorrelatedChange,
    ResourceView,
    correlate_all,
)
from platform.changes.models import Change, ChangeWindow
from platform.changes.port import ChangeSource
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class ComponentReporter(Protocol):
    """A change source that also knows what each component manages.

    Separate from ``ChangeSource`` because most sources are not one: a git host
    can list commits and has no idea what a deployment applied. Keeping it apart
    is what lets a deployment run both and still correlate through the one that
    knows.
    """

    def components(self) -> dict[str, tuple[str, ...]]:
        """Return each component's managed resources, by correlation key."""


@dataclass(frozen=True, slots=True)
class ChangeAnswer:
    """What every source said about one resource in one window.

    ``changes`` holds everything that landed in the window, graded; ``linked``
    is the subset that reached the resource. Both, because the report needs the
    first to say what it ruled out and the second to say what it found.
    """

    resource: ResourceView
    window: ChangeWindow
    sources: tuple[str, ...] = ()
    changes: tuple[CorrelatedChange, ...] = ()
    #: How many changes were in the window before the cap.
    total: int = 0
    truncated: bool = False
    #: One line per source that could not answer, naming it and why.
    degraded: tuple[str, ...] = ()

    @property
    def linked(self) -> tuple[CorrelatedChange, ...]:
        """Return the changes that actually reached this resource."""
        return tuple(entry for entry in self.changes if not entry.strength.is_temporal_only)

    @property
    def answered(self) -> bool:
        """Return whether a negative claim can honestly be made from this.

        False when nothing was consulted and false when something failed. Both
        are "we do not know", and reporting either as "nothing changed" is the
        one way this feature could make an investigation worse than it was.
        """
        return bool(self.sources) and not self.degraded

    @property
    def statement(self) -> str:
        """Return the sentence a report carries, positive or negative."""
        listed = ", ".join(self.sources) if self.sources else "nothing"
        if not self.sources:
            return NO_CHANGE_SOURCE
        if self.linked:
            return CHANGES_FOUND.format(
                count=len(self.changes),
                window=self.window.describe(),
                sources=listed,
                strong=len(self.linked),
            )
        if self.total == 0:
            return NO_CHANGE_AT_ALL.format(window=self.window.describe(), sources=listed)
        return NO_CHANGE_TOUCHED.format(
            resource=self.resource.display_name or self.resource.resource_id,
            window=self.window.describe(),
            sources=listed,
            total=self.total,
        )

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a trace, a route and a console read."""
        return {
            "resource_id": self.resource.resource_id,
            "resource": self.resource.display_name,
            "window": {
                "start": self.window.start.isoformat(),
                "end": self.window.end.isoformat(),
                "hours": self.window.hours,
            },
            "sources": list(self.sources),
            "answered": self.answered,
            "statement": self.statement,
            "total": self.total,
            "truncated": self.truncated,
            "degraded": list(self.degraded),
            "changes": [entry.to_record() for entry in self.changes],
        }


@dataclass(slots=True)
class ChangeInquiry:
    """Every configured change source, asked one question at a time.

    Holds the sources rather than constructing them: which sources a deployment
    has is a composition decision, and a class that built its own would be one
    that reads a repository nobody pointed it at.
    """

    sources: Sequence[Any] = field(default_factory=list)

    async def about(
        self,
        resource: ResourceView,
        *,
        window: ChangeWindow,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> ChangeAnswer:
        """Return what changed for ``resource`` in ``window``, graded and explained."""
        collected: list[Change] = []
        degraded: list[str] = []
        names: list[str] = []
        stopped_looking = False

        for source in self.sources:
            name = str(getattr(source, "name", "")) or type(source).__name__
            names.append(name)
            try:
                found = await source.changes_in(window, limit=limit)
                # A source that returned exactly what it was asked for stopped
                # looking rather than ran out. Reported, because "three changes"
                # and "at least three changes" are different claims.
                stopped_looking = stopped_looking or len(found) >= limit
                collected.extend(found)
            except Exception as failure:  # noqa: BLE001 — every source, one rule
                # Never raised into an investigation. A source that could not be
                # read is a degradation to report, not a reason to abandon the
                # question — and it is named, so the negative below is not
                # believed more than it deserves.
                degraded.append(f"{name}: {failure}")
                logger.warning("changes.source_failed", source=name, error=str(failure))

        components = self._components()
        graded = correlate_all(collected, resource=resource, components=components)

        answer = ChangeAnswer(
            resource=resource,
            window=window,
            sources=tuple(sorted(names)),
            changes=graded[:limit],
            total=len(graded),
            truncated=len(graded) > limit or stopped_looking,
            degraded=tuple(degraded),
        )
        logger.info(
            "changes.answered",
            resource_id=resource.resource_id,
            sources=list(answer.sources),
            total=answer.total,
            linked=len(answer.linked),
            degraded=len(answer.degraded),
        )
        return answer

    def _components(self) -> ComponentMap:
        """Return what every source that knows says its components manage."""
        managed: dict[str, tuple[str, ...]] = {}
        for source in self.sources:
            if isinstance(source, ComponentReporter):
                managed.update(source.components())
        return ComponentMap(managed=managed)


def sources_of(inquiry: ChangeInquiry) -> tuple[str, ...]:
    """Return the names of the sources ``inquiry`` would consult.

    For a health report and for the console's "what would be consulted" line,
    which has to be answerable without running a query.
    """
    return tuple(
        sorted(
            str(getattr(source, "name", "")) or type(source).__name__ for source in inquiry.sources
        )
    )


__all__ = ["ChangeAnswer", "ChangeInquiry", "ChangeSource", "ComponentReporter", "sources_of"]
