"""The incident detail contract this feature has to grow into.

``GET /v1/incidents/{id}`` is what the console's incident page reads. Once an
investigation has run against an incident, this feature says the response
must carry three things: the timeline holds all five kinds a reasoning step
may be (recebimento, hipóteses, evidência, diagnóstico, entrega); each
evidence step names the query that was actually run and the result it
returned; and the investigation is summarised by how many steps it took, how
long it ran and what it cost.

None of the three exists yet. ``TimelineKind``
(``platform/persistence/ports/incident_store.py``) declares ten lifecycle
kinds and none of the five reasoning ones; ``TimelineEntryView`` — the model
``gateway/http/routes/incidents.py`` serialises every timeline entry through —
carries no ``query``/``result`` pair; ``IncidentDetailView`` carries no
investigation summary at all. Adding the five kinds is this feature's own
later phase to own, not this one's: a ``TimelineEntry`` built with a ``kind``
that is not a real ``TimelineKind`` member would crash that same route's own
serialisation (``entry.kind.value`` on a plain ``str``) rather than
demonstrate anything about this feature, so this file does not attempt it.

The five spellings named below (``alert_received``, ``hypotheses_drawn``,
``evidence``, ``diagnosis``, ``report_delivered``) are this file's own design
choice, following the existing members' own convention — English,
``lower_snake_case``, naming the moment — not a value copied from any
committed source, because none exists yet. Whoever adds the real enum member
either matches this spelling or updates this set in the same change, the same
way a screen built against an acceptance spec is expected to make its
assertions pass rather than have them rewritten from nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.routes.incidents import TimelineEntryView
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

# No module-level ``pytestmark = pytest.mark.asyncio``: this file mixes async
# HTTP-round-trip tests with one plain sync schema check
# (``test_the_timeline_entry_schema_has_nowhere_to_carry_a_query_or_a_result``),
# and ``pytest.ini``'s ``asyncio_mode = auto`` already collects every
# ``async def test_*`` correctly without it. Applying the mark to the whole
# module marked the sync test too and pytest warned about it for no benefit.

#: This file's own design choice for the five reasoning kinds a later phase
#: has to add to ``TimelineKind`` — see the module docstring for why these
#: exact spellings and not others.
EXPECTED_REASONING_KINDS = frozenset(
    {"alert_received", "hypotheses_drawn", "evidence", "diagnosis", "report_delivered"}
)


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    secret: str


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
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
    secret = await issue_token(
        gateway, tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=FakeInvestigationRunner())
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Deployment(client=client, gateway=gateway, secret=secret)


async def _investigated_incident(deployment: Deployment) -> str:
    """Raise an incident and attach a run to it, using only the lifecycle
    kinds ``TimelineKind`` declares today, and return the incident's id.

    This is the closest state this slice can build to "an incident
    investigated": a real origin, a real severity, a real run attached and the
    incident moved to ``investigating`` — everything except the five
    reasoning steps themselves, which nothing in this deployment can produce
    yet (see the module docstring).
    """
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key="alert:InstanceDown:cedar",
                title="cedar is down",
                summary="the blackbox probe against cedar has failed",
                origin=IncidentOrigin.ALERT,
                origin_id="InstanceDown",
                severity="critical",
                subjects=(
                    IncidentSubject(
                        resource_id="cedar",
                        detail="the blackbox probe against cedar has failed",
                        observed_at=now,
                    ),
                ),
                team_node_id=TEAM_PAYMENTS,
                cause="InstanceDown fired for cedar",
            ),
            now=now,
        )
        await lifecycle.attach_run(
            incident.incident_id, "run-1", objective="diagnose cedar", now=now
        )
    return incident.incident_id


async def _detail(deployment: Deployment, incident_id: str) -> Any:
    """Return the parsed JSON body of the real incident detail route."""
    response = await deployment.client.get(
        f"/v1/incidents/{incident_id}", headers={"Authorization": f"Bearer {deployment.secret}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Claim: the timeline carries the five reasoning step kinds --------------------


async def test_the_timeline_carries_the_five_reasoning_step_kinds(deployment: Deployment) -> None:
    """The state this claim needs is a timeline holding an entry of each of
    the five reasoning kinds; nothing in this deployment can produce that
    state (see the module docstring), so what is provable today is that a
    real, freshly-raised-and-investigated incident's timeline carries none of
    them — only the lifecycle kinds it always has.
    """
    incident_id = await _investigated_incident(deployment)

    body = await _detail(deployment, incident_id)

    observed_kinds = {entry["kind"] for entry in body["timeline"]}
    missing = EXPECTED_REASONING_KINDS - observed_kinds
    assert not missing, (
        f"none of the five reasoning kinds are on the timeline; missing {sorted(missing)}, "
        f"observed only {sorted(observed_kinds)}"
    )


# --- Claim: each evidence step carries the query and the result -------------------


def test_the_timeline_entry_schema_has_nowhere_to_carry_a_query_or_a_result() -> None:
    """At the one level this slice can prove it at.

    The live half of this claim — a real evidence step, in a real response,
    carrying a non-empty query and result — needs a timeline entry of a kind
    that cannot be produced yet, exactly as in the test above; asserting it
    here would either explode on a malformed ``TimelineEntry`` (a red for the
    wrong reason) or pass vacuously over an empty list (no red at all, dressed
    up as one). Neither proves anything. What is provable without touching
    production code is the schema itself: ``TimelineEntryView`` has no field
    to carry either value in the first place, for any entry.
    """
    fields = set(TimelineEntryView.model_fields)
    missing = {"query", "result"} - fields
    assert not missing, f"TimelineEntryView cannot carry {sorted(missing)}; it has {sorted(fields)}"


# --- Claim: the investigation's step count, duration and cost ---------------------


async def test_the_response_carries_the_investigations_step_count_duration_and_cost(
    deployment: Deployment,
) -> None:
    """Legible next to the incident, not on a second screen.

    ``IncidentDetailView`` has no field carrying any of the three today, so
    the first assertion below — that the response has anywhere to carry an
    investigation summary at all — is the one this slice actually proves red.
    The three per-field checks after it name the rest of the claim for
    whoever makes the first assertion pass; they cannot be exercised before
    that, because there is nothing in the response for them to read yet.
    """
    incident_id = await _investigated_incident(deployment)

    body = await _detail(deployment, incident_id)

    assert "investigation" in body, (
        f"no investigation summary on the incident detail response; "
        f"top-level keys are {sorted(body)}"
    )
    investigation = body["investigation"]
    assert investigation is not None, (
        "an incident with an attached run must not summarise to nothing"
    )
    for field_name in ("step_count", "duration_ms", "cost"):
        assert field_name in investigation, (
            f"investigation summary is missing {field_name!r}; has {sorted(investigation)}"
        )


__all__: list[str] = []
