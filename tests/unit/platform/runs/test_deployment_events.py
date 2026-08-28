"""What one deployment-channel frame may carry, and what it may never.

Every one of the ten kinds the channel serves, and the allowlist that refuses
a payload key outside what its scope declares — the check that keeps a title,
an objective, or a decision's document from ever crossing this channel.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.runs.deployment import DeploymentEvent, DeploymentEventKind, DeploymentScope

_NOW = datetime(2026, 8, 27, tzinfo=UTC)


@pytest.mark.parametrize(
    ("scope", "kind", "payload"),
    [
        (DeploymentScope.RUN, DeploymentEventKind.RUN_STARTED, {"run_id": "r1"}),
        (DeploymentScope.RUN, DeploymentEventKind.STAGE_COMPLETED, {"run_id": "r1"}),
        (DeploymentScope.RUN, DeploymentEventKind.ATTENTION_CHANGED, {"run_id": "r1"}),
        (DeploymentScope.RUN, DeploymentEventKind.RUN_FINISHED, {"run_id": "r1"}),
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_OPENED, {"incident_id": "i1"}),
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_CLOSED, {"incident_id": "i1"}),
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_PROPOSED, {"proposal_id": "p1"}),
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_EXPIRED, {"proposal_id": "p1"}),
        (
            DeploymentScope.DECISION,
            DeploymentEventKind.DECISION_DECIDED,
            {"proposal_id": "p1", "interaction_id": "int1"},
        ),
        (DeploymentScope.CONTROL, DeploymentEventKind.RESYNC, {}),
    ],
)
def test_every_declared_kind_constructs_with_its_scopes_known_ids(
    scope: DeploymentScope, kind: DeploymentEventKind, payload: dict[str, str]
) -> None:
    event = DeploymentEvent(scope=scope, kind=kind, sequence=1, occurred_at=_NOW, payload=payload)
    assert event.scope is scope
    assert event.kind is kind
    assert dict(event.payload) == payload


def test_a_kind_that_does_not_belong_to_its_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="does not belong to scope"):
        DeploymentEvent(
            scope=DeploymentScope.INCIDENT,
            kind=DeploymentEventKind.RUN_STARTED,
            sequence=1,
            occurred_at=_NOW,
            payload={},
        )


@pytest.mark.parametrize("sensitive_key", ["title", "objective", "document", "summary", "headline"])
def test_a_sensitive_field_never_crosses_the_channel(sensitive_key: str) -> None:
    with pytest.raises(ValueError, match="extra key"):
        DeploymentEvent(
            scope=DeploymentScope.RUN,
            kind=DeploymentEventKind.RUN_STARTED,
            sequence=1,
            occurred_at=_NOW,
            payload={"run_id": "r1", sensitive_key: "leaked"},
        )


def test_a_decision_document_body_is_refused_even_alone() -> None:
    with pytest.raises(ValueError, match="extra key"):
        DeploymentEvent(
            scope=DeploymentScope.DECISION,
            kind=DeploymentEventKind.DECISION_PROPOSED,
            sequence=1,
            occurred_at=_NOW,
            payload={"document": {"plan": "restart the pod"}},
        )


def test_resync_carries_no_payload_at_all() -> None:
    with pytest.raises(ValueError, match="extra key"):
        DeploymentEvent(
            scope=DeploymentScope.CONTROL,
            kind=DeploymentEventKind.RESYNC,
            sequence=1,
            occurred_at=_NOW,
            payload={"anything": "at all"},
        )
