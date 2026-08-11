"""The negative half of acceptance 2, asserted by attempting it.

"No proposal applies without explicit human approval" is a negative, and a
negative nobody tries is a negative nobody has checked. So this suite tries: it
drives an undecided proposal through **every** entry point that could apply one
and requires a refusal from each, then checks the node afterwards to be sure the
refusal was a refusal rather than a message.

The entry points are enumerated from the applier map rather than listed by hand.
An origin added next quarter is covered by this file on the day it is wired, not
on the day somebody remembers to extend a list.
"""

from __future__ import annotations

from typing import cast

import pytest

from platform.approvals.appliers import proposal_appliers_for
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.proposals.models import AgentProposal, ProposalState, ProposalType
from platform.proposals.service import ProposalNotApproved, ProposalQueue
from tests.unit.platform.proposals.conftest import TEAM, Clock, settings_of

pytestmark = pytest.mark.unit

REVIEWER = "erik@example.com"


def payload_for(kind: ProposalType) -> dict[str, object]:
    """Return a valid payload for ``kind``, so only the decision is what is missing."""
    if kind is ProposalType.DETECTOR:
        return {
            "detector_id": "corpus-x",
            "name": "A check",
            "description": "Something the corpus described.",
            "signal": "datastore.used_percent",
            "kind": "threshold",
            "comparison": "above",
            "fire_value": 85.0,
            "enabled": False,
        }
    if kind is ProposalType.OPERATING_CONTEXT:
        return {"agents": {"operating_context": {"sections": {"Estate": "One cluster."}}}}
    return {"agents": {"max_iterations": 9}}


def proposal_for(kind: ProposalType) -> AgentProposal:
    """Return a complete, acceptable proposal of ``kind`` that nobody has answered."""
    return AgentProposal(
        proposal_id=f"prop-{kind.value}",
        proposal_type=kind,
        org_id="acme",
        team_node_id=TEAM,
        node_id=TEAM,
        summary=f"A {kind.value} change nobody has decided",
        payload=payload_for(kind),
        rationale="Established across three investigations of the same alert.",
        evidence=("run-1/turn-2", "run-2/turn-5"),
        run_id="run-2",
        correlation_id=f"{kind.value}:under-test",
    )


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


#: Every origin a deployment with a configuration service can apply, read off
#: the applier map rather than listed by hand. An origin wired next quarter is
#: parametrised into this file on the day it is wired rather than on the day
#: somebody remembers a list exists. ``cast`` because the map only ever asks
#: whether a service was supplied — nothing is called while it is being built.
EVERY_ORIGIN = tuple(sorted(proposal_appliers_for(config=cast(ConfigService, object())), key=str))


@pytest.mark.parametrize("kind", EVERY_ORIGIN, ids=lambda kind: kind.value)
async def test_an_undecided_proposal_refuses_at_the_applier_entry_point(
    kind: ProposalType,
    gateway: PersistenceGateway,
    scope: TenantScope,
    config: ConfigService,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """``apply`` is public precisely so this can be attempted."""
    reviews = queue(gateway, scope, config, engine, clock)
    await reviews.propose(proposal_for(kind))

    with pytest.raises(ProposalNotApproved):
        await reviews.apply(f"prop-{kind.value}")

    assert await settings_of(gateway) == {}


@pytest.mark.parametrize("kind", EVERY_ORIGIN, ids=lambda kind: kind.value)
async def test_a_rejected_proposal_still_refuses(
    kind: ProposalType,
    gateway: PersistenceGateway,
    scope: TenantScope,
    config: ConfigService,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """A decision was taken, and it was the other one."""
    reviews = queue(gateway, scope, config, engine, clock)
    await reviews.propose(proposal_for(kind))
    await reviews.reject(
        f"prop-{kind.value}", reviewer=REVIEWER, reason="Already covered by the shipped set."
    )

    with pytest.raises(ProposalNotApproved):
        await reviews.apply(f"prop-{kind.value}")

    assert await settings_of(gateway) == {}


@pytest.mark.parametrize("kind", EVERY_ORIGIN, ids=lambda kind: kind.value)
async def test_an_expired_proposal_cannot_be_applied_later(
    kind: ProposalType,
    gateway: PersistenceGateway,
    scope: TenantScope,
    config: ConfigService,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """Nobody answered in time, which is not the same as answering yes."""
    reviews = queue(gateway, scope, config, engine, clock)
    await reviews.propose(proposal_for(kind))
    clock.advance(hours=1_000)
    async with gateway.begin(scope) as uow:
        await uow.approvals.expire_due(clock())

    stored = await reviews.get(f"prop-{kind.value}")
    assert stored is not None
    assert stored.state is ProposalState.EXPIRED
    with pytest.raises(ProposalNotApproved):
        await reviews.apply(f"prop-{kind.value}")

    assert await settings_of(gateway) == {}
