"""Starting an investigation and handing it to the background, from any trigger.

Shared by ``routes/investigations.py`` (an operator's request) and
``gateway/webhooks/router.py`` (an alert). Both need the same two guarantees:
the run's identity exists — recorded — before the caller is told about it, and
the investigation itself never blocks the response that reports it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

from config.constants.runs import RUN_METADATA_TEAM
from gateway.http.services import InvestigationRunner, InvestigationStart
from gateway.http.state import GatewayState
from platform.incidents.lifecycle import IncidentLifecycle
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RunRecorder


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def start_investigation(
    state: GatewayState,
    *,
    scope: TenantScope,
    trigger: str,
    objective: str,
    principal_id: str,
    alert_source: str = "",
    alert_id: str | None = None,
    context: Mapping[str, str] | None = None,
    incident_id: str = "",
    alert_labels: Mapping[str, str] | None = None,
    credential_name: str = "",
) -> str:
    """Record the run beginning, launch it in the background, and return its id.

    Returns as soon as the row exists — ``RunRecorder.start_run`` is one write
    — so a caller (a route, a webhook) can respond immediately (acceptance
    scenario 1) while the investigation itself runs after the response has
    gone out.

    ``incident_id``, ``alert_labels`` and ``credential_name`` are empty by
    default: an operator-triggered investigation (``routes/investigations.py``)
    has no incident to attach a receipt to and no delivery to name. A caller
    that names both an incident and a delivery credential (``gateway/webhooks/
    router.py``, once a delivery has raised the incident) gets the alert's
    receipt recorded on that incident's timeline in the same transaction that
    reserves the run's identity — before the response goes out, and without
    holding a transaction open for the investigation itself, which can run far
    longer than one write. The same three values also ride on the
    ``InvestigationStart`` handed to the investigator, so a runner composed
    with somewhere to record reasoning through (``gateway/runtime``) sees them
    too; only one of the two should ever be wired to actually write the
    receipt at a time, or the entry would be recorded twice.
    """
    team_node_id = scope.team_node_id or ""
    async with state.gateway.begin(scope) as uow:
        recorder = RunRecorder(
            store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
        )
        run = await recorder.start_run(
            trigger=trigger,
            principal_id=principal_id,
            team_node_id=team_node_id,
            alert_id=alert_id,
            metadata={RUN_METADATA_TEAM: team_node_id},
        )
        if incident_id and credential_name:
            await IncidentLifecycle(store=uow.incidents).record_alert_received(
                incident_id,
                labels=alert_labels or {},
                credential_name=credential_name,
                now=_utc_now(),
            )

    task = asyncio.create_task(
        _drive(
            state,
            scope=scope,
            request=InvestigationStart(
                run_id=run.run_id,
                objective=objective,
                team_node_id=team_node_id,
                principal_id=principal_id,
                alert_source=alert_source,
                context=dict(context or {}),
                incident_id=incident_id,
                alert_labels=dict(alert_labels or {}),
                credential_name=credential_name,
            ),
        ),
        name=run.run_id,
    )
    state.track(task)
    return run.run_id


async def _drive(state: GatewayState, *, scope: TenantScope, request: InvestigationStart) -> None:
    """Run the investigation to completion and close the run, whatever happened.

    A fresh unit of work — not the one ``start_investigation`` used — because
    this coroutine outlives the request that scheduled it.
    """
    investigator: InvestigationRunner = state.investigator
    try:
        summary = await investigator.investigate(request)
        status = RunStatus.COMPLETED
    except asyncio.CancelledError:
        status = RunStatus.CANCELLED
        summary = "cancelled"
        raise
    except Exception as error:  # noqa: BLE001 — recorded as the run's own failure, then swallowed
        status = RunStatus.FAILED
        summary = f"{type(error).__name__}: {error}"
    finally:
        async with state.gateway.begin(scope) as uow:
            recorder = RunRecorder(
                store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
            )
            await recorder.complete_run(request.run_id, status=status, summary=summary)


__all__ = ["start_investigation"]
