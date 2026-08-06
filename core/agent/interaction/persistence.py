"""Pending interactions, written down with the session that is waiting on them.

An investigation suspended on a question is a run whose whole state is "somebody
has to answer this". If that survives a restart and the question does not, the
run comes back with nothing to wait for and no way to say why it stopped —
which is indistinguishable, to the operator looking at it, from a run that
crashed.

So interactions travel inside the session record rather than in a store of their
own. One write, one read, one thing to keep consistent: a session that was
persisted has its pending questions, and there is no arrangement of two stores
where the answer to "is this still answerable" depends on which one you asked.

**Expiry is decided on read, against the clock now.** A question raised before
a weekend outage is not answerable when the deployment comes back, and a
resumption that offered it would be offering somebody a button that reasons
about a cluster which no longer exists. The resumed registry says ``EXPIRED``
rather than dropping it, because "you missed this" is a thing the person
resuming needs to be told.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from core.agent.interaction.models import Interaction
from core.agent.interaction.registry import InteractionRegistry
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The key a session record holds its interactions under. Named because the
#: session's ``to_record`` writes it and ``from_record`` reads it, and a second
#: spelling is a run that resumes with its question silently gone.
INTERACTIONS_KEY = "interactions"


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


def to_records(interactions: Sequence[Interaction]) -> list[dict[str, Any]]:
    """Return the JSON-serialisable form of ``interactions``."""
    return [interaction.to_record() for interaction in interactions]


def from_records(records: Sequence[Mapping[str, Any]]) -> tuple[Interaction, ...]:
    """Return the interactions ``records`` describe, skipping any that are not.

    A record that will not parse is dropped with a log line rather than taking
    the whole resumption down. A session that comes back without one of its
    three questions is recoverable; a session that will not load at all is an
    investigation somebody has to start again from the alert.
    """
    restored: list[Interaction] = []
    for record in records:
        try:
            restored.append(Interaction.from_record(record))
        except (KeyError, ValueError, TypeError) as broken:
            logger.warning(
                "agent.interaction_record_unreadable",
                interaction_id=str(record.get("interaction_id", "?")),
                error=str(broken),
            )
    return tuple(restored)


def restore_registry(
    interactions: Sequence[Interaction],
    *,
    run_id: str = "",
    now: Callable[[], datetime] = _utc_now,
) -> InteractionRegistry:
    """Return a registry holding ``interactions``, with lapsed ones marked expired.

    The expiry sweep runs as part of restoring rather than being left to the
    caller. A caller that forgot would hand a surface a question whose window
    closed during the outage, and the surface has no way of knowing.
    """
    registry = InteractionRegistry(run_id=run_id, clock=now)
    registry.restore(interactions)
    lapsed = registry.expire_due()
    if lapsed:
        logger.info(
            "agent.interactions_expired_on_resume",
            run_id=run_id,
            count=len(lapsed),
        )
    return registry


__all__ = [
    "INTERACTIONS_KEY",
    "from_records",
    "restore_registry",
    "to_records",
]
