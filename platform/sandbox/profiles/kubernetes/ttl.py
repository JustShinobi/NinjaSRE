"""Expiry, kept on the pod rather than in anybody's memory.

A sandbox's TTL lives in an annotation on its own pod. That is the whole design
decision in this module, and it is what makes the reaper correct across
replicas: any process that can read the cluster can tell whether an instance has
expired, including one that started after the process that created it died.

An investigation that is still working says so by refreshing. Refresh is
explicit rather than implied by activity, because "active" is the wrong test — a
capability tailing logs for an hour is active and still needs a bound, and an
investigation waiting on a human approval is idle and must not be collected.

The format is ISO 8601 in UTC with an offset. Annotations are strings, and a
naive timestamp read by a replica in another zone is a fifteen-hour TTL nobody
intended.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config.constants.security import (
    SANDBOX_EXPIRES_AT_ANNOTATION,
    SANDBOX_TTL_REFRESH_INTERVAL_SECONDS,
)


def expiry_of(ttl_seconds: int, *, now: datetime | None = None) -> datetime:
    """Return when a sandbox created at ``now`` with ``ttl_seconds`` expires."""
    at = now if now is not None else datetime.now(UTC)
    return at + timedelta(seconds=ttl_seconds)


def render(at: datetime) -> str:
    """Return ``at`` as the annotation value, in UTC with an explicit offset."""
    return at.astimezone(UTC).isoformat()


def parse(value: str) -> datetime | None:
    """Return the instant ``value`` names, or ``None`` if it is unreadable.

    ``None`` rather than a raise, and the caller treats it as expired. An
    annotation somebody edited by hand into nonsense describes a pod nobody is
    tracking, and the safe reading of "I cannot tell when this expires" is "now".
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def expires_at_of(metadata: dict[str, object]) -> datetime | None:
    """Return the expiry recorded on a pod's metadata, or ``None``."""
    annotations = metadata.get("annotations")
    if not isinstance(annotations, dict):
        return None
    value = annotations.get(SANDBOX_EXPIRES_AT_ANNOTATION)
    return parse(value) if isinstance(value, str) else None


def is_expired(metadata: dict[str, object], *, now: datetime | None = None) -> bool:
    """Return whether the pod ``metadata`` describes has outlived its TTL."""
    at = now if now is not None else datetime.now(UTC)
    expires = expires_at_of(metadata)
    return expires is None or at >= expires


def due_for_refresh(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Return whether an active investigation should push this expiry out now.

    True once less than the refresh interval remains, so a caller polling at the
    interval never lets one lapse — and so a caller that refreshes on every turn
    does not write an annotation per turn.
    """
    at = now if now is not None else datetime.now(UTC)
    return (expires_at - at).total_seconds() <= SANDBOX_TTL_REFRESH_INTERVAL_SECONDS


__all__ = [
    "due_for_refresh",
    "expires_at_of",
    "expiry_of",
    "is_expired",
    "parse",
    "render",
]
