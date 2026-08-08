"""The closed-loop routes: what they say, and what they refuse to say.

The assertion this file exists for is the first one. An action that has been
executed and not yet verified must come back saying so — not with a missing
verdict a caller could read either way, and never with anything that reads as
success. The five minutes between the change and the check is exactly when an
operator is looking.

The refusals are the other half. Clearing a suspension without a reason is
rejected at the schema before a handler runs, and closing a recurring problem
without naming the change that closed it is rejected the same way: both are
records of a person having looked, and a record with no reason says nobody did.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, ConfigNodeKind, PersistenceGateway, TenantScope
from platform.persistence.ports.remediation_ledger import (
    RecurringProblem,
    RemediationOutcome,
    VerificationState,
    VerificationVerdict,
)
from platform.remediation.suspension import AutonomySuspensions
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.asyncio

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def an_outcome(
    *,
    action_id: str = "action-1",
    verdict: VerificationVerdict | None = None,
    capability: str = "clear_cache",
    resource_id: str = "store-cove",
    minutes: float = 0.0,
) -> RemediationOutcome:
    """Return one ledger row, verified or still settling."""
    return RemediationOutcome(
        action_id=action_id,
        capability=capability,
        resource_id=resource_id,
        condition_key="datastore-near-full",
        team_node_id=TEAM_PAYMENTS,
        incident_id="incident-1",
        executed_at=at(minutes),
        due_at=at(minutes + 5),
        settle_seconds=300,
        state=(VerificationState.VERIFIED if verdict else VerificationState.AWAITING),
        verdict=verdict,
        signal_names=("filesystem.used_percent",),
        before={"filesystem.used_percent": 95.65},
        after={"filesystem.used_percent": 60.0} if verdict else {},
        verified_at=at(minutes + 5) if verdict else None,
        autonomous=True,
    )


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, PersistenceGateway, str]]:
    """Yield a client, the store behind it, and an owner's bearer token."""
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
        store, state.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield client, store, secret


def bearer(secret: str) -> dict[str, str]:
    """Return the header a request carries."""
    return {"authorization": f"Bearer {secret}"}


async def test_an_action_awaiting_verification_never_reads_as_a_success(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """FR-007 and T-012: the state is a field, not something a caller infers."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.remediation.record(an_outcome())

    listing = await client.get("/v1/remediations", headers=bearer(secret))
    detail = await client.get("/v1/remediations/action-1", headers=bearer(secret))

    assert listing.status_code == 200
    assert listing.json()["awaiting"] == 1
    row = listing.json()["outcomes"][0]
    assert row["awaiting_verification"] is True
    assert row["verdict"] is None
    assert detail.json()["awaiting_verification"] is True
    assert detail.json()["before"] == {"filesystem.used_percent": 95.65}
    assert detail.json()["after"] == {}


async def test_a_verified_action_carries_its_verdict_and_both_sets_of_values(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """SC-001 over the API: the values are what makes the verdict arguable."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.remediation.record(an_outcome(verdict=VerificationVerdict.EFFECTIVE))

    response = await client.get("/v1/remediations/action-1", headers=bearer(secret))

    body = response.json()
    assert body["awaiting_verification"] is False
    assert body["verdict"] == "effective"
    assert body["before"] == {"filesystem.used_percent": 95.65}
    assert body["after"] == {"filesystem.used_percent": 60.0}
    assert body["settle_seconds"] == 300


async def test_an_unknown_action_is_a_404_that_does_not_describe_the_tenant(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """A missing row and another tenant's row must be indistinguishable."""
    client, _, secret = deployment

    response = await client.get("/v1/remediations/nothing", headers=bearer(secret))

    assert response.status_code == 404
    assert ORG not in response.text


async def test_effectiveness_answers_the_question_a_proposal_asks(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """FR-015: the counts a screen renders and the sentence a reviewer reads."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.INEFFECTIVE)
        )
        await uow.remediation.record(
            an_outcome(action_id="b", verdict=VerificationVerdict.WORSENED, minutes=10)
        )

    response = await client.get(
        "/v1/remediations/effectiveness/summary",
        params={"capability": "clear_cache", "resource": "store-cove"},
        headers=bearer(secret),
    )

    body = response.json()
    assert body["verified"] == 2
    assert body["success_ratio"] == 0.0
    assert body["known"] is True
    assert body["discouraged"] is True
    assert body["counts"] == {"ineffective": 1, "worsened": 1}
    assert "propose something else" in body["summary"]


async def test_effectiveness_sliced_by_one_dimension_is_the_aggregate(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """FR-014 over the API, with no capability-and-resource pair to narrow on."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.EFFECTIVE)
        )
        await uow.remediation.record(
            an_outcome(
                action_id="b",
                verdict=VerificationVerdict.EFFECTIVE,
                resource_id="store-reef",
                minutes=5,
            )
        )

    response = await client.get(
        "/v1/remediations/effectiveness/summary",
        params={"capability": "clear_cache"},
        headers=bearer(secret),
    )

    assert response.json()["total"] == 2
    assert response.json()["counts"] == {"effective": 2}


async def test_a_recurring_problem_is_listed_and_closed_by_naming_a_change(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """FR-018 over the API: closed by a change, and the change is on the record."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.remediation.upsert_problem(
            RecurringProblem(
                problem_id="problem-1",
                pattern_key="clear_cache@store-cove",
                capability="clear_cache",
                resource_id="store-cove",
                title="clear_cache keeps being applied to store-cove",
                summary="Four applications in thirty days.",
                raised_at=at(),
                occurrences=4,
                window_seconds=2_592_000,
            )
        )

    listed = await client.get("/v1/remediations/problems/recurring", headers=bearer(secret))
    assert [item["problem_id"] for item in listed.json()["problems"]] == ["problem-1"]
    assert listed.json()["problems"][0]["suppresses_autonomy"] is True

    refused = await client.post(
        "/v1/remediations/problems/problem-1/close", json={}, headers=bearer(secret)
    )
    assert refused.status_code == 422

    closed = await client.post(
        "/v1/remediations/problems/problem-1/close",
        json={"change": "added log rotation to the datastore"},
        headers=bearer(secret),
    )

    assert closed.status_code == 200
    assert closed.json()["live"] is False
    assert closed.json()["close_reason"] == "added log rotation to the datastore"
    assert closed.json()["closed_by"] == "ada"

    still_live = await client.get("/v1/remediations/problems/recurring", headers=bearer(secret))
    assert still_live.json()["problems"] == []


async def test_closing_a_problem_nobody_raised_is_a_404(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """Somebody working from a stale listing gets an answer, not a stack trace."""
    client, _, secret = deployment

    response = await client.post(
        "/v1/remediations/problems/nothing/close",
        json={"change": "a change"},
        headers=bearer(secret),
    )

    assert response.status_code == 404


async def test_a_suspension_is_visible_and_cleared_with_a_reason(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """FR-010 and T-017 over the API: visible, and cleared only by a person."""
    client, store, secret = deployment
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await AutonomySuspensions(audit=uow.audit, clock=lambda: at()).suspend(
            "store-cove",
            reason="clear_cache made things worse and the rollback failed",
            action_id="action-1",
        )

    listed = await client.get("/v1/remediations/suspensions", headers=bearer(secret))
    assert [item["resource_id"] for item in listed.json()["suspensions"]] == ["store-cove"]
    assert listed.json()["suspensions"][0]["live"] is True

    refused = await client.post(
        "/v1/remediations/suspensions/store-cove/clear", json={}, headers=bearer(secret)
    )
    assert refused.status_code == 422

    cleared = await client.post(
        "/v1/remediations/suspensions/store-cove/clear",
        json={"reason": "replica count restored by hand and the workload is healthy"},
        headers=bearer(secret),
    )

    assert cleared.status_code == 200
    assert cleared.json()["live"] is False
    assert cleared.json()["cleared_by"] == "ada"

    after = await client.get("/v1/remediations/suspensions", headers=bearer(secret))
    assert after.json()["suspensions"] == []


async def test_clearing_a_resource_that_is_not_suspended_is_a_404(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """An operator who cleared it twice gets an answer rather than a 500."""
    client, _, secret = deployment

    response = await client.post(
        "/v1/remediations/suspensions/store-cove/clear",
        json={"reason": "nothing to do"},
        headers=bearer(secret),
    )

    assert response.status_code == 404


async def test_a_listing_above_the_bound_is_refused_rather_than_shortened(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """A caller that asked for 500 and received 100 cannot tell that from 100."""
    client, _, secret = deployment

    response = await client.get("/v1/remediations", params={"limit": 500}, headers=bearer(secret))

    assert response.status_code == 400
