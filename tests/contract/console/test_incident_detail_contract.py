"""The incident detail contract this feature has to grow into.

``GET /v1/incidents/{id}`` is what the console's incident page reads. Once an
investigation has run against an incident, this feature says the response
must carry three things: the timeline holds all five kinds a reasoning step
may be (recebimento, hipóteses, evidência, diagnóstico, entrega); each
evidence step names the query that was actually run and the result it
returned; and the investigation is summarised by how many steps it took, how
long it ran and what it cost.

All three now exist. ``TimelineKind``
(``platform/persistence/ports/incident_store.py``) declares the five
reasoning kinds beside the ten lifecycle ones, on the same enum rather than a
parallel one, and ``TimelineEntry`` carries ``query``/``result`` alongside
``cause``/``detail``. The route mirrors both: ``TimelineEntryView`` — the
model ``gateway/http/routes/incidents.py`` serialises every timeline entry
through — carries ``query``/``result``, and ``IncidentDetailView`` carries an
investigation summary. The first claim below is still proved by appending
reasoning-kind entries straight through the store — the same seam the
demonstration seeder writes through — rather than through an investigation
runtime, which does not record one on its own yet either; that choice did not
change when the route did.

The five spellings below (``alert_received``, ``hypotheses_drawn``,
``evidence``, ``diagnosis``, ``report_delivered``) are the ones the real
``TimelineKind`` members now carry — the same spelling this file chose before
the enum existed, matched rather than renegotiated, the same way a screen
built against an acceptance spec is expected to make its assertions pass
rather than have them rewritten from nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.runs import TRIGGER_ALERT, TURN_USAGE_COST
from gateway.http.app import create_app
from gateway.http.routes.incidents import TimelineEntryView
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.incident_store import (
    SYSTEM_ACTOR,
    IncidentOrigin,
    IncidentSubject,
    TimelineEntry,
    TimelineKind,
    timeline_key,
)
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, TurnRecord
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
    """Raise an incident, attach a run, and give it a full reasoning timeline.

    A real origin, a real severity, a real run attached, the incident moved to
    ``investigating``, and — now that ``TimelineKind`` carries them — one
    entry of each of the five reasoning kinds. Appended straight through the
    store rather than through ``IncidentLifecycle``, because the lifecycle has
    no method yet that records a hypothesis or a piece of evidence; that is a
    later phase's job, not this one's. The store does not care who calls it,
    which is exactly what lets this helper prove the first claim below
    without waiting for the phase that adds that caller.
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
        await uow.incidents.append(_reasoning_timeline(incident.incident_id, now))
    return incident.incident_id


def _reasoning_timeline(incident_id: str, started_at: datetime) -> tuple[TimelineEntry, ...]:
    """Return one entry of each of the five reasoning kinds, in the order an investigation produces them.

    Only the evidence step carries a query and a result — every other kind
    leaves them empty, the same as every lifecycle entry always has.
    """
    # kind, cause, detail, query, result
    steps: tuple[tuple[TimelineKind, str, str, str, str], ...] = (
        (
            TimelineKind.ALERT_RECEIVED,
            "InstanceDown fired for cedar, delivered by the cluster's Alertmanager",
            "delivery token am-cluster",
            "",
            "",
        ),
        (
            TimelineKind.HYPOTHESES_DRAWN,
            "considered before any integration was queried",
            "node reboot; network partition between zones; probe agent crashed",
            "",
            "",
        ),
        (
            TimelineKind.EVIDENCE,
            "cedar has not answered its own probe in 6 minutes",
            "",
            'up{instance="cedar"}',
            "0 (last seen 1 at 06:41 UTC, 6m ago)",
        ),
        (
            TimelineKind.DIAGNOSIS,
            "cedar is down: it stopped responding to its own probe and has not recovered",
            "",
            "",
            "",
        ),
        (
            TimelineKind.REPORT_DELIVERED,
            "report delivered",
            "#incidents, oncall@example.test",
            "",
            "",
        ),
    )
    return tuple(
        TimelineEntry(
            entry_id=timeline_key(incident_id, kind, started_at + timedelta(minutes=index + 1)),
            incident_id=incident_id,
            kind=kind,
            at=started_at + timedelta(minutes=index + 1),
            actor=SYSTEM_ACTOR,
            cause=cause,
            detail=detail,
            query=query,
            result=result,
        )
        for index, (kind, cause, detail, query, result) in enumerate(steps)
    )


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
    """The one level this test can prove the claim at.

    The live half of the claim — a real evidence step, in a real response,
    carrying a non-empty query and result — still needs a timeline entry of a
    kind that cannot be produced through a real investigation yet, exactly as
    in the test above; asserting it here would either explode on a malformed
    ``TimelineEntry`` (a red for the wrong reason) or pass vacuously over an
    empty list (no red at all, dressed up as one). Neither would prove
    anything. What this test proves instead is the schema itself:
    ``TimelineEntryView`` now carries a field for each, for every entry — not
    only for the one chosen by hand.
    """
    fields = set(TimelineEntryView.model_fields)
    missing = {"query", "result"} - fields
    assert not missing, f"TimelineEntryView cannot carry {sorted(missing)}; it has {sorted(fields)}"


# --- Claim: the investigation's step count, duration and cost ---------------------


async def test_the_response_carries_the_investigations_step_count_duration_and_cost(
    deployment: Deployment,
) -> None:
    """Legible next to the incident, not on a second screen.

    ``IncidentDetailView`` now carries an investigation summary, and the
    three per-field checks below exercise it against a real incident with a
    real run attached: step count, duration, and cost.
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


async def test_the_summary_says_whether_the_run_is_still_going(
    deployment: Deployment,
) -> None:
    """The run's own status, so no screen has to infer it from what is missing.

    The console decided "still running" by looking for a delivery step in the
    incident's timeline and finding none. A completed run that delivered
    nowhere therefore read as running for as long as the incident existed —
    and was drawn beside a state chip saying the incident had been resolved
    two hours earlier. Two chips, one header, opposite claims.

    A run id attached with no trace row behind it yet is the one case that
    answers nothing, and it answers with the empty string rather than a
    plausible word: the screen has to be able to say "not known" there, and it
    cannot if this route has already guessed on its behalf.
    """
    started = datetime.now(UTC)
    incident_id = await _incident_with_a_traced_run(
        deployment,
        run_id="run-status",
        started_at=started,
        finished_at=started + timedelta(seconds=5),
        turns=(TurnRecord(turn_id="turn-1", run_id="run-status", index=1),),
    )

    body = await _detail(deployment, incident_id)

    investigation = body["investigation"]
    assert "status" in investigation, (
        f"investigation summary cannot say whether the run is over; has {sorted(investigation)}"
    )
    assert investigation["status"] == RunStatus.RUNNING.value, (
        f"the summary did not report the run's own status: {investigation}"
    )


async def test_a_run_with_no_trace_row_reports_no_status_rather_than_a_guess(
    deployment: Deployment,
) -> None:
    """An attached run id whose trace has not appeared yet says nothing.

    This is the moment right after ``attach_run``, and the honest answer is
    that nobody knows where the run got to. Reporting "completed" would age
    into a lie the moment the run finished; reporting "running" would be a
    claim about a process this route cannot see.
    """
    incident_id = await _investigated_incident(deployment)

    body = await _detail(deployment, incident_id)

    assert body["investigation"]["status"] == "", (
        f"a run with no trace row was given a status anyway: {body['investigation']}"
    )


# --- Claim: an incident nothing has ever investigated has no summary --------------


async def _bare_incident(deployment: Deployment, correlation_key: str) -> str:
    """Raise an incident and return its id, without ever attaching a run."""
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key=correlation_key,
                title="a probe failed",
                summary="the blackbox probe has failed",
                origin=IncidentOrigin.ALERT,
                origin_id="InstanceDown",
                severity="critical",
                subjects=(
                    IncidentSubject(
                        resource_id="birch", detail="the blackbox probe has failed", observed_at=now
                    ),
                ),
                team_node_id=TEAM_PAYMENTS,
                cause="InstanceDown fired for birch",
            ),
            now=now,
        )
    return incident.incident_id


async def test_an_incident_with_no_run_attached_has_no_investigation_summary(
    deployment: Deployment,
) -> None:
    """The mirror of the claim above: the field exists, and here its value is
    ``None`` — a real absence, not an object full of absent numbers. Nothing
    has ever investigated this incident, so there is nothing to summarise.
    """
    incident_id = await _bare_incident(deployment, "alert:InstanceDown:birch")

    body = await _detail(deployment, incident_id)

    assert "investigation" in body, f"top-level keys are {sorted(body)}"
    assert body["investigation"] is None, (
        f"an incident with no run attached must summarise to nothing, got {body['investigation']!r}"
    )


# --- Claim: an unknown duration or cost is omitted, never a fabricated zero -------


async def _incident_with_a_traced_run(
    deployment: Deployment,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime | None,
    turns: tuple[TurnRecord, ...],
) -> str:
    """Raise an incident, attach ``run_id``, and record its trace directly.

    ``started_at``/``finished_at`` are the caller's, not derived from the
    instant this helper happens to run at — a duration assertion has to be
    exact, and deriving both ends from ``datetime.now()`` calls made
    microseconds apart would make it a coin flip on a slow machine.

    Two independent stores, written the same way production eventually will:
    the incident links to the run, and the run's own turns land in the trace
    store. Through ``run_traces`` directly rather than a real investigation
    runtime, for the same reason the module docstring gives for the timeline
    entries above — no runtime records one on its own yet either.
    """
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key=f"alert:InstanceDown:{run_id}",
                title="a probe failed",
                summary="the blackbox probe has failed",
                origin=IncidentOrigin.ALERT,
                origin_id="InstanceDown",
                severity="critical",
                subjects=(
                    IncidentSubject(
                        resource_id=run_id, detail="the blackbox probe has failed", observed_at=now
                    ),
                ),
                team_node_id=TEAM_PAYMENTS,
                cause="InstanceDown fired",
            ),
            now=now,
        )
        await lifecycle.attach_run(incident.incident_id, run_id, objective="diagnose", now=now)
        await uow.run_traces.start_run(
            AgentRun(
                run_id=run_id, trigger=TRIGGER_ALERT, started_at=started_at, finished_at=finished_at
            )
        )
        for turn in turns:
            await uow.run_traces.record_turn(turn)
    return incident.incident_id


async def test_duration_and_cost_are_omitted_not_zeroed_while_a_run_has_no_price_or_end(
    deployment: Deployment,
) -> None:
    """A run still going, whose turns carry no priced figure at all.

    ``step_count`` is a real, non-zero count — the two turns genuinely
    happened. ``duration_ms`` and ``cost`` are the two numbers this run
    cannot yet honestly report, and the claim is that they come back absent
    (``None``, JSON ``null``) rather than as ``0`` — the exact confusion a
    fabricated zero would create for an operator reading the header.
    """
    incident_id = await _incident_with_a_traced_run(
        deployment,
        run_id="run-omitted",
        started_at=datetime.now(UTC),
        finished_at=None,
        turns=(
            TurnRecord(turn_id="turn-1", run_id="run-omitted", index=0, usage={}),
            TurnRecord(turn_id="turn-2", run_id="run-omitted", index=1, usage={}),
        ),
    )

    body = await _detail(deployment, incident_id)

    investigation = body["investigation"]
    assert investigation is not None, "a run with two recorded turns must summarise to something"
    assert investigation["step_count"] == 2, investigation
    assert investigation["duration_ms"] is None, (
        f"a run with no finished_at must omit duration, not zero it: {investigation}"
    )
    assert investigation["cost"] is None, (
        f"turns that carry no priced figure must omit cost, not zero it: {investigation}"
    )


async def test_a_run_priced_at_exactly_zero_and_finished_reports_real_numbers_not_absence(
    deployment: Deployment,
) -> None:
    """The other half of the same claim: a real zero must survive as one.

    A finished run has a real duration, and a turn genuinely priced at
    ``0.0`` is a fact, not a missing figure — collapsing it into ``None``
    would be exactly as dishonest as fabricating a zero for a run that never
    reported a price at all.
    """
    started = datetime.now(UTC)
    incident_id = await _incident_with_a_traced_run(
        deployment,
        run_id="run-priced",
        started_at=started,
        finished_at=started + timedelta(seconds=5),
        turns=(
            TurnRecord(
                turn_id="turn-1", run_id="run-priced", index=0, usage={TURN_USAGE_COST: 0.0}
            ),
        ),
    )

    body = await _detail(deployment, incident_id)

    investigation = body["investigation"]
    assert investigation is not None
    assert investigation["duration_ms"] == 5000, (
        f"a finished run has a real duration, not an absent one: {investigation}"
    )
    assert investigation["cost"] == 0.0, (
        f"a turn priced at exactly zero is a real zero, not an absent cost: {investigation}"
    )


__all__: list[str] = []
