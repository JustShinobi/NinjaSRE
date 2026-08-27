"""Whether a decision arriving after the window is refused."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.approvals.errors import ChangeExpired
from platform.approvals.models import ChangeState, ChangeTarget, ChangeType, PendingChange

QUEUED = datetime(2026, 8, 25, 23, 48, tzinfo=UTC)


def _pending() -> PendingChange:
    """Return a remediation queued with the fifteen-minute window it ships with."""
    return PendingChange.queued(
        change_id="7271ee3f",
        change_type=ChangeType.REMEDIATION,
        target=ChangeTarget(identifier="pve01", path="proxmox_start_guest"),
        proposed={"capability": "proxmox_start_guest"},
        current={"status": "stopped"},
        requester="alert-router",
        rationale="the guest stopped and nothing stopped it",
        at=QUEUED,
        expiry_hours=0.25,
    )


def test_a_change_past_its_window_is_expired_on_the_clock_not_on_its_label() -> None:
    """The label is a cache of the clock, and the sweep that writes it may not be running.

    Measured against staging on 2026-08-25: a remediation proposed at 23:48 with
    a fifteen-minute window was still ``pending`` at 00:53, because nothing
    sweeps lapsed changes in that deployment. It was approved and carried out
    fifty minutes after the reading behind it stopped being current.
    """
    change = _pending()

    assert change.state is ChangeState.PENDING
    assert change.has_expired(QUEUED + timedelta(minutes=16))
    assert not change.has_expired(QUEUED + timedelta(minutes=14))


def test_the_refusal_says_the_window_closed_rather_than_that_somebody_decided() -> None:
    """Two different facts, and only one of them means "look at what they chose"."""
    with pytest.raises(ChangeExpired) as refused:
        raise ChangeExpired("7271ee3f", "2026-08-26T00:03:08+00:00", "2026-08-26T00:53:37+00:00")

    assert "could be answered until" in str(refused.value)
    assert "nobody has looked at since" in str(refused.value)
