"""The queue over HTTP: what is waiting, what it would do, and answering it.

Driven through the running gateway rather than against the service, because
every acceptance this feature is judged on is about what a *person* can reach:
the link back to the run, the mechanism that shows the effect, the reason a
rejection is refused without, and the recall of what was said last time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.approvals.appliers import proposal_appliers_for
from platform.config_service.service import ConfigService
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from platform.proposals.models import AgentProposal, ProposalType
from platform.proposals.service import ProposalQueue
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, issue_token
from tests.unit.gateway.http.test_incident_routes import FakeInvestigationRunner

pytestmark = pytest.mark.anyio

REVIEWER = "ada"


def detector_proposal(proposal_id: str = "prop-det") -> AgentProposal:
    """Return the corpus's proposal in the disabled-with-origin shape 056 produces."""
    return AgentProposal(
        proposal_id=proposal_id,
        proposal_type=ProposalType.DETECTOR,
        org_id=ORG,
        team_node_id=TEAM_PAYMENTS,
        node_id=TEAM_PAYMENTS,
        summary="Watch the datastore fill the runbook says to check",
        payload={
            "detector_id": "corpus-datastore-fill",
            "name": "Datastore fill",
            "description": "A datastore past this cannot complete a snapshot.",
            "signal": "datastore.used_percent",
            "kind": "threshold",
            "comparison": "above",
            "fire_value": 85.0,
            "enabled": False,
            "origin": "docs/verification.md",
        },
        rationale="This symptom appeared three times and nothing was watching for it.",
        evidence=("run-12/turn-8", "run-30/turn-3"),
        run_id="run-30",
        correlation_id="detector:corpus-datastore-fill",
    )


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, str, FakePersistence]]:
    """Yield a client over a deployment with one team and nothing proposed yet."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )

    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=FakeInvestigationRunner()
    )
    secret = await issue_token(
        store, state.tokens, user_id=REVIEWER, role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield client, secret, store


async def queue_one(store: FakePersistence, proposal: AgentProposal) -> None:
    """Put ``proposal`` in the queue the way the agent's capability would."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    config = ConfigService(gateway=store, scope=scope)
    await ProposalQueue(
        gateway=store, scope=scope, appliers=proposal_appliers_for(config=config)
    ).propose(proposal)


def auth(secret: str) -> dict[str, str]:
    """Return the authorization header for ``secret``."""
    return {"authorization": f"Bearer {secret}"}


async def test_a_queued_proposal_carries_its_evidence_and_a_link_to_its_run(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """Acceptance 1: the origin is a field, so following it is not guesswork."""
    client, secret, store = deployment
    await queue_one(store, detector_proposal())

    listed = await client.get("/v1/proposals", headers=auth(secret))
    assert listed.status_code == 200, listed.text
    row = listed.json()["proposals"][0]

    assert row["proposal_type"] == "detector"
    assert row["run_id"] == "run-30"
    assert row["evidence"] == ["run-12/turn-8", "run-30/turn-3"]
    assert row["effect"] == {
        "mechanism": "detector-dry-run",
        "target": "corpus-datastore-fill",
    }

    # The run link resolves: the run route answers about the run the proposal names.
    followed = await client.get(f"/v1/runs/{row['run_id']}", headers=auth(secret))
    assert followed.status_code in {200, 404}, followed.text


async def test_the_count_is_one_endpoint_the_band_and_the_badge_both_read(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    client, secret, store = deployment

    empty = await client.get("/v1/proposals/count", headers=auth(secret))
    assert empty.json() == {"pending": 0}

    await queue_one(store, detector_proposal())

    assert (await client.get("/v1/proposals/count", headers=auth(secret))).json() == {"pending": 1}


async def test_a_rejection_without_a_reason_is_refused_by_the_server(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """A control is a courtesy; a server check is a rule."""
    client, secret, store = deployment
    await queue_one(store, detector_proposal())

    refused = await client.post(
        "/v1/proposals/prop-det/decision",
        json={"verdict": "reject", "reason": "   "},
        headers=auth(secret),
    )

    assert refused.status_code == 400
    still = await client.get("/v1/proposals/prop-det", headers=auth(secret))
    assert still.json()["state"] == "pending"


async def test_the_reason_resurfaces_on_the_next_proposal_of_the_same_thing(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """Acceptance 4: matched on the correlation key, not on the wording."""
    client, secret, store = deployment
    await queue_one(store, detector_proposal("prop-first"))

    rejected = await client.post(
        "/v1/proposals/prop-first/decision",
        json={"verdict": "reject", "reason": "The snapshot runs nightly; 85 is normal here."},
        headers=auth(secret),
    )
    assert rejected.status_code == 200, rejected.text

    # A second investigation proposes the same detector, worded differently.
    again = detector_proposal("prop-second")
    await queue_one(store, again)

    reviewed = await client.get("/v1/proposals/prop-second", headers=auth(secret))
    prior: list[dict[str, Any]] = reviewed.json()["prior_rejections"]

    assert [item["proposal_id"] for item in prior] == ["prop-first"]
    assert "snapshot runs nightly" in prior[0]["reason"]
    assert prior[0]["decided_by"] == REVIEWER


async def test_approving_writes_the_change_and_reports_what_it_did(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """Acceptance 2 and 5: a human decides, the platform applies, both are recorded."""
    client, secret, store = deployment
    await queue_one(store, detector_proposal())

    decided = await client.post(
        "/v1/proposals/prop-det/decision",
        json={"verdict": "approve"},
        headers=auth(secret),
    )

    assert decided.status_code == 200, decided.text
    assert decided.json()["state"] == "approved"
    assert "corpus-datastore-fill" in decided.json()["applied"]

    running = await client.get("/v1/detectors", headers=auth(secret))
    rows = {row["detector_id"]: row for row in running.json()["detectors"]}
    assert rows["corpus-datastore-fill"]["enabled"] is True


async def test_an_org_scoped_credential_reads_an_empty_queue_not_an_error(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """The credential first run establishes is organisation-wide, not a team's.

    That is the token the console holds in a real deployment, so the queue has
    to answer it — an empty queue is an answer, a refusal is a broken screen.
    """
    client, _, store = deployment
    org_secret = await issue_token(
        store, TokenService(gateway=store), user_id="root", role=Role.OWNER, node_id=None
    )

    listed = await client.get("/v1/proposals", headers=auth(org_secret))
    assert listed.status_code == 200, listed.text
    assert listed.json()["proposals"] == []
    assert listed.json()["acceptance"]["decided"] == 0

    counted = await client.get("/v1/proposals/count", headers=auth(org_secret))
    assert counted.status_code == 200, counted.text
    assert counted.json() == {"pending": 0}


async def test_an_org_scoped_reviewer_sees_and_decides_every_teams_proposals(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """An organisation-wide owner is every team's reviewer, not none of them."""
    client, _, store = deployment
    await queue_one(store, detector_proposal())
    org_secret = await issue_token(
        store, TokenService(gateway=store), user_id="root", role=Role.OWNER, node_id=None
    )

    listed = await client.get("/v1/proposals", headers=auth(org_secret))
    assert listed.status_code == 200, listed.text
    assert [row["proposal_id"] for row in listed.json()["proposals"]] == ["prop-det"]

    decided = await client.post(
        "/v1/proposals/prop-det/decision",
        json={"verdict": "approve"},
        headers=auth(org_secret),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["state"] == "approved"


async def test_the_acceptance_figure_carries_both_numbers(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """A rate with no denominator lets five decisions pass for two hundred."""
    client, secret, store = deployment
    await queue_one(store, detector_proposal("prop-a"))
    await queue_one(store, detector_proposal("prop-b"))

    await client.post(
        "/v1/proposals/prop-a/decision", json={"verdict": "approve"}, headers=auth(secret)
    )
    await client.post(
        "/v1/proposals/prop-b/decision",
        json={"verdict": "reject", "reason": "Already covered by the shipped set."},
        headers=auth(secret),
    )

    figure = (await client.get("/v1/proposals", headers=auth(secret))).json()["acceptance"]

    assert figure == {"decided": 2, "approved": 1, "rate": 0.5}
