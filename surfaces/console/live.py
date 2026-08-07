"""Keeping an open page current from the event stream, without a refresh.

The console does not poll. A decision made somewhere else — in chat, at the CLI,
by another person in another browser — reaches the run's event log, the log
reaches the SSE stream the open page is already reading, and the page applies
it. That is what SC-003 means by "without a manual refresh": there is no second
mechanism, because the mechanism the transcript already uses is enough.

What lives here is the mapping from an event to a change in what is on screen.
It is deliberately small and deliberately total: an event that says nothing
about an interaction leaves the interactions exactly as they were, and an event
that closes one closes it whoever closed it and wherever they were.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from surfaces.console.stream import StreamEvent

#: The run saying it has started or stopped waiting on a person. The only kind
#: that closes a card — an approval being *raised* also concerns an interaction
#: and must not be mistaken for one being decided.
CLOSING_KIND: Final = "attention_changed"

#: The run saying something new needs a decision.
OPENING_KIND: Final = "approval_requested"

#: Both, for a caller filtering a stream down to what could change this page.
INTERACTION_KINDS: Final[frozenset[str]] = frozenset({CLOSING_KIND, OPENING_KIND})

#: The payload keys an event uses to name what it is about. Several, because the
#: vocabulary is the platform's and an approval and a question identify
#: themselves differently.
_IDENTIFIER_KEYS: Final[tuple[str, ...]] = ("interaction_id", "approval_id")


def closed_by(event: StreamEvent) -> str:
    """Return the interaction this event closed, or the empty string.

    An event only closes something if it says so. ``attention_changed`` with
    ``waiting`` true is the run *starting* to wait, which closes nothing — and
    treating any attention change as a closure would make a card vanish at the
    moment it became relevant.
    """
    if event.kind != CLOSING_KIND:
        return ""
    payload = event.payload
    if payload.get("waiting") is not False:
        return ""
    for key in _IDENTIFIER_KEYS:
        found = payload.get(key)
        if isinstance(found, str) and found:
            return found
    return ""


def opened_by(event: StreamEvent) -> Mapping[str, Any] | None:
    """Return the interaction this event opened, or ``None``.

    The other half of "without a refresh": an approval raised while somebody is
    watching the run should appear on their screen, not wait for them to
    navigate away and back.
    """
    if event.kind != OPENING_KIND:
        return None
    payload = event.payload
    identifier = next(
        (
            str(payload[key])
            for key in _IDENTIFIER_KEYS
            if isinstance(payload.get(key), str) and payload.get(key)
        ),
        "",
    )
    if not identifier:
        return None
    return {
        "interaction_id": identifier,
        "approval_id": identifier,
        "run_id": event.run_id,
        "kind": "approval",
        "text": str(payload.get("summary") or payload.get("text") or ""),
        "is_open": True,
    }


def apply_event(
    interactions: Sequence[Mapping[str, Any]], event: StreamEvent
) -> tuple[Mapping[str, Any], ...]:
    """Return ``interactions`` as ``event`` leaves them.

    Closing marks the item rather than removing it. A card that disappeared
    would leave the person who was about to answer it wondering whether they
    clicked something; a card that says "this was decided elsewhere" tells them
    what happened.
    """
    closed = closed_by(event)
    if closed:
        return tuple(
            {**interaction, "is_open": False} if _identifies(interaction, closed) else interaction
            for interaction in interactions
        )

    opened = opened_by(event)
    if opened is None:
        return tuple(interactions)
    if any(_identifies(interaction, str(opened["interaction_id"])) for interaction in interactions):
        return tuple(interactions)
    return (*interactions, opened)


def apply_events(
    interactions: Sequence[Mapping[str, Any]], events: Sequence[StreamEvent]
) -> tuple[Mapping[str, Any], ...]:
    """Return ``interactions`` as the whole batch of ``events`` leaves them."""
    current = tuple(interactions)
    for event in events:
        current = apply_event(current, event)
    return current


def open_count(interactions: Sequence[Mapping[str, Any]]) -> int:
    """Return how many of these are still waiting on a person."""
    return sum(1 for interaction in interactions if interaction.get("is_open", True))


def _identifies(interaction: Mapping[str, Any], identifier: str) -> bool:
    """Return whether ``interaction`` is the one ``identifier`` names."""
    return any(str(interaction.get(key, "")) == identifier for key in _IDENTIFIER_KEYS)


__all__ = [
    "CLOSING_KIND",
    "INTERACTION_KINDS",
    "OPENING_KIND",
    "apply_event",
    "apply_events",
    "closed_by",
    "open_count",
    "opened_by",
]
