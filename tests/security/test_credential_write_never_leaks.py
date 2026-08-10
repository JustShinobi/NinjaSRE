"""A credential written over HTTP is in the vault, and nowhere a person can read.

The route ``PUT /v1/integrations/{name}/credential`` is the only path a secret
takes into a deployment over the network, so this is the sweep that says it
arrived and stopped. Four places do the writing in this platform — the response
body, the structured log, the audit trail, and an exception's own message — and
all four are swept, over a write that succeeded and a write that was refused.

The sweep looks for the value itself rather than for a shape. A test asserting
"no thirty-two-character hex string" would pass against a log line carrying the
key with a dash in it, and that is not the property Article IV describes.

Field *names* are expected to be present and are asserted for: an operator
reading the trail six months after an incident needs to know which fields were
replaced at 02:00, and a trail that recorded only "something changed" is one
nobody can act on.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import CREDENTIAL_AUDIT_ACTION_WRITE
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    Deployment,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.security

#: The value the sweep looks for. Valid against Datadog's declared format, so
#: the write it is used in is one that actually succeeds — a sweep over a
#: rejected write would prove only that a refusal is quiet.
SENTINEL = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
SENTINEL_APP_KEY = "abcdefghij0123456789ABCDEFGHIJ0123456789"

CREDENTIAL_PATH = "/v1/integrations/datadog/credential"


@pytest.fixture
def captured_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture everything every logger emits, at every level.

    At ``NOTSET``, so a debug line added later is swept too. A sweep that only
    read ``INFO`` would pass the day somebody logged the value while debugging
    why the write did not work.
    """
    with caplog.at_level(logging.NOTSET):
        yield caplog


@pytest.fixture
async def wired() -> AsyncIterator[tuple[AsyncClient, Deployment, str]]:
    """Return the real application, a real operator token, and the store behind them."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )
    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    secret = await issue_token(
        gateway, tokens, user_id="ada", role=Role.OPERATOR, node_id=TEAM_PAYMENTS
    )
    deployment = Deployment(gateway=gateway, tokens=tokens, state=state, runner=runner)
    transport = ASGITransport(app=create_app(state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http, deployment, secret


def _log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Return everything that was logged, message and structured payload alike."""
    parts: list[str] = [caplog.text]
    for record in caplog.records:
        parts.append(str(record.getMessage()))
        parts.append(repr(getattr(record, "__dict__", {})))
    return "\n".join(parts)


async def _audit_events(gateway: FakePersistence) -> list[dict[str, object]]:
    """Return every audit event this deployment recorded, as a query would render it."""
    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        events = await uow.audit.query()
    return [
        {
            "action": event.action,
            "actor_id": event.actor_id,
            "resource_kind": event.resource_kind,
            "resource_id": event.resource_id,
            "detail": dict(event.detail),
        }
        for event in events
    ]


# --- The trail ----------------------------------------------------------------


async def test_the_write_is_audited_with_the_actor_the_integration_and_the_fields(
    wired: tuple[AsyncClient, Deployment, str],
) -> None:
    """A credential replaced during an incident is a fact somebody needs later."""
    http, deployment, secret = wired

    await http.put(
        CREDENTIAL_PATH,
        headers={"Authorization": f"Bearer {secret}"},
        json={"values": {"api_key": SENTINEL, "app_key": SENTINEL_APP_KEY}},
    )

    written = [
        event
        for event in await _audit_events(deployment.gateway)
        if event["action"] == CREDENTIAL_AUDIT_ACTION_WRITE
    ]
    assert len(written) == 1
    entry = written[0]
    assert entry["actor_id"] == "ada"
    assert entry["resource_id"] == "datadog"
    detail = entry["detail"]
    assert isinstance(detail, dict)
    assert detail["integration"] == "datadog"
    assert detail["fields"] == ["api_key", "app_key"]
    assert detail["version"] == 1


async def test_rotating_leaves_the_sequence_in_the_trail(
    wired: tuple[AsyncClient, Deployment, str],
) -> None:
    """Writing again is rotation, and the trail carries the order it happened in."""
    http, deployment, secret = wired
    headers = {"Authorization": f"Bearer {secret}"}

    await http.put(
        CREDENTIAL_PATH,
        headers=headers,
        json={"values": {"api_key": SENTINEL, "app_key": SENTINEL_APP_KEY}},
    )
    await http.put(
        CREDENTIAL_PATH,
        headers=headers,
        json={
            "values": {"api_key": "f0e1d2c3b4a5968778695a4b3c2d1e0f", "app_key": SENTINEL_APP_KEY}
        },
    )

    versions = [
        event["detail"]["version"]  # type: ignore[index]
        for event in await _audit_events(deployment.gateway)
        if event["action"] == CREDENTIAL_AUDIT_ACTION_WRITE
    ]
    # Newest first, which is the order the trail is queried in everywhere else.
    # Asserted as the store serves it rather than sorted, because "the rotation
    # is on top" is the property somebody opening the trail is relying on.
    assert versions == [2, 1]


# --- The sweep ----------------------------------------------------------------


async def test_a_written_credential_appears_in_no_response_no_log_and_no_audit_detail(
    wired: tuple[AsyncClient, Deployment, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    """The whole of Article IV for this route, asserted over everything it produced."""
    http, deployment, secret = wired
    headers = {"Authorization": f"Bearer {secret}"}

    stored = await http.put(
        CREDENTIAL_PATH,
        headers=headers,
        json={"values": {"api_key": SENTINEL, "app_key": SENTINEL_APP_KEY}},
    )
    verified = await http.post("/v1/integrations/datadog/verify", headers=headers)
    listed = await http.get("/v1/integrations", headers=headers)

    swept = "\n".join(
        [
            stored.text,
            verified.text,
            listed.text,
            _log_text(captured_logs),
            json.dumps(await _audit_events(deployment.gateway), default=str),
        ]
    )

    assert stored.status_code == 200
    assert SENTINEL not in swept
    assert SENTINEL_APP_KEY not in swept
    # The names are expected to be there. Asserting it here is what stops the
    # sweep passing because nothing was recorded at all.
    assert "api_key" in swept


async def test_a_refused_write_does_not_become_the_place_the_value_survives(
    wired: tuple[AsyncClient, Deployment, str], captured_logs: pytest.LogCaptureFixture
) -> None:
    """A validation failure names the field it is about and never quotes it."""
    http, deployment, secret = wired

    refused = await http.put(
        CREDENTIAL_PATH,
        headers={"Authorization": f"Bearer {secret}"},
        json={"values": {"api_key": SENTINEL, "app_key": "too-short"}},
    )

    swept = "\n".join(
        [
            refused.text,
            _log_text(captured_logs),
            json.dumps(await _audit_events(deployment.gateway), default=str),
        ]
    )

    assert refused.status_code == 400
    assert "app_key" in refused.text
    assert SENTINEL not in swept
    assert "too-short" not in swept
