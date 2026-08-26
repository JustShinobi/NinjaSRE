"""The incident and detector routes: what they return, and what they refuse.

The two refusals are the interesting half. A close without a reason is rejected
at the schema before a handler runs, and a dry run has no parameter that would
make it fire — an operator testing a threshold against last week must not be
able to page somebody with last week's numbers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    PersistenceGateway,
    Resource,
    Signal,
    SignalKind,
    TenantScope,
)
from platform.persistence.ports.signal_store import signal_key
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.asyncio


def at(minutes: float = 0.0) -> datetime:
    """Return an instant offset by ``minutes`` from right now.

    The routes read the wall clock — a "last verdict" is what the detector
    concludes *now* — so the signals a test seeds have to be near it. Read at
    call time rather than at import, because a module-level epoch drifts out of
    every window over the length of a full suite run and every detector then
    reports that it has nothing to read.
    """
    return datetime.now(UTC) + timedelta(minutes=minutes)


def a_detector(detector_id: str = "datastore-near-full", **overrides: Any) -> dict[str, Any]:
    """Return the settings document one detector is written as."""
    return {
        "detector_id": detector_id,
        "signal": "storage.used_percent",
        "name": "Datastore near full",
        "description": "A datastore that fills stops every guest on it at once.",
        "resource_kinds": ["datastore"],
        "fire_value": 90.0,
        "clear_value": 80.0,
        "for_seconds": 300,
        "recovery_seconds": 300,
        "severity": "critical",
        **overrides,
    }


def a_raise(key: str = "detector:datastore-near-full") -> IncidentRaise:
    """Return one raise."""
    return IncidentRaise(
        correlation_key=key,
        title="Datastore near full",
        summary="store-cove is 95.65% full",
        origin=IncidentOrigin.DETECTOR,
        origin_id="datastore-near-full",
        severity="critical",
        subjects=(
            IncidentSubject(
                resource_id="store-cove",
                detail="store-cove is 95.65% full",
                evidence={"used_percent": "95.65"},
                observed_at=at(),
            ),
        ),
        team_node_id=TEAM_PAYMENTS,
        cause="the datastore crossed ninety per cent and stayed there",
    )


def sample(minutes: float, value: float) -> Signal:
    """Return one numeric sample about the datastore."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key("storage.used_percent", "store-cove", observed_at),
        name="storage.used_percent",
        resource_id="store-cove",
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        interval_seconds=60,
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
        await uow.estate.upsert(
            Resource(
                resource_id="store-cove",
                kind="datastore",
                source="proxmox",
                native_id="store-cove",
            )
        )
        await uow.signals.append([sample(-4, 91.0), sample(-2, 92.0), sample(0, 95.65)])

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


async def declare_a_detector(client: AsyncClient, secret: str, **overrides: Any) -> None:
    """Write one detector into the team's configuration."""
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        json={"patch": {"policies": {"observation": {"detectors": [a_detector(**overrides)]}}}},
        headers=bearer(secret),
    )
    assert response.status_code == 200, response.text


async def open_an_incident(store: PersistenceGateway) -> str:
    """Raise one incident and return its identifier."""
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        incident = await IncidentLifecycle(store=uow.incidents).raise_incident(a_raise(), now=at())
    return incident.incident_id


# --- Incidents ------------------------------------------------------------------------


async def test_a_listing_names_every_subject_rather_than_counting_them(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    await open_an_incident(store)

    response = await client.get("/v1/incidents", headers=bearer(secret))

    assert response.status_code == 200
    body = response.json()
    assert [entry["subjects"] for entry in body["incidents"]] == [["store-cove"]]
    assert body["incidents"][0]["state"] == "open"


async def test_a_listing_carries_the_key_two_firings_of_one_cause_share(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """The correlation key reaches the wire, because grouping is impossible without it.

    It is mandatory on the domain object and is built from exactly the two
    things a reader groups by — the condition and the resource it fired on —
    and it was dropped at this boundary. Two consequences, both live: the
    console cannot fold repeated firings of one cause into one row, so an
    estate that raises the same seven conditions all day reads as fifty
    unrelated problems; and the global search already filters on this field,
    against a value that was always the empty string, so searching by
    correlation key matched nothing and said so to nobody.
    """
    client, store, secret = deployment
    await open_an_incident(store)

    response = await client.get("/v1/incidents", headers=bearer(secret))

    assert response.status_code == 200
    row = response.json()["incidents"][0]
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        stored = (await uow.incidents.query(IncidentQuery()))[0]
    assert row["correlation_key"] == stored.correlation_key
    assert row["correlation_key"] != ""


async def test_a_state_outside_the_closed_set_is_refused(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """Receiving every incident for ``state=acknowledged`` would be a lie about all of them."""
    client, _store, secret = deployment

    response = await client.get(
        "/v1/incidents", params={"state": "acknowledged"}, headers=bearer(secret)
    )

    assert response.status_code == 422
    assert "not an incident state" in response.text


async def test_one_incident_comes_back_with_its_timeline(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    incident_id = await open_an_incident(store)

    response = await client.get(f"/v1/incidents/{incident_id}", headers=bearer(secret))

    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["incident_id"] == incident_id
    assert body["subjects"][0]["evidence"] == {"used_percent": "95.65"}
    assert [entry["kind"] for entry in body["timeline"]] == ["opened"]
    assert body["timeline"][0]["cause"]


async def test_an_incident_nobody_raised_is_a_404(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, _store, secret = deployment

    response = await client.get("/v1/incidents/nothing-here", headers=bearer(secret))

    assert response.status_code == 404


async def test_closing_takes_a_reason_and_records_who(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    incident_id = await open_an_incident(store)

    response = await client.post(
        f"/v1/incidents/{incident_id}/close",
        json={"reason": "the datastore was expanded by hand"},
        headers=bearer(secret),
    )
    detail = await client.get(f"/v1/incidents/{incident_id}", headers=bearer(secret))

    assert response.status_code == 200
    assert response.json()["state"] == IncidentState.CLOSED_WITHOUT_ACTION.value
    assert response.json()["close_reason"] == "the datastore was expanded by hand"
    assert detail.json()["timeline"][-1]["actor"]


async def test_closing_without_a_reason_is_refused_before_a_handler_runs(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    incident_id = await open_an_incident(store)

    response = await client.post(
        f"/v1/incidents/{incident_id}/close", json={"reason": ""}, headers=bearer(secret)
    )

    assert response.status_code == 422


async def test_suppressing_names_what_covered_it(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    incident_id = await open_an_incident(store)

    response = await client.post(
        f"/v1/incidents/{incident_id}/suppress",
        json={"rule": "rack-4-migration", "reason": "the whole rack is being moved"},
        headers=bearer(secret),
    )

    assert response.status_code == 200
    assert response.json()["state"] == IncidentState.SUPPRESSED.value
    assert response.json()["suppressed_by"] == "rack-4-migration"


# --- Detectors --------------------------------------------------------------------------


async def test_the_detector_listing_reports_coverage_and_what_it_concludes_now(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, _store, secret = deployment
    await declare_a_detector(client, secret)

    response = await client.get("/v1/detectors", headers=bearer(secret))

    assert response.status_code == 200
    row = response.json()["detectors"][0]
    assert row["detector_id"] == "datastore-near-full"
    assert row["subjects_covered"] == 1
    assert row["subjects_total"] == 1
    assert row["last_verdict"] == "firing"
    assert row["enabled"] is True


async def test_the_listing_says_when_detection_is_paused(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """ "Why is this empty" is asked on the listing, so the answer belongs there."""
    client, _store, secret = deployment
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        json={
            "patch": {
                "policies": {
                    "observation": {
                        "detectors": [a_detector()],
                        "paused": True,
                        "pause_reason": "migrating the cluster",
                    }
                }
            }
        },
        headers=bearer(secret),
    )
    assert response.status_code == 200

    listing = await client.get("/v1/incidents", headers=bearer(secret))

    assert listing.json()["paused"] is True
    assert listing.json()["pause_reason"] == "migrating the cluster"


async def test_the_observations_endpoint_reports_what_the_detectors_see(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, _store, secret = deployment
    await declare_a_detector(client, secret)

    response = await client.get("/v1/observations", headers=bearer(secret))

    assert response.status_code == 200
    seen = response.json()["observations"]
    assert [entry["subject"] for entry in seen] == ["store-cove"]
    assert seen[0]["verdict"] == "firing"
    assert seen[0]["evidence"]["storage.used_percent"] == "95.65"


async def test_a_dry_run_reports_what_would_fire_and_fires_nothing(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, store, secret = deployment
    await declare_a_detector(client, secret)

    response = await client.post(
        "/v1/detectors/datastore-near-full/dry-run", headers=bearer(secret)
    )
    incidents = await client.get("/v1/incidents", headers=bearer(secret))

    assert response.status_code == 200
    assert response.json()["would_fire"] is True
    assert response.json()["fired"] is False
    assert incidents.json()["incidents"] == []


async def test_a_dry_run_of_a_detector_nobody_declared_is_a_404(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, _store, secret = deployment

    response = await client.post("/v1/detectors/nothing-here/dry-run", headers=bearer(secret))

    assert response.status_code == 404


async def test_disabling_a_detector_persists_through_configuration(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    """Not an in-process toggle: a restart must not undo an operator's decision."""
    client, store, secret = deployment
    await declare_a_detector(client, secret)

    disabled = await client.post(
        "/v1/detectors/datastore-near-full/disable", headers=bearer(secret)
    )
    listing = await client.get("/v1/detectors", headers=bearer(secret))

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        node = await uow.config.get(TEAM_PAYMENTS)

    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert listing.json()["detectors"][0]["enabled"] is False
    assert node is not None
    stored = node.values["settings"]["policies"]["observation"]["detectors"][0]
    assert stored["enabled"] is False


async def test_enabling_it_again_puts_it_back(
    deployment: tuple[AsyncClient, PersistenceGateway, str],
) -> None:
    client, _store, secret = deployment
    await declare_a_detector(client, secret)
    await client.post("/v1/detectors/datastore-near-full/disable", headers=bearer(secret))

    enabled = await client.post("/v1/detectors/datastore-near-full/enable", headers=bearer(secret))

    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
