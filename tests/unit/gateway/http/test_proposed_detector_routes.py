"""A detector a document proposed, over HTTP: visible, previewable, and quiet.

The whole of the risk in reading detectors out of somebody's runbook is that one
of them starts paging people before anybody decided it should. These are the
three assertions that say it does not: the row arrives disabled and marked as a
proposal, the dry run works on it so an operator can see what it *would* have
found, and nothing it would have found reaches the observations a tick acts on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.config_service.schema.policies import DetectorSettings, ObservationPolicySettings
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.knowledge.base.detector_candidates import CANDIDATE_ID_PREFIX, candidates_from
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, issue_token
from tests.unit.gateway.http.test_incident_routes import FakeInvestigationRunner

pytestmark = pytest.mark.anyio

#: The verification document, in the shape the real one is written in.
QUERIES = """# Cluster double-check queries

## No datastore is above its safe fill

A datastore past this cannot complete a snapshot of its largest guest.

- signal: `datastore.used_percent`
- fires when: above 85
"""

CANDIDATE_ID = f"{CANDIDATE_ID_PREFIX}no-datastore-is-above-its-safe-fill"


def _at(minutes: float = 0.0) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _sample(minutes: float) -> Signal:
    """Return one datastore reading, comfortably over the proposed threshold."""
    observed_at = _at(minutes)
    return Signal(
        signal_id=signal_key("datastore.used_percent", "store-cove", observed_at),
        name="datastore.used_percent",
        resource_id="store-cove",
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=95.0,
        interval_seconds=60,
    )


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, str]]:
    """Yield a client over a deployment whose only detector is a candidate."""
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
        await uow.estate.upsert(
            Resource(
                resource_id="store-cove",
                kind="datastore",
                source="proxmox",
                native_id="store-cove",
                last_seen_at=_at(),
            )
        )
        await uow.signals.append([_sample(-minutes) for minutes in (6, 4, 2, 0)])

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
        await _declare(client, secret, store)
        yield client, secret


async def _declare(client: AsyncClient, secret: str, store: PersistenceGateway) -> None:
    """Write the candidates the document proposes into the team's configuration."""
    proposed = candidates_from(
        QUERIES,
        document_id="corpus:docs/runbooks/cluster-double-check-queries.md",
        location="docs/runbooks/cluster-double-check-queries.md",
    )
    assert proposed, "the document must actually propose something"
    # Through the configuration service, exactly as an operator's own detector
    # is written: the audit line and the field locks are not optional because
    # the author was a document.
    entries: list[dict[str, Any]] = [candidate.to_settings() for candidate in proposed]
    ObservationPolicySettings(detectors=[DetectorSettings(**entry) for entry in entries])
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        json={"patch": {"policies": {"observation": {"detectors": entries}}}},
        headers={"authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text


async def test_the_candidate_is_listed_as_a_proposal_and_is_not_running(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment

    response = await client.get("/v1/detectors", headers={"authorization": f"Bearer {secret}"})

    row = response.json()["detectors"][0]
    assert row["detector_id"] == CANDIDATE_ID
    assert row["enabled"] is False
    assert row["proposed"] is True


async def test_the_row_cites_the_document_and_quotes_it(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment

    response = await client.get("/v1/detectors", headers={"authorization": f"Bearer {secret}"})

    row = response.json()["detectors"][0]
    assert row["origin"] == "corpus:docs/runbooks/cluster-double-check-queries.md"
    assert "cannot complete a snapshot" in row["origin_excerpt"]


async def test_a_dry_run_shows_what_it_would_have_found(
    deployment: tuple[AsyncClient, str],
) -> None:
    # The point of proposing rather than enabling: an operator sees the answer
    # before anything can page anybody with it.
    client, secret = deployment

    response = await client.post(
        f"/v1/detectors/{CANDIDATE_ID}/dry-run",
        headers={"authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["would_fire"] is True
    assert body["fired"] is False
    assert [entry["subject"] for entry in body["observations"]] == ["store-cove"]


async def test_nothing_it_would_find_reaches_the_observations(
    deployment: tuple[AsyncClient, str],
) -> None:
    # A tick acts on the observations. A candidate that appeared here would be
    # a document that had enabled itself.
    client, secret = deployment

    response = await client.get("/v1/observations", headers={"authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    assert response.json()["observations"] == []


async def test_enabling_it_is_an_ordinary_detector_write(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment
    headers = {"authorization": f"Bearer {secret}"}

    enabled = await client.post(f"/v1/detectors/{CANDIDATE_ID}/enable", headers=headers)

    assert enabled.status_code == 200
    listing = await client.get("/v1/detectors", headers=headers)
    row = listing.json()["detectors"][0]
    assert row["enabled"] is True
    # Still a proposal in provenance. Where it came from does not stop being
    # true because somebody agreed with it.
    assert row["proposed"] is True
    observations = await client.get("/v1/observations", headers=headers)
    assert observations.json()["observations"] != []
