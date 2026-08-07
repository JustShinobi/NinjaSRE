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
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.runs import RUN_METADATA_TEAM
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.config_service.document import NodeDocument
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.transaction import TenantScope
from surfaces.cli.client import (
    Endpoint,
    InvestigationRequest,
    RemoteClient,
    ScheduleRequest,
)
from surfaces.cli.errors import UnavailableError
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
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=answer.status_code,
                msg=answer.text,
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
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


def test_the_integration_catalogue_comes_back(remote: RemoteClient) -> None:
    integrations = asyncio.run(remote.list_integrations())

    assert integrations
    assert all(status.integration for status in integrations)


def test_verifying_an_integration_reports_its_credential_state(remote: RemoteClient) -> None:
    status = asyncio.run(remote.verify_integration("datadog"))

    assert status.integration == "datadog"
    assert status.credential_state


# --- What the API does not answer --------------------------------------------


@pytest.mark.parametrize(
    "ask",
    [
        pytest.param(lambda client: client.cost_of_runs(), id="cost"),
        pytest.param(lambda client: client.spend(), id="spend"),
        pytest.param(lambda client: client.list_providers(), id="providers"),
        pytest.param(lambda client: client.verify_provider("anthropic"), id="verify-provider"),
        pytest.param(lambda client: client.credential_fields("datadog"), id="credential-fields"),
        pytest.param(
            lambda client: client.store_integration_credential("datadog", {"api_key": "x"}),
            id="store-credential",
        ),
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


def test_a_credential_never_reaches_the_deployments_access_log(remote: RemoteClient) -> None:
    # Refused rather than sent, but the refusal must still not be the place a
    # secret ends up: it is raised before any request is built.
    with pytest.raises(UnavailableError) as refusal:
        asyncio.run(remote.store_integration_credential("datadog", {"api_key": "SECRET"}))

    assert "SECRET" not in str(refusal.value)
