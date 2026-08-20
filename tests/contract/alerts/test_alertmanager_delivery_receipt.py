"""What the Alertmanager delivery path needs beyond the five claims
``test_alertmanager_delivery_contract.py`` already proves, plus the
end-to-end proof that a real delivery's receipt is now actually recorded.

Four things live here, none of them duplicating the five claims that file
already covers:

1. A refusal through the delivery-token path is checked against the transit
   ledger, not only the wire. What is found here is a real gap, not a
   confirmation: on a deployment with no shared-secret route configured for
   the path — which both real serving entry points
   (``gateway/http/asgi.py:application`` and ``gateway/http/serve.py``) are —
   ``gateway/webhooks/router.py``'s ``_ledger_refusal`` has nobody to
   attribute the row to and writes nothing durable, only a log line. Both
   tests below prove today's real behaviour, deliberately, rather than
   asserting a durable record as though it already existed.
2. "Duplicate" is a claim about the investigation, not only about the
   incident: an identical redelivery must start no *second investigation*,
   counted directly against what the investigator was asked to do, rather
   than inferred from the incident count staying flat.
3. Wiring a real delivery's ``incident_id``, ``alert_labels`` and
   ``credential_name`` through to
   ``platform.incidents.lifecycle.IncidentLifecycle.record_alert_received``
   (via ``gateway/http/orchestration.py``) is proved end to end: a real
   token, issued through the real service, drives a real delivery, and the
   incident it opens carries a receipt naming the token's own display name
   and the labels that arrived.
4. The same delivery's *entire* stored record — every timeline entry, the
   incident row itself, and the transit ledger's row and sample — is swept
   for the token's actual secret value, not only the one field it is
   supposed to be absent from.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Permission, Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.incident_store import TimelineKind
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.transit_ledger import TransitQuery
from tests.contract.alerts.fixtures_alertmanager_delivery import (
    ALERTMANAGER_FIRING_GROUPED,
    ALERTMANAGER_FIRING_GROUPED_RETRY,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    tokens: TokenService
    runner: FakeInvestigationRunner


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """A deployment reachable only by a delivery token, the same shape the
    Alertmanager delivery contract tests use — see that file for why: nothing
    is wired ahead of time that would stand in for the shared-secret receivers
    this feature does not touch.
    """
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS, kind=ConfigNodeKind.TEAM, name=TEAM_PAYMENTS, parent_id=ORG
            )
        )
    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Deployment(client=client, gateway=gateway, tokens=tokens, runner=runner)


async def _delivery_token(
    deployment: Deployment, *, user_id: str = "alertmanager"
) -> tuple[str, str]:
    """Return ``(token_id, secret)`` for a token scoped to exactly the delivery permission."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    async with deployment.gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=f"{user_id}@acme.test", display_name=user_id)
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=f"grant-{user_id}",
                user_id=user_id,
                role=Role.RESPONDER.value,
                node_id=TEAM_PAYMENTS,
            )
        )
    issued = await deployment.tokens.issue(
        scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=user_id),
        user_id=user_id,
        name=f"{user_id}-delivery-token",
        node_id=TEAM_PAYMENTS,
        permissions=(Permission.WEBHOOK_DELIVER,),
    )
    return issued.token.token_id, issued.secret


async def _deliver(deployment: Deployment, payload: Mapping[str, Any], *, token: str | None) -> Any:
    """POST ``payload`` to the real Alertmanager intake path, unmodified."""
    body = json.dumps(dict(payload)).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await deployment.client.post("/webhooks/alertmanager", content=body, headers=headers)


async def _rows(deployment: Deployment) -> tuple[Any, ...]:
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        return await uow.transit.deliveries(TransitQuery())


def _leak_scan(obj: object, *, secret: str) -> bool:
    """Return whether ``secret`` appears anywhere on ``obj``'s own fields.

    Every string field is checked directly, and every string-keyed mapping
    field has its values checked too — so a field added later to any of the
    record types this is run against stays covered without this scan being
    updated by hand.
    """
    for entry_field in dataclasses.fields(obj):
        value = getattr(obj, entry_field.name)
        if isinstance(value, str) and secret in value:
            return True
        if isinstance(value, Mapping) and any(
            isinstance(item, str) and secret in item for item in value.values()
        ):
            return True
    return False


# --- What a refusal actually leaves behind, on the delivery-token path -----------
#
# A refused delivery is supposed to be recorded with the reason for the
# refusal, durably, not only as a log line. ``gateway/webhooks/router.py``'s
# ``_ledger_refusal`` writes that record against the *first configured
# route*'s tenant — and when the delivery-token path is the only verifier a
# deployment has (both real serving entry points call
# ``create_app``/``build_state`` with no ``webhook_routes`` at all:
# ``gateway/http/asgi.py:253`` and ``gateway/http/serve.py:170``), there is no
# configured route to attribute the row to, and the function returns without
# writing one. Both tests below prove today's real behaviour — a log line, no
# durable row — rather than assert a durable record as though it already
# existed. Reported as a finding, not fixed here: see the slice report.


async def test_a_missing_tokens_refusal_leaves_no_ledger_row_on_a_token_only_deployment(
    deployment: Deployment,
) -> None:
    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=None)
    assert response.status_code == 401, response.text

    rows = await _rows(deployment)
    assert rows == (), rows


async def test_a_revoked_tokens_refusal_leaves_no_ledger_row_on_a_token_only_deployment(
    deployment: Deployment,
) -> None:
    """A separate test from the missing-token one above, proving the same gap
    holds for revocation specifically, not merely for absence.
    """
    token_id, secret = await _delivery_token(deployment)
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    was_live = await deployment.tokens.revoke(
        scope, AuditContext(actor_kind=ActorKind.USER, actor_id="operator"), token_id
    )
    assert was_live  # precondition: the token really was live before this revoked it

    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert response.status_code == 401, response.text

    rows = await _rows(deployment)
    assert rows == (), rows


# --- No second investigation, counted directly against the investigator ---------


async def test_an_identical_redelivery_starts_no_second_investigation(
    deployment: Deployment,
) -> None:
    """The delivery contract file proves the incident count does not move.
    This proves the stronger, more literal claim: the investigator itself was
    asked to investigate exactly once, counted directly rather than inferred.
    """
    _, secret = await _delivery_token(deployment)

    first = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert first.status_code == 202, first.text
    assert len(deployment.runner.started) == 1, deployment.runner.started

    second = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED_RETRY, token=secret)

    assert second.status_code == 202, second.text
    assert second.json().get("duplicate_delivery") is True
    assert len(deployment.runner.started) == 1, deployment.runner.started


# --- The receipt wiring: a real delivery now produces a real receipt -------------


async def test_a_real_delivery_records_a_receipt_naming_the_credential_and_the_labels(
    deployment: Deployment,
) -> None:
    """Before this slice, ``InvestigationStart`` always reached the
    investigator with ``incident_id``/``alert_labels``/``credential_name`` all
    empty, and nothing ever wrote the receipt
    ``platform.incidents.lifecycle.IncidentLifecycle.record_alert_received``
    was already able to record (built, and structurally guarded, the slice
    before this one). This is what a real delivery produces now that
    ``gateway/http/orchestration.py`` populates and records them.
    """
    token_id, secret = await _delivery_token(deployment, user_id="alertmanager")

    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert response.status_code == 202, response.text
    incident_id = response.json()["incident_id"]

    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        timeline = await uow.incidents.timeline(incident_id)
        token_name = next(
            token.name
            for token in await uow.identity.tokens_for_user("alertmanager")
            if token.token_id == token_id
        )

    receipts = [entry for entry in timeline if entry.kind is TimelineKind.ALERT_RECEIVED]
    assert len(receipts) == 1, timeline
    receipt = receipts[0]
    assert token_name in receipt.cause
    assert "alertname=InstanceDown" in receipt.detail

    # The same three values also reached the InvestigationStart the composed
    # investigator received — proving the seam `gateway/runtime` reads from is
    # fed correctly too, even though this fixture's fake investigator does not
    # itself write anything (only a runner composed with `incidents=` does).
    started = deployment.runner.started[0]
    assert started.incident_id == incident_id
    assert started.credential_name == token_name
    assert started.alert_labels.get("alertname") == "InstanceDown"


async def test_the_stored_record_never_carries_the_delivery_tokens_secret_value(
    deployment: Deployment,
) -> None:
    """Sweeps the *entire* stored record produced by one real delivery, not
    only the field the secret value is supposed to be absent from: every
    timeline entry, the incident row itself, the transit ledger's row, and its
    masked sample.
    """
    _, secret = await _delivery_token(deployment)

    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert response.status_code == 202, response.text
    incident_id = response.json()["incident_id"]

    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        timeline = await uow.incidents.timeline(incident_id)
        incident = await uow.incidents.get(incident_id)
        rows = await uow.transit.deliveries(TransitQuery())
        sample = await uow.transit.sample("alertmanager")

    assert incident is not None
    assert not _leak_scan(incident, secret=secret)
    for entry in timeline:
        assert not _leak_scan(entry, secret=secret), entry
    for row in rows:
        assert not _leak_scan(row, secret=secret), row
    assert sample is not None
    assert not _leak_scan(sample, secret=secret), sample
    # Not vacuous: the fixture's own token secret is a real, high-entropy
    # value this scan would find if anything above put it somewhere it
    # should not be.
    assert len(secret) > 20


__all__: list[str] = []
