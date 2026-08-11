"""Three origins, one queue, and the same guarantee from each.

Each origin gets the same four assertions, because the point of one queue is
that they are the same four: nothing is written at propose time, an undo is
stored before anybody can decide, an approval writes through the owning
package's own path with the agent *and* the approver in the audit, and the
stored plan puts it back.

The knowledge origin is not here. It has had this shape since feature 012 and
its own suite asserts it; what is new is the other three sharing it.
"""

from __future__ import annotations

import pytest

from config.constants.proposals import PROPOSAL_DECISION_TTL_HOURS
from platform.approvals.appliers import (
    CONFIG_ROLLBACK_CAPABILITY,
    proposal_appliers_for,
)
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports import ActorKind, PersistenceGateway, TenantScope
from platform.proposals.models import AgentProposal, ProposalState, ProposalType
from platform.proposals.service import (
    ProposalNotApproved,
    ProposalQueue,
    ProposalUnknown,
)
from tests.unit.platform.proposals.conftest import TEAM, Clock, at, settings_of

pytestmark = pytest.mark.unit

REVIEWER = "erik@example.com"


def queue(
    gateway: PersistenceGateway,
    scope: TenantScope,
    config: ConfigService,
    engine: GuardrailEngine,
    clock: Clock,
) -> ProposalQueue:
    """Return the review queue over the shipped appliers."""
    return ProposalQueue(
        gateway=gateway,
        scope=scope,
        appliers=proposal_appliers_for(config=config),
        guardrails=engine,
        clock=clock,
    )


def context_proposal() -> AgentProposal:
    """Return a proposed fact about how this estate actually behaves (059)."""
    return AgentProposal(
        proposal_id="prop-ctx",
        proposal_type=ProposalType.OPERATING_CONTEXT,
        org_id="acme",
        team_node_id=TEAM,
        node_id=TEAM,
        summary="Record that LXC container metrics come from the host",
        payload={
            "agents": {
                "operating_context": {
                    "sections": {
                        "Metrics": "Container memory for LXC guests is read from the host.",
                    }
                }
            }
        },
        rationale="Every LXC investigation so far had to rediscover this.",
        evidence=("run-71/turn-4", "run-77/turn-2", "run-83/turn-6"),
        run_id="run-83",
        correlation_id="agents.operating_context.Metrics",
    )


def detector_proposal() -> AgentProposal:
    """Return a proposed detector, in the disabled-with-origin shape 056 produces."""
    return AgentProposal(
        proposal_id="prop-det",
        proposal_type=ProposalType.DETECTOR,
        org_id="acme",
        team_node_id=TEAM,
        node_id=TEAM,
        summary="Watch the quorum margin the runbook says to check",
        payload={
            "detector_id": "corpus-quorum-margin",
            "name": "Quorum margin",
            "description": "The cluster loses quorum when the margin reaches zero.",
            "signal": "proxmox.quorum.margin",
            "kind": "threshold",
            "comparison": "below",
            "fire_value": 1.0,
            "enabled": False,
            "origin": "docs/verification.md",
        },
        rationale="This symptom appeared three times and nothing was watching for it.",
        evidence=("run-12/turn-8", "run-30/turn-3", "run-83/turn-9"),
        run_id="run-83",
        correlation_id="detector:corpus-quorum-margin",
    )


def configuration_proposal() -> AgentProposal:
    """Return a proposed ordinary configuration change (058's write path)."""
    return AgentProposal(
        proposal_id="prop-cfg",
        proposal_type=ProposalType.CONFIGURATION,
        org_id="acme",
        team_node_id=TEAM,
        node_id=TEAM,
        summary="Raise the investigation turn ceiling to 16",
        payload={"agents": {"max_iterations": 16}},
        rationale="Four of the last six investigations hit the ceiling mid-diagnosis.",
        evidence=("run-91/turn-20", "run-88/turn-20"),
        run_id="run-91",
        correlation_id="agents.max_iterations",
    )


ORIGINS = pytest.mark.parametrize(
    "proposal",
    [context_proposal(), detector_proposal(), configuration_proposal()],
    ids=["operating-context", "detector", "configuration"],
)


class TestProposingChangesNothing:
    """Nothing an agent proposes takes effect by being proposed."""

    @ORIGINS
    async def test_the_node_is_untouched_and_the_proposal_waits(
        self,
        proposal: AgentProposal,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        queued = await queue(gateway, scope, config, engine, clock).propose(proposal)

        assert queued.state is ProposalState.PENDING
        assert await settings_of(gateway) == {}

    @ORIGINS
    async def test_the_undo_is_stored_before_anybody_can_decide(
        self,
        proposal: AgentProposal,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        """Article III's 'and', made structural: no plan, no approval."""
        await queue(gateway, scope, config, engine, clock).propose(proposal)

        async with gateway.begin(scope) as uow:
            plan = await uow.approvals.rollback_plan_for(proposal.proposal_id)
            request = await uow.approvals.get_request(proposal.proposal_id)

        assert plan is not None
        assert [step.capability for step in plan.steps] == [CONFIG_ROLLBACK_CAPABILITY]
        assert request is not None
        assert request.run_id == proposal.run_id
        assert request.expires_at == at(PROPOSAL_DECISION_TTL_HOURS)

    @ORIGINS
    async def test_applying_an_undecided_proposal_is_refused(
        self,
        proposal: AgentProposal,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        """The bypass, attempted at the method a bypass would call."""
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(proposal)

        with pytest.raises(ProposalNotApproved):
            await reviews.apply(proposal.proposal_id)

        assert await settings_of(gateway) == {}


class TestApprovingWritesThroughTheOwningPath:
    """An approved proposal is an ordinary write, attributed to both parties."""

    async def test_an_operating_context_section_reaches_the_node(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(context_proposal())

        outcome = await reviews.approve("prop-ctx", reviewer=REVIEWER)

        assert outcome.state is ProposalState.APPROVED
        stored = await settings_of(gateway)
        sections = stored["agents"]["operating_context"]["sections"]
        assert "Metrics" in sections

    async def test_a_detector_arrives_enabled_and_leaves_the_others_alone(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        """Enabling one candidate must not delete every other detector."""
        await config.set_settings(
            TEAM,
            {
                "policies": {
                    "observation": {
                        "detectors": [
                            {
                                "detector_id": "shipped-load",
                                "name": "Load average",
                                "description": "The host is saturated.",
                                "signal": "guardian.host.load",
                                "kind": "threshold",
                                "comparison": "above",
                                "fire_value": 8.0,
                                "enabled": True,
                            }
                        ]
                    }
                }
            },
            actor_id="operator",
        )
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(detector_proposal())

        await reviews.approve("prop-det", reviewer=REVIEWER)

        rows = (await settings_of(gateway))["policies"]["observation"]["detectors"]
        by_id = {row["detector_id"]: row for row in rows}
        assert by_id["corpus-quorum-margin"]["enabled"] is True
        assert by_id["shipped-load"]["enabled"] is True

    async def test_a_configuration_change_is_written_and_validated(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(configuration_proposal())

        await reviews.approve("prop-cfg", reviewer=REVIEWER)

        assert (await settings_of(gateway))["agents"]["max_iterations"] == 16

    @ORIGINS
    async def test_the_audit_names_the_agent_and_the_approver(
        self,
        proposal: AgentProposal,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        """Acceptance 5's second half: both parties are on the record."""
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(proposal)

        await reviews.approve(proposal.proposal_id, reviewer=REVIEWER)

        async with gateway.begin(TenantScope(org_id="acme")) as uow:
            events = await uow.audit.query(limit=50)
        actors = {(event.actor_kind, event.actor_id) for event in events}
        assert any(
            kind is ActorKind.AGENT and proposal.proposal_id in actor and REVIEWER in actor
            for kind, actor in actors
        )


class TestRollingBackAnAppliedProposal:
    """A change that cannot be undone is not an improvement, it is accumulated risk."""

    @ORIGINS
    async def test_the_stored_plan_restores_what_was_there(
        self,
        proposal: AgentProposal,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        """The plan is read at propose time, so it restores what the reviewer saw."""
        before = dict(await settings_of(gateway))
        reviews = queue(gateway, scope, config, engine, clock)
        await reviews.propose(proposal)
        await reviews.approve(proposal.proposal_id, reviewer=REVIEWER)
        assert await settings_of(gateway) != before

        async with gateway.begin(scope) as uow:
            plan = await uow.approvals.rollback_plan_for(proposal.proposal_id)
        assert plan is not None
        step = plan.steps[0]
        await config.set_settings(
            str(step.arguments["node_id"]),
            step.arguments["settings"],
            actor_id="reverser",
            replace=True,
        )

        assert await settings_of(gateway) == before


class TestTheQueueIsOneTeams:
    """A queue that showed another team's proposals is one the wrong person answers."""

    async def test_an_unknown_proposal_is_named_rather_than_guessed_at(
        self,
        gateway: PersistenceGateway,
        scope: TenantScope,
        config: ConfigService,
        engine: GuardrailEngine,
        clock: Clock,
    ) -> None:
        with pytest.raises(ProposalUnknown):
            await queue(gateway, scope, config, engine, clock).apply("prop-nothing")
