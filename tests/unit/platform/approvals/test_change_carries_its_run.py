"""Which run a queued change says it belongs to, and who needs the answer."""

from __future__ import annotations

from datetime import UTC, datetime

from platform.approvals.models import ChangeTarget, ChangeType, PendingChange

AT = datetime(2026, 8, 25, 23, 47, tzinfo=UTC)


def _queued(change_type: ChangeType, proposed: dict[str, object]) -> PendingChange:
    """Return a change as ``ApprovalService.queue`` builds one."""
    return PendingChange.queued(
        change_id="c1",
        change_type=change_type,
        target=ChangeTarget(identifier="pve01", path="proxmox_start_guest"),
        proposed=proposed,
        current={},
        requester="alert-router",
        rationale="because",
        at=AT,
    )


def test_a_remediation_is_stored_under_the_run_that_proposed_it() -> None:
    """The screen that offers the decision finds the approval by run, and only by run.

    ``incident-detail.tsx`` reads ``/v1/approvals?run_id=<the incident's run>``
    and renders the approve and reject controls only when that returns
    something. The store row was written with a run id synthesised from the
    change type and the target — ``remediation:pve01`` — while the run that
    actually proposed the action sat in the payload the row carries.

    So the query never matched, the screen found no proposal, and the controls
    were never drawn. Measured against staging on 2026-08-25: a live pending
    approval with fifteen minutes left, and zero buttons on both the incident
    page and the decisions list. The component exists and is wired; nothing
    could ever satisfy the condition that renders it.
    """
    change = _queued(
        ChangeType.REMEDIATION,
        {"run_id": "ac1f544d55f4422186c78d96e79111c7", "capability": "proxmox_start_guest"},
    )

    assert change.to_request().run_id == "ac1f544d55f4422186c78d96e79111c7"


def test_a_change_nobody_investigated_keeps_the_key_built_from_its_target() -> None:
    """A configuration edit is queued by a person, so there is no run to name.

    The synthesised key stays what it was for those: it is how a listing groups
    changes to one target when no run exists to group them by, and inventing a
    run id there would be worse than the string it replaced.
    """
    change = _queued(ChangeType.CONFIGURATION, {"retention_days": 30})

    assert change.to_request().run_id == "configuration:pve01"
