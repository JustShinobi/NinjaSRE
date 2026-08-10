"""The CLI's remote transport, driven against the API this repository serves.

The CLI's ``--endpoint`` path was written against a documented shape before the
REST surface existed, and was only ever exercised against an opener that
answered with whatever the test wanted. That proves the client parses its own
invention. It does not prove a single request it issues is one the deployment
answers, and every disagreement between the two — a verb, a body field, a
response envelope — is invisible until an operator points the CLI at a real
deployment during an incident.

So nothing here stands in for the boundary being proven: the application is the
real ``create_app``, the persistence is the same ``PersistenceGateway`` protocol
Postgres implements, the token is issued by the real ``TokenService`` and
checked by the real permission guard, and the client is the real
``RemoteClient`` opening what it would open over the network.

``RemoteClient`` opens synchronously, so the application runs on its own loop in
its own thread and the opener hands requests across. That is what a socket would
have done, minus the socket.
"""

from __future__ import annotations

import asyncio
import io
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.runs import RUN_METADATA_TEAM
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.config_service.document import NodeDocument
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.estate_repository import (
    HealthDerivation,
    Resource,
    ResourceHealth,
)
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key
from platform.persistence.ports.transaction import TenantScope
from surfaces.cli.client import (
    Endpoint,
    EstateFilter,
    IncidentFilter,
    InvestigationRequest,
    RemoteClient,
    ScheduleRequest,
)
from surfaces.cli.errors import CliError, UnavailableError
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    TEAM_PLATFORM,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.contract

RUN_ID = "run-0001"
MASKING_LEVEL = "policies.masking.level"
ENDPOINT_URL = "https://ninjasre.internal"


class _Answer(io.BytesIO):
    """What ``urlopen`` returns, as much of it as this client reads."""

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass(slots=True)
class _Deployment:
    """A running application, reachable through a urllib-shaped opener."""

    loop: asyncio.AbstractEventLoop
    thread: threading.Thread
    http: AsyncClient
    gateway: FakePersistence
    token: str

    def run(self, coroutine: Any) -> Any:
        """Run ``coroutine`` on the application's own loop and return its result."""
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=30)

    def open(self, request: urllib.request.Request, timeout: float = 0) -> _Answer:
        """Answer one request from the real application."""
        answer = self.run(
            self.http.request(
                request.get_method(),
                request.full_url,
                content=request.data,
                headers=dict(request.header_items()),
            )
        )
        if answer.status_code >= 400:
            # The body is handed over as the file object, which is what
            # ``urllib`` does over a socket. Without it the client's own
            # ``_failure_detail`` has nothing to read, and every refusal in this
            # suite would read as a bare status — hiding exactly the sentence the
            # deployment wrote for the operator.
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=answer.status_code,
                msg=answer.text,
                hdrs=None,  # type: ignore[arg-type]
                fp=_Answer(answer.content),
            )
        return _Answer(answer.content)

    def close(self) -> None:
        """Stop the application's loop and join its thread."""
        self.run(self.http.aclose())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=10)


async def _seed(gateway: FakePersistence) -> None:
    """Create the organisation, two teams with settings, and one finished run."""
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        root = await uow.config.get(ORG)
        assert root is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=ORG,
                kind=root.kind,
                name=root.name,
                parent_id=None,
                values=NodeDocument.of(
                    {"policies": {"masking": {"level": "standard", "enabled": True}}}
                ).to_values(),
                version=root.version,
            )
        )
        for team in (TEAM_PAYMENTS, TEAM_PLATFORM):
            await uow.config.upsert(
                ConfigNode(node_id=team, kind=ConfigNodeKind.TEAM, name=team, parent_id=ORG)
            )
    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        await uow.run_traces.start_run(
            AgentRun(
                run_id=RUN_ID,
                trigger="alert",
                status=RunStatus.COMPLETED,
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                finished_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
                summary="the checkout pool was exhausted",
                metadata={RUN_METADATA_TEAM: TEAM_PAYMENTS},
            )
        )


async def _seed_estate(gateway: FakePersistence, now: datetime) -> None:
    """Write a node and one stopped guest hanging off it."""
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-node",
                kind="node",
                source="proxmox",
                native_id="node/pve1",
                display_name="pve1",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await uow.estate.upsert(
            Resource(
                resource_id="res-guest",
                kind="virtual_machine",
                source="proxmox",
                native_id="qemu/101",
                display_name="checkout",
                parent_id="res-node",
                labels=("env:prod",),
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await uow.estate.record_health(
            "res-node",
            HealthDerivation(
                state=ResourceHealth.HEALTHY,
                rule="provider_status",
                derived_at=now,
                raw_status="online",
            ),
        )
        await uow.estate.record_health(
            "res-guest",
            HealthDerivation(
                state=ResourceHealth.UNHEALTHY,
                rule="provider_status",
                derived_at=now,
                raw_status="stopped",
            ),
        )


@pytest.fixture
def deployment() -> Iterator[_Deployment]:
    """Return the real application, running on its own loop, with a real token."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    def on_loop(coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=30)

    gateway = FakePersistence()
    on_loop(_seed(gateway))
    tokens = TokenService(gateway=gateway)
    token = on_loop(
        issue_token(gateway, tokens, user_id="ada", role=Role.ADMIN, node_id=TEAM_PAYMENTS)
    )
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=FakeInvestigationRunner())
    http = AsyncClient(transport=ASGITransport(app=create_app(state)), base_url=ENDPOINT_URL)

    running = _Deployment(loop=loop, thread=thread, http=http, gateway=gateway, token=token)
    try:
        yield running
    finally:
        running.close()


@pytest.fixture
def remote(deployment: _Deployment) -> RemoteClient:
    """Return the CLI's remote client, pointed at the running application."""
    return RemoteClient(
        endpoint=Endpoint(url=ENDPOINT_URL, token=deployment.token), opener=deployment.open
    )


# --- What the API answers ----------------------------------------------------


def test_a_listing_reaches_the_runs_the_deployment_holds(remote: RemoteClient) -> None:
    # The failure this catches: a client that parses an envelope the API does
    # not write reports an empty listing on a deployment with runs in it, and
    # nothing about "no runs" says the two disagreed.
    runs = asyncio.run(remote.list_runs())

    assert [run.run_id for run in runs] == [RUN_ID]
    assert runs[0].status == RunStatus.COMPLETED.value
    assert runs[0].trigger == "alert"
    assert runs[0].started_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert runs[0].ended_at == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)


def test_one_run_is_read_back_in_full(remote: RemoteClient) -> None:
    detail = asyncio.run(remote.show_run(RUN_ID))

    assert detail.run.run_id == RUN_ID
    assert detail.result == "the checkout pool was exhausted"


def test_a_run_that_is_not_there_is_reported_as_missing(remote: RemoteClient) -> None:
    from surfaces.cli.errors import NotFoundError

    with pytest.raises(NotFoundError):
        asyncio.run(remote.show_run("run-9999"))


def test_a_replay_is_rebuilt_from_the_deployments_own_trace(remote: RemoteClient) -> None:
    replay = asyncio.run(remote.replay_run(RUN_ID))

    assert replay.run_id == RUN_ID


def test_starting_an_investigation_returns_the_runs_identity(remote: RemoteClient) -> None:
    outcome = asyncio.run(
        remote.investigate(InvestigationRequest(objective="checkout is timing out"))
    )

    assert outcome.run_id
    assert outcome.status


def test_effective_configuration_comes_back_attributed(remote: RemoteClient) -> None:
    view = asyncio.run(remote.show_config(TEAM_PAYMENTS))

    assert view.node_id == TEAM_PAYMENTS
    assert view.entries
    assert all(entry.source_node_id for entry in view.entries)


def test_a_configuration_write_lands_and_is_read_back(remote: RemoteClient) -> None:
    # The failure this catches: the API takes a patch document and the client
    # was sending a path and a value, so every remote write was rejected.
    change = asyncio.run(remote.set_config(TEAM_PAYMENTS, MASKING_LEVEL, "strict"))

    assert change.applied
    assert change.after == "strict"
    after = asyncio.run(remote.show_config(TEAM_PAYMENTS))
    assert any(entry.path == MASKING_LEVEL and entry.value == "strict" for entry in after.entries)


def test_a_schedule_is_created_listed_and_removed(remote: RemoteClient) -> None:
    created = asyncio.run(
        remote.add_schedule(
            ScheduleRequest(objective="nightly capacity check", cron="0 2 * * *", job_id="nightly")
        )
    )

    assert created.job_id == "nightly"
    assert created.cron == "0 2 * * *"

    listed = asyncio.run(remote.list_schedules())
    assert [schedule.job_id for schedule in listed] == ["nightly"]

    assert asyncio.run(remote.remove_schedule("nightly")) is True
    assert asyncio.run(remote.remove_schedule("nightly")) is False


def test_memory_is_searched_and_counted(remote: RemoteClient) -> None:
    assert asyncio.run(remote.search_memory("checkout")) == ()
    assert asyncio.run(remote.memory_stats()).episodes == 0


def test_the_estate_is_listed_summarised_opened_and_suppressed(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """The CLI's estate commands, against the routes the deployment really serves."""
    now = datetime.now(UTC)
    deployment.run(_seed_estate(deployment.gateway, now))

    listed = asyncio.run(remote.list_estate(EstateFilter()))
    summary = asyncio.run(remote.estate_summary())
    detail = asyncio.run(remote.show_resource("res-guest"))
    suppressed = asyncio.run(
        remote.set_maintenance(
            "res-guest", until=now + timedelta(hours=1), reason="replacing a disk"
        )
    )
    released = asyncio.run(remote.clear_maintenance("res-guest"))

    assert {resource.resource_id for resource in listed} == {"res-node", "res-guest"}
    assert summary.total == 2
    assert summary.problems == 1
    assert detail.resource.health == "unhealthy"
    assert detail.rule == "provider_status"
    assert detail.raw_status == "stopped"
    assert [entry.state for entry in detail.transitions] == ["unhealthy"]
    assert suppressed.health == "maintenance"
    assert suppressed.maintenance_reason == "replacing a disk"
    assert released.health == "unhealthy"


def test_an_estate_filter_reaches_the_routes_own_parameters(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """Every dimension the filter carries is one the deployment actually reads."""
    now = datetime.now(UTC)
    deployment.run(_seed_estate(deployment.gateway, now))

    by_kind = asyncio.run(remote.list_estate(EstateFilter(kinds=("node",))))
    by_health = asyncio.run(remote.list_estate(EstateFilter(health=("unhealthy",))))
    by_label = asyncio.run(remote.list_estate(EstateFilter(labels=("env:prod",))))
    by_parent = asyncio.run(remote.list_estate(EstateFilter(parent_id="res-node")))

    assert [found.resource_id for found in by_kind] == ["res-node"]
    assert [found.resource_id for found in by_health] == ["res-guest"]
    assert [found.resource_id for found in by_label] == ["res-guest"]
    assert [found.resource_id for found in by_parent] == ["res-guest"]


async def _seed_observation(gateway: FakePersistence, now: datetime) -> None:
    """Declare one detector, seed the signals that fire it, and raise one incident."""
    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        team = await uow.config.get(TEAM_PAYMENTS)
        assert team is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=team.kind,
                name=team.name,
                parent_id=team.parent_id,
                values=NodeDocument.of(
                    {
                        "policies": {
                            "observation": {
                                "detectors": [
                                    {
                                        "detector_id": "datastore-near-full",
                                        "signal": "storage.used_percent",
                                        "name": "Datastore near full",
                                        "description": "A datastore that fills stops "
                                        "every guest on it at once.",
                                        "resource_kinds": ["datastore"],
                                        "fire_value": 90.0,
                                        "clear_value": 80.0,
                                        "for_seconds": 300,
                                        "recovery_seconds": 300,
                                        "severity": "critical",
                                    }
                                ]
                            }
                        }
                    }
                ).to_values(),
                version=team.version,
            )
        )

    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="store-cove",
                kind="datastore",
                source="proxmox",
                native_id="store-cove",
            )
        )
        await uow.signals.append(
            [
                Signal(
                    signal_id=signal_key("storage.used_percent", "store-cove", moment),
                    name="storage.used_percent",
                    resource_id="store-cove",
                    source="poller:proxmox",
                    kind=SignalKind.NUMBER,
                    observed_at=moment,
                    value=95.65,
                    interval_seconds=60,
                )
                for moment in (
                    now - timedelta(minutes=4),
                    now - timedelta(minutes=2),
                    now,
                )
            ]
        )
        await IncidentLifecycle(store=uow.incidents).raise_incident(
            IncidentRaise(
                correlation_key="detector:datastore-near-full",
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
                        observed_at=now,
                    ),
                ),
                team_node_id=TEAM_PAYMENTS,
                cause="the datastore crossed ninety per cent and stayed there",
            ),
            now=now,
        )


def test_incidents_are_listed_opened_and_closed(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """The CLI's incident commands, against the routes the deployment really serves."""
    now = datetime.now(UTC)
    deployment.run(_seed_observation(deployment.gateway, now))

    listed = asyncio.run(remote.list_incidents(IncidentFilter()))
    detail = asyncio.run(remote.show_incident(listed[0].incident_id))
    closed = asyncio.run(
        remote.close_incident(listed[0].incident_id, reason="the datastore was expanded")
    )

    assert [entry.detector for entry in listed] == ["datastore-near-full"]
    assert listed[0].subjects == ("store-cove",)
    assert detail.subjects[0].evidence == {"used_percent": "95.65"}
    assert [entry.kind for entry in detail.timeline] == ["opened"]
    assert closed.state == "closed_without_action"
    assert closed.close_reason == "the datastore was expanded"


def test_an_incident_is_suppressed_with_the_rule_that_covered_it(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    now = datetime.now(UTC)
    deployment.run(_seed_observation(deployment.gateway, now))
    listed = asyncio.run(remote.list_incidents(IncidentFilter(live_only=True)))

    suppressed = asyncio.run(
        remote.suppress_incident(
            listed[0].incident_id, rule="rack-4-migration", reason="the rack is being moved"
        )
    )

    assert suppressed.state == "suppressed"
    assert suppressed.suppressed_by == "rack-4-migration"


def test_detectors_are_listed_toggled_and_dry_run(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """Including the one property a dry run has to have: it fires nothing."""
    now = datetime.now(UTC)
    deployment.run(_seed_observation(deployment.gateway, now))

    listed = asyncio.run(remote.list_detectors())
    seen = asyncio.run(remote.list_observations())
    run = asyncio.run(remote.dry_run_detector("datastore-near-full"))
    disabled = asyncio.run(remote.set_detector_enabled("datastore-near-full", enabled=False))

    assert [entry.detector_id for entry in listed] == ["datastore-near-full"]
    assert listed[0].signal == "storage.used_percent"
    assert not asyncio.run(remote.detection_state()).paused
    assert [entry.subject for entry in seen] == ["store-cove"]
    assert run.would_fire
    assert not run.fired
    assert not disabled.enabled


def test_the_integration_catalogue_comes_back(remote: RemoteClient) -> None:
    integrations = asyncio.run(remote.list_integrations())

    assert integrations
    assert all(status.integration for status in integrations)


def test_verifying_an_integration_reports_its_credential_state(remote: RemoteClient) -> None:
    status = asyncio.run(remote.verify_integration("datadog"))

    assert status.integration == "datadog"
    assert status.credential_state


# --- Writing a credential over the wire --------------------------------------

#: Valid against Datadog's declared format, so the write it is used in is one
#: the deployment really accepts. A sweep over a rejected write would prove only
#: that a refusal is quiet.
SENTINEL_KEY = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
SENTINEL_APP_KEY = "abcdefghij0123456789ABCDEFGHIJ0123456789"


def test_a_credential_written_remotely_lands_and_verifies(remote: RemoteClient) -> None:
    """The four steps an onboarding takes, against the route that serves them."""
    stored = asyncio.run(
        remote.store_integration_credential(
            "datadog", {"api_key": SENTINEL_KEY, "app_key": SENTINEL_APP_KEY}
        )
    )
    verified = asyncio.run(remote.verify_integration("datadog"))

    assert stored.integration == "datadog"
    assert stored.configured
    assert stored.credential_state == "configured"
    assert verified.healthy


def test_the_secret_is_in_the_request_body_and_in_nothing_else(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """Where a credential is allowed to be, and the four places it is not.

    Recorded off the request the client actually built, rather than asserted
    about a request the test constructed — the failure worth preventing is a
    client that puts a credential in a query string or a header, both of which
    are logged by every proxy between here and the deployment.
    """
    seen: list[urllib.request.Request] = []

    def watching(request: urllib.request.Request, timeout: float = 0) -> _Answer:
        seen.append(request)
        return deployment.open(request, timeout)

    watched = RemoteClient(endpoint=remote.endpoint, opener=watching)
    status = asyncio.run(
        watched.store_integration_credential(
            "datadog", {"api_key": SENTINEL_KEY, "app_key": SENTINEL_APP_KEY}
        )
    )

    written = seen[-1]
    assert written.get_method() == "PUT"
    assert written.full_url.endswith("/v1/integrations/datadog/credential")
    assert SENTINEL_KEY not in written.full_url
    assert SENTINEL_KEY not in repr(dict(written.header_items()))
    assert SENTINEL_KEY in (written.data or b"").decode()
    # And not on the way back out.
    assert SENTINEL_KEY not in repr(status)
    assert SENTINEL_KEY not in repr(status.to_record())


def test_a_credential_the_vendors_schema_refuses_names_the_field_not_the_value(
    remote: RemoteClient,
) -> None:
    with pytest.raises(CliError) as refused:
        asyncio.run(
            remote.store_integration_credential(
                "datadog", {"api_key": SENTINEL_KEY, "app_key": "too-short"}
            )
        )

    assert "app_key" in str(refused.value)
    assert SENTINEL_KEY not in str(refused.value)
    assert "too-short" not in str(refused.value)


# --- What the API does not answer --------------------------------------------


@pytest.mark.parametrize(
    "ask",
    [
        pytest.param(lambda client: client.cost_of_runs(), id="cost"),
        pytest.param(lambda client: client.spend(), id="spend"),
        pytest.param(lambda client: client.list_providers(), id="providers"),
        pytest.param(lambda client: client.verify_provider("anthropic"), id="verify-provider"),
        pytest.param(lambda client: client.credential_fields("datadog"), id="credential-fields"),
        pytest.param(lambda client: client.diagnose(), id="doctor"),
    ],
)
def test_what_this_api_does_not_serve_is_refused_by_name(remote: RemoteClient, ask: Any) -> None:
    # These have no route on this surface. The failure worth preventing is not
    # the absence — it is a client that answers them from defaults, so an
    # operator reads "no providers configured" or "£0.00 spent" and believes it.
    with pytest.raises(UnavailableError) as refusal:
        asyncio.run(ask(remote))

    assert "does not expose" in str(refusal.value)
    assert refusal.value.remedy


def test_a_refusal_for_something_unserved_never_carries_what_was_asked(
    remote: RemoteClient,
) -> None:
    # A refusal is raised before any request is built, and must not become the
    # place the argument ends up: it is a string an operator pastes.
    with pytest.raises(UnavailableError) as refusal:
        asyncio.run(remote.credential_fields("a-vendor-nobody-installed"))

    assert "a-vendor-nobody-installed" not in str(refusal.value)
