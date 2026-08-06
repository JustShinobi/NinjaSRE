"""Capability enablement, diffed as a set.

Enabling a capability is not editing a value, it is widening what an agent may
do during somebody else's incident. The reviewer's question is "which tools does
this add", and a set difference answers it in one line each where a path-wise
document diff would bury it under list indices.

Two sections, and the order is deliberate: what is being **enabled** comes
first, because that is the half that increases what the agent can do. What is
being disabled is a reduction, and a reviewer who reads only the first section
has still read the part that carries the risk.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from platform.approvals.diff.engine import DiffLine, DiffOperation, DiffSection

#: Where the enabled set lives in a capability change's payload. One spelling,
#: because a second one is a change that reads back as enabling nothing.
ENABLED_KEY: Final = "enabled"

ENABLING_TITLE: Final = "enabling"
DISABLING_TITLE: Final = "disabling"


class CapabilityRenderer:
    """Renders a capability change as the tools it adds and the tools it removes."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return the enabling section, then the disabling one."""
        before = _names(current)
        after = _names(proposed)

        enabling = tuple(
            DiffLine(path=name, operation=DiffOperation.ADDED, after="enabled")
            for name in sorted(after - before)
        )
        disabling = tuple(
            DiffLine(path=name, operation=DiffOperation.REMOVED, before="enabled")
            for name in sorted(before - after)
        )

        sections: list[DiffSection] = []
        if enabling:
            sections.append(DiffSection(title=ENABLING_TITLE, lines=enabling))
        if disabling:
            sections.append(DiffSection(title=DISABLING_TITLE, lines=disabling))
        return tuple(sections)


def _names(payload: Mapping[str, Any]) -> frozenset[str]:
    """Return the capability names a payload enables.

    Two shapes are accepted because two callers produce them: a console sends
    ``{"enabled": [...]}`` and a configuration path sends the list itself. A
    renderer that understood only one would show an empty diff for the other,
    which is the worst possible failure for a value a human is about to approve.
    """
    enabled = payload.get(ENABLED_KEY, payload)
    return frozenset(_strings(enabled))


def _strings(value: Any) -> Iterable[str]:
    """Yield every capability name in ``value``, whatever shape it arrived in."""
    if isinstance(value, Mapping):
        return tuple(str(name) for name, on in value.items() if on)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(name) for name in value)
    return ()


__all__ = ["CapabilityRenderer"]
