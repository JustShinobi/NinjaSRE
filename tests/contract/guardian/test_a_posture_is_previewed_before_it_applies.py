"""SC-005: the recommended preset is inspectable and previewable before it applies.

Driven through feature 040's own `preview_change` over real recorded actions,
resolved by the real resolver. Nothing here reimplements a precedence rule,
which is the property that stops the preview and the decision drifting apart —
the failure that would make this worse than useless, because it would be
reassuring and wrong.

The scenario is the one the primary story describes. An operator has watched for
a week under propose-only; the deployment has recorded what it would have done;
they are now deciding whether to relax. What they are owed at that moment is a
list of the specific actions that would have run without them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.autonomy.configuration import policy_set_of
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.preview import PolicyChange, RecordedAction, preview_change
from platform.autonomy.risk import RiskClass
from platform.autonomy.subjects import ProposedAction, Subject
from platform.config_service.schema.policies import AutonomyPolicySettings, PoliciesConfig
from platform.guardian.posture import (
    PosturePreset,
    PostureProposal,
    is_propose_only,
    preset_document,
)

pytestmark = pytest.mark.contract

NOW = datetime(2026, 8, 7, 3, 14, tzinfo=UTC)


def _policies(document: dict[str, object]) -> PolicySet:
    """Return what ``document`` resolves to, through the ordinary resolver."""
    return policy_set_of(
        PoliciesConfig(autonomy=AutonomyPolicySettings.model_validate(document)),
        source="home",
    )


def _action(
    action_id: str,
    capability: str,
    *,
    risk: RiskClass = RiskClass.LOW,
    days_ago: float = 1.0,
) -> RecordedAction:
    """Return one action the deployment proposed during the watching week."""
    return RecordedAction(
        action=ProposedAction(
            action_id=action_id,
            capability=capability,
            subjects=(Subject(resource_id="res-ct100", kind="container"),),
            risk_class=risk,
            has_rollback_plan=True,
        ),
        at=NOW - timedelta(days=days_ago),
    )


def _a_week_of_proposals() -> tuple[RecordedAction, ...]:
    """Return the week the story describes: locks, retries, and one destruction."""
    return (
        _action("a1", "proxmox_unlock_guest", risk=RiskClass.TRIVIAL, days_ago=6),
        _action("a2", "proxmox_retry_backup", risk=RiskClass.MODERATE, days_ago=5),
        _action("a3", "proxmox_start_guest", days_ago=4),
        _action("a4", "proxmox_unlock_guest", risk=RiskClass.TRIVIAL, days_ago=2),
        _action("a5", "proxmox_reclaim_storage", risk=RiskClass.CRITICAL, days_ago=1),
        _action("a6", "proxmox_migrate_guest", risk=RiskClass.MODERATE, days_ago=1),
    )


def _change() -> PolicyChange:
    """Return what applying the recommended preset would have decided differently."""
    return preview_change(
        _policies(preset_document(PosturePreset.PROPOSE_ONLY)),
        _policies(preset_document(PosturePreset.RECOMMENDED)),
        _a_week_of_proposals(),
    )


def test_the_week_started_with_a_deployment_that_did_nothing() -> None:
    """SC-004, as the starting point of this scenario rather than as an assertion
    about a document: what a fresh deployment *resolves* to acts on nothing."""
    assert is_propose_only(_policies({}))


def test_the_preview_names_the_actions_that_would_now_run_without_asking() -> None:
    """FR-019 and SC-005. A configuration diff cannot answer this question, and the
    two documents look almost identical while the answer changes completely."""
    change = _change()

    newly = {entry.capability for entry in change.newly_autonomous}

    assert newly == {
        "proxmox_unlock_guest",
        "proxmox_retry_backup",
        "proxmox_start_guest",
    }


def test_the_preview_leaves_the_destructive_actions_exactly_where_they_were() -> None:
    """The half an operator does not have to read, and the half that decides
    whether they trust the other half."""
    change = _change()

    unchanged = {entry.capability for entry in change.previewed if not entry.changed}

    assert {"proxmox_reclaim_storage", "proxmox_migrate_guest"} <= unchanged


def test_every_previewed_action_carries_the_reason_for_both_verdicts() -> None:
    """Article I: a conclusion carries what supports it, including this one."""
    for entry in _change().previewed:
        assert entry.before_reason, entry.action_id
        assert entry.after_reason, entry.action_id


def test_each_action_is_replayed_at_its_own_instant() -> None:
    """A freeze window and an override both mean different things at different
    times, so replaying last Tuesday's action against today's clock would answer
    a question nobody asked."""
    change = _change()

    assert [entry.at for entry in change.previewed] == [
        recorded.at for recorded in _a_week_of_proposals()
    ]


def test_the_preview_summarises_itself_in_a_sentence_before_the_list() -> None:
    summary = _change().summarise()

    assert "would be decided differently" in summary
    assert "less human involvement" in summary


def test_the_proposal_puts_the_preset_its_document_and_its_preview_in_one_value() -> None:
    """Three calls is how one of the three gets skipped, and the one that gets
    skipped is the preview."""
    proposal = PostureProposal(
        preset=PosturePreset.RECOMMENDED,
        document=preset_document(PosturePreset.RECOMMENDED),
        preview=_change(),
    )

    record = proposal.to_record()

    assert record["preset"] == "recommended"
    assert record["document"]["rules"]
    # Four *actions*, not four capabilities: the guest lock was cleared twice
    # that week, and the preview counts what would have run rather than what
    # kinds of thing would have.
    assert record["preview"]["newly_autonomous"] == 4
    assert "Five things happen without asking" in record["summary"]


def test_applying_the_preset_leaves_everything_it_did_not_name_proposing() -> None:
    """The deployment-wide rule stays propose-only. A preset that raised the floor
    would make every future capability autonomous the day it was added."""
    policies = _policies(preset_document(PosturePreset.RECOMMENDED))

    deployment_wide = [rule for rule in policies.rules if not rule.scope.capability]

    assert deployment_wide
    assert all(rule.level is AutonomyLevel.PROPOSE_ONLY for rule in deployment_wide)
