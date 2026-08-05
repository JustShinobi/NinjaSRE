"""Holding time-bounded capability calls to the window intake derived.

A model asked to look at logs "around the incident" reliably asks for the last
twenty-four hours, because that is what the examples in its training data say
and because a wider range feels safer. It is not safer. A day of logs answers a
different question from the forty minutes the incident happened in, costs the
vendor's largest query, and returns a result the context budget then evicts.

So the window is enforced rather than suggested. Enforcement is at
``pre_tool_use`` — the one hook point that can change what happens — and it
*clamps* rather than denies: a call whose range overlaps the window runs
against the overlap, and the model is told the arguments were rewritten. A
denial here would teach the model to stop asking for time ranges, which is the
opposite of what the window is for.

Matching is on argument name. A per-capability declaration would be unenforced
for every capability whose author forgot to add one, and that is exactly the
set that needs it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.investigation import (
    CONTEXT_WINDOW_END,
    CONTEXT_WINDOW_START,
    TIME_WINDOW_END_ARGUMENTS,
    TIME_WINDOW_START_ARGUMENTS,
)
from core.agent.hooks.types import ALLOW, HookResult, Rewrite, ToolContext
from core.domain.alerts.window import IncidentWindow, as_utc
from core.llm.types import ToolCall

#: Told to the model when a range was narrowed. It names the window so the next
#: call is inside it rather than being clamped again.
CLAMPED_TO_WINDOW = (
    "The time range was narrowed to the incident window ({start} .. {end}). Queries outside "
    "it answer a different question from the one this investigation is asking."
)


@dataclass(frozen=True, slots=True)
class IncidentWindowGuard:
    """Clamps time-bounded arguments to the incident window.

    A hook rather than a wrapper on each capability: the capabilities are
    written by eighty-five different integrations and the bound belongs to the
    investigation, not to any one of them.

    The window is read from the session being guarded rather than captured when
    the guard is built. That is what makes one instance safe on a runtime
    serving many concurrent investigations — a captured window would be the
    previous incident's, applied to this one. ``window`` overrides it, for a
    caller running a single investigation that has the value to hand.
    """

    window: IncidentWindow | None = None

    async def __call__(self, call: ToolCall, context: ToolContext) -> HookResult | None:
        """Return the call with its range clamped, or allow it unchanged."""
        window = self.window if self.window is not None else window_of(context.session.context)
        if window is None:
            return ALLOW

        clamped = clamp_arguments(call.arguments, window)
        if clamped is None:
            return ALLOW
        return Rewrite(
            arguments=clamped,
            reason=CLAMPED_TO_WINDOW.format(
                start=window.start.isoformat(), end=window.end.isoformat()
            ),
        )


def window_of(context: Mapping[str, str]) -> IncidentWindow | None:
    """Return the window a run's context names, or ``None`` when it names none.

    A run started without one — a sub-agent, a one-off question from a surface —
    is not clamped at all, which is correct: there is no incident to bound it to.
    """
    start, end = context.get(CONTEXT_WINDOW_START, ""), context.get(CONTEXT_WINDOW_END, "")
    if not start or not end:
        return None
    try:
        return IncidentWindow(
            start=as_utc(datetime.fromisoformat(start)),
            end=as_utc(datetime.fromisoformat(end)),
        )
    except ValueError:
        return None


def clamp_arguments(arguments: Mapping[str, Any], window: IncidentWindow) -> dict[str, Any] | None:
    """Return ``arguments`` with any out-of-window range moved inside it.

    ``None`` means nothing needed changing, which is the common case and the
    one worth not allocating for. An argument that does not parse as a time is
    left alone: the capability knows what it meant, and rewriting a value this
    module does not understand is how a guard breaks a working call.
    """
    changed: dict[str, Any] = {}

    for name, value in arguments.items():
        if name.lower() not in _TIME_ARGUMENTS:
            continue
        moment = _moment(value)
        if moment is None:
            continue
        inside = window.clamp(moment)
        if inside != moment:
            changed[name] = _rendered_like(value, inside)

    if not changed:
        return None
    return {**dict(arguments), **changed}


_TIME_ARGUMENTS = frozenset(
    name.lower() for name in (*TIME_WINDOW_START_ARGUMENTS, *TIME_WINDOW_END_ARGUMENTS)
)


def _moment(value: object) -> datetime | None:
    """Return the instant ``value`` names, or ``None`` if it names none."""
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value > 0:
        return datetime.fromtimestamp(_seconds(value), tz=UTC)
    if isinstance(value, str) and value.strip():
        try:
            return as_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _seconds(value: int | float) -> float:
    """Return ``value`` as epoch seconds, whichever unit it was written in.

    The boundary is far enough in the future that no plausible incident
    timestamp in seconds reaches it, and every millisecond timestamp is past it.
    """
    return float(value) / 1000.0 if value > _MILLISECOND_BOUNDARY else float(value)


#: Above this, an epoch number is milliseconds. 1e11 seconds is the year 5138.
_MILLISECOND_BOUNDARY = 1e11


def _rendered_like(original: object, moment: datetime) -> Any:
    """Return ``moment`` in the shape ``original`` was written in, unit included.

    A capability that was given epoch milliseconds parses epoch milliseconds.
    Handing it seconds because that is what this module prefers would move the
    query to 1970, and handing it an ISO string would make it fail to parse.
    """
    if isinstance(original, datetime):
        return moment
    if isinstance(original, int | float) and not isinstance(original, bool):
        stamp = moment.timestamp()
        scaled = stamp * 1000.0 if original > _MILLISECOND_BOUNDARY else stamp
        return int(scaled) if isinstance(original, int) else scaled
    return moment.isoformat()


__all__ = [
    "CLAMPED_TO_WINDOW",
    "IncidentWindowGuard",
    "clamp_arguments",
    "window_of",
]
