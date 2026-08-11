"""The whole loop, over HTTP: proposed, reviewed, applied, undone, and recorded.

Acceptances 1, 2 and 5 in one pass, because they are one thing. An investigation
establishes something; the proposal arrives with the evidence and a link back to
the run; nobody's approval, nothing written; a person approves; the document
exists carrying the agent *and* the approver; the stored plan reverses it; and
the audit shows both directions.

Driven through the gateway rather than against the services, because every step
of that sentence is something a person does through an interface, and a loop
that only closes in Python is a loop nobody can walk.

The knowledge origin in particular, because it is the one the capability
already writes: the row `propose_knowledge` stores is exactly the row this queue
reads, which is what "one queue" has to mean if it means anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.proposals import KnowledgeProposal
from platform.knowledge.proposals import ProposalQueue as KnowledgeQueue
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, issue_token
from tests.unit.gateway.http.test_incident_routes import FakeInvestigationRunner

pytestmark = pytest.mark.anyio

REVIEWER = "ada"
RUN = "run-payments-5xx"
PROPOSAL = "prop-5xx-runbook"


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, str, FakePersistence]]:
    """Yield a client over a deployment whose agent has just finished a run."""
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


async def investigate_and_propose(store: FakePersistence) -> None:
    """Do what the investigation's ``propose_knowledge`` call does, verbatim.

    The capability's own binding, over the real queue. Scripting the *tool*
    rather than reproducing what it stores is the point: a test that wrote the
    approval row itself would pass on the day the capability stopped writing one.
    """
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    queue = KnowledgeQueue(
        gateway=store,
        scope=scope,
        ingestor=KnowledgeIngestor(gateway=store, scope=scope, embedder=LocalEmbedder()),
    )
    await queue.propose(
        KnowledgeProposal(
            proposal_id=PROPOSAL,
            org_id=ORG,
            team_node_id=TEAM_PAYMENTS,
            title="Payments 5xx after a limit change",
            body=(
                "When payments returns 5xx shortly after a deploy, compare the container "
                "memory limit against the previous revision before looking at the database."
            ),
            correlation_id=RUN,
            run_id=RUN,
            rationale="The last three investigations of this alert all ended here.",
            evidence=(f"{RUN}/turn-7",),
        )
    )


def auth(secret: str) -> dict[str, str]:
    """Return the authorization header for ``secret``."""
    return {"authorization": f"Bearer {secret}"}


async def test_the_loop_closes_and_leaves_a_record_of_both_directions(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    client, secret, store = deployment
    await investigate_and_propose(store)

    # 1 — it is waiting, with the evidence and a link back to the run.
    listed = (await client.get("/v1/proposals", headers=auth(secret))).json()
    row = next(item for item in listed["proposals"] if item["proposal_id"] == PROPOSAL)
    assert row["proposal_type"] == "knowledge"
    assert row["run_id"] == RUN
    assert row["evidence"] == [f"{RUN}/turn-7"]
    assert row["rationale"].startswith("The last three investigations")

    # 2 — and nothing has been written while it waits.
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        assert await uow.knowledge.count_chunks() == 0

    # 3 — a person approves, and the document exists carrying both names.
    decided = await client.post(
        f"/v1/proposals/{PROPOSAL}/decision",
        json={"verdict": "approve"},
        headers=auth(secret),
    )
    assert decided.status_code == 200, decided.text
    document_id = f"proposed-{PROPOSAL}"
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        written = await uow.knowledge.get_document(document_id)
    assert written is not None
    # The attribution is a sentence on the stored document's metadata, because
    # it is shown to whoever later reads it: "agent-originated, approved by Ada"
    # is what they need rather than a flag they would have to look up.
    attribution = str(written.metadata.get("attribution", ""))
    assert RUN in attribution
    assert REVIEWER in attribution

    # 4 — the plan stored at propose time undoes it, through the route that
    #     already existed for remediation.
    rolled = await client.post(f"/v1/approvals/{PROPOSAL}/rollback", headers=auth(secret))
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["completed_steps"] == [1]

    # 5 — and both acts are recoverable from the record rather than from memory.
    stored = (await client.get(f"/v1/approvals/{PROPOSAL}", headers=auth(secret))).json()
    assert stored["state"] == "approved"
    assert stored["decided_by"] == REVIEWER
    assert stored["rollback_plan"]["notes"] is not None
    assert "executed" in stored["rollback_plan"]["notes"]


async def test_the_queue_shows_the_capabilitys_own_row_rather_than_a_copy(
    deployment: tuple[AsyncClient, str, FakePersistence],
) -> None:
    """One queue means one row: the approvals surface and this one agree."""
    client, secret, store = deployment
    await investigate_and_propose(store)

    approvals = (await client.get("/v1/approvals", headers=auth(secret))).json()
    proposals = (await client.get("/v1/proposals", headers=auth(secret))).json()

    assert [item["approval_id"] for item in approvals["approvals"]] == [PROPOSAL]
    assert [item["proposal_id"] for item in proposals["proposals"]] == [PROPOSAL]
