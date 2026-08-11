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

from config.constants.proposals import SEALED_CONFIG_PREFIXES
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


def payload_setting(path: str, value: object) -> dict[str, object]:
    """Return the payload that sets the dotted ``path`` to ``value``."""
    segments = path.split(".")
    nested: dict[str, object] = {segments[-1]: value}
    for segment in reversed(segments[:-1]):
        nested = {segment: nested}
    return nested


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


def test_a_change_to_the_containment_is_refused() -> None:
    """Every sealed section, read from the constant rather than listed again here.

    Listing the four by hand is how a fifth is added to the seal and covered by
    nothing: the test would still pass, naming the sections that were sealed on
    the day it was written. Driving the cases from what the screen actually reads
    means a section joins the seal and its case exists in the same commit.
    """
    for sealed in SEALED_CONFIG_PREFIXES:
        with pytest.raises(ProposalRefused) as refusal:
            screen(proposal(payload=payload_setting(f"{sealed}.mode", "observe")))
        assert sealed in str(refusal.value)


def test_emptying_a_sealed_section_is_a_change_like_any_other() -> None:
    """The most destructive sealed edit is the one with nothing in it.

    ``policies.autonomy.statements = []`` revokes every autonomy statement a team
    has, and ``policies.guardrails = {}`` removes the section that constrains the
    agent at all. Neither has a scalar anywhere under it, so a screen that only
    looked at scalars would find nothing to refuse and let both through.
    """
    for sealed in SEALED_CONFIG_PREFIXES:
        for payload in (
            payload_setting(sealed, {}),
            payload_setting(sealed, []),
            payload_setting(f"{sealed}.statements", []),
        ):
            with pytest.raises(ProposalRefused) as refusal:
                screen(proposal(payload=payload))
            assert sealed in str(refusal.value)


class TestTheSeal:
    """What no proposal may name, whatever it says about why."""

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
