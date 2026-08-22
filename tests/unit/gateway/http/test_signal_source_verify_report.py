"""What a deep verify of a signal source puts in front of an operator.

The route was built for Proxmox's privilege report and is deliberately untyped
at the transport: each verifier answers the question its own vendor can be
asked. These assertions are that a *signal source's* answer — is there anything
in the store, and does its clock agree with ours — survives the trip unflattened,
because a screen cannot render a finding the route dropped.

The verifier under test is the real one, driven through the real credential
proxy, so a rename inside ``VerificationReport.to_record`` fails here rather
than on a screen.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.signals import (
    SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
    VERIFY_WINDOW_MINUTES,
)
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations._catalogue.discovery import catalogue
from integrations._verification.framework import runner_for
from integrations.registry import credential_schemas
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.vault import Vault
from platform.identity.permissions import Role
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

INTEGRATION = "prometheus"
SCOPE = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
CONTEXT = RequestContext(org_id=ORG, team_id=TEAM_PAYMENTS, capability="deep_verify")

#: The instant the platform believes it is. Pinned, because the skew this route
#: reports is a subtraction against it.
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

#: How far ahead the scripted Prometheus's clock is. Comfortably past the
#: tolerance, so the assertion is about the reporting rather than about rounding.
DRIFT_SECONDS = SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS + 90


def _rfc1123(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")


class SkewedPrometheus:
    """A Prometheus holding series, whose clock is ahead of the platform's."""

    def __init__(self, *, series: int, skew_seconds: float) -> None:
        self._series = series
        self._skew = skew_seconds

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        payload: object = {"data": {"result": [{"metric": {}} for _ in range(self._series)]}}
        return OutboundResponse(
            200,
            {
                "content-type": "application/json",
                "date": _rfc1123(NOW + timedelta(seconds=self._skew)),
            },
            json.dumps(payload).encode("utf-8"),
        )


async def _deep_verifier(*, series: int, skew_seconds: float):
    """Return a deep verifier running the real Prometheus checks over a script."""
    descriptors = [entry.descriptor for entry in catalogue()]
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    # What the production composition hands the vault: the whole catalogue,
    # minus the address fields, which are configuration rather than credentials.
    schemas = credential_schemas()
    vault = Vault(gateway=gateway, schemas=schemas)
    await vault.store(
        SCOPE,
        CredentialHandle(integration=INTEGRATION, team_id=TEAM_PAYMENTS),
        {"token": "ninjasre-scenario-token-000000"},
    )
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*(found.rule for found in descriptors)),
        sender=SkewedPrometheus(series=series, skew_seconds=skew_seconds),
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: NOW,
    )
    transport = InProcessProxyTransport(create_proxy_app(engine))
    runner = runner_for(descriptors, clock=lambda: NOW)

    async def verify(name: str, team_id: str) -> Mapping[str, Any] | None:
        del team_id
        if name != INTEGRATION:
            return None
        report = await runner.verify(name, transport=transport, context=CONTEXT)
        return report.to_record()

    return verify


async def _client(deployment: Deployment, verifier: Any) -> AsyncClient:
    state: GatewayState = deployment.state
    state.deep_verifier = verifier
    return AsyncClient(
        transport=ASGITransport(app=create_app(state)), base_url="http://gateway.test"
    )


@pytest.fixture
async def manager_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def skewed(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment whose Prometheus holds data and whose clock is wrong."""
    verifier = await _deep_verifier(series=3, skew_seconds=DRIFT_SECONDS)
    async with await _client(deployment, verifier) as http:
        yield http


@pytest.fixture
async def emptied(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment whose Prometheus answers 200 and holds nothing."""
    verifier = await _deep_verifier(series=0, skew_seconds=0.0)
    async with await _client(deployment, verifier) as http:
        yield http


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def test_the_report_carries_what_the_window_read_found(
    skewed: AsyncClient, manager_token: str
) -> None:
    response = await skewed.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
    )

    assert response.status_code == 200
    window = response.json()["report"]["data_window"]
    assert window["state"] == "returned"
    assert window["rows"] == 3
    assert window["window_minutes"] == VERIFY_WINDOW_MINUTES
    assert window["probe"].strip(), "a result with no statement of what was read is unreadable"


async def test_a_skewed_source_reaches_the_caller_as_degraded_with_the_offset(
    skewed: AsyncClient, manager_token: str
) -> None:
    """Acceptance 4, at the surface an operator actually reads."""
    response = await skewed.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
    )

    report = response.json()["report"]
    assert report["degraded"] is True
    assert report["clock"]["state"] == "out_of_tolerance"
    assert report["clock"]["offset_seconds"] == pytest.approx(DRIFT_SECONDS)
    assert report["clock"]["tolerance_seconds"] == SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS
    assert any(f"{DRIFT_SECONDS:.1f}s" in reason for reason in report["degradations"])


async def test_an_empty_store_is_reported_as_a_finding_rather_than_as_a_clean_bill(
    emptied: AsyncClient, manager_token: str
) -> None:
    response = await emptied.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
    )

    report = response.json()["report"]
    assert report["ok"] is False
    assert report["data_window"]["state"] == "empty_window"
    assert report["data_window"]["rows"] == 0
    assert report["data_window"]["advice"].strip(), "an empty window with no advice is a status"
    assert any("holds nothing" in reason for reason in report["degradations"])


async def test_the_connectivity_half_still_says_the_credential_works(
    emptied: AsyncClient, manager_token: str
) -> None:
    """The distinction the whole probe exists for: reachable and useless."""
    response = await emptied.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
    )

    report = response.json()["report"]
    assert report["connectivity"]["reachable"] is True
    assert report["missing_permissions"] == []
    assert report["ok"] is False
