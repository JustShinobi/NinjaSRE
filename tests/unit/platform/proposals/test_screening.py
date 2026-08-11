"""What a proposal has to carry, and what it may never name.

Two halves of one gate, both enforced where the proposal is *made* rather than
where it is reviewed. That placement is the whole point of acceptance 6: a
refusal at review time means the change sat in a queue, on a screen, in front of
somebody, until they read it carefully enough to notice — and "the operator was
careful" is not a control.

The first half is completeness. A proposal without a rationale, without
evidence, or without the investigation that produced it is a proposal a reviewer
approves because there is nothing to disagree with.

The second half is the seal. Credentials and the sections that decide what the
agent is allowed to do are not proposable, at any confidence, by any origin.
"""

from __future__ import annotations

import pytest

from platform.guardrails.engine import GuardrailEngine
from platform.proposals.errors import ProposalRefused
from platform.proposals.models import AgentProposal, ProposalType
from platform.proposals.screening import screen

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "team-payments"


def proposal(**overrides: object) -> AgentProposal:
    """Return a complete, acceptable configuration proposal."""
    fields: dict[str, object] = {
        "proposal_id": "prop-1",
        "proposal_type": ProposalType.CONFIGURATION,
        "org_id": ORG,
        "team_node_id": TEAM,
        "node_id": TEAM,
        "summary": "Raise the investigation turn ceiling to 24",
        "payload": {"agents": {"max_turns": 24}},
        "rationale": "Four of the last six investigations hit the ceiling mid-diagnosis.",
        "evidence": ("run-91/turn-20", "run-88/turn-20"),
        "run_id": "run-91",
        "correlation_id": "agents.max_turns",
    }
    fields.update(overrides)
    return AgentProposal(**fields)  # type: ignore[arg-type]


class TestAProposalNobodyCouldReview:
    """The three fields whose absence makes review theatre."""

    def test_no_rationale_is_refused(self) -> None:
        with pytest.raises(ProposalRefused) as refusal:
            screen(proposal(rationale="   "))
        assert "rationale" in str(refusal.value)

    def test_no_evidence_is_refused(self) -> None:
        with pytest.raises(ProposalRefused) as refusal:
            screen(proposal(evidence=()))
        assert "evidence" in str(refusal.value)

    def test_no_originating_run_is_refused(self) -> None:
        with pytest.raises(ProposalRefused) as refusal:
            screen(proposal(run_id=""))
        assert "investigation" in str(refusal.value)

    def test_a_complete_proposal_passes(self) -> None:
        screen(proposal())


class TestTheSeal:
    """What no proposal may name, whatever it says about why."""

    @pytest.mark.parametrize(
        "payload",
        [
            {"policies": {"guardrails": {"mode": "observe"}}},
            {"policies": {"masking": {"enabled": False}}},
            {"policies": {"approvals": {"required_levels": []}}},
            {"policies": {"autonomy": {"statements": []}}},
        ],
        ids=["guardrails", "masking", "approvals", "autonomy"],
    )
    def test_a_change_to_the_containment_is_refused(self, payload: dict[str, object]) -> None:
        with pytest.raises(ProposalRefused) as refusal:
            screen(proposal(payload=payload))
        assert "policies." in str(refusal.value)

    def test_a_field_an_integration_calls_secret_is_refused_by_name(self) -> None:
        """Refused on the field name, whatever the value looks like."""
        with pytest.raises(ProposalRefused) as refusal:
            screen(
                proposal(
                    payload={"integrations": {"datadog": {"settings": {"api_key": "tbd"}}}},
                )
            )
        assert "api_key" in str(refusal.value)

    def test_a_credential_shaped_value_is_refused_without_being_quoted(self) -> None:
        """The refusal names the path. It never reproduces what it found."""
        secret = "AKIAIOSFODNN7EXAMPLE"
        with pytest.raises(ProposalRefused) as refusal:
            screen(
                proposal(payload={"integrations": {"aws": {"settings": {"note": secret}}}}),
                guardrails=GuardrailEngine(),
            )
        assert "integrations.aws.settings.note" in str(refusal.value)
        assert secret not in str(refusal.value)

    def test_a_credential_reference_is_not_a_credential(self) -> None:
        """``credential`` holds a pointer to the vault. That is the field's job."""
        screen(
            proposal(payload={"integrations": {"datadog": {"credential": "datadog-prod"}}}),
            guardrails=GuardrailEngine(),
        )

    def test_the_seal_reaches_inside_a_list(self) -> None:
        """A sealed field in the third entry is a sealed field."""
        with pytest.raises(ProposalRefused):
            screen(
                proposal(
                    proposal_type=ProposalType.DETECTOR,
                    payload={
                        "detectors": [
                            {"detector_id": "corpus-a"},
                            {"detector_id": "corpus-b"},
                            {"detector_id": "corpus-c", "password": "hunter2"},
                        ]
                    },
                )
            )
