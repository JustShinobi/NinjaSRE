"""Starting an investigation and handing it to the background, from any trigger.

Shared by ``routes/investigations.py`` (an operator's request) and
``gateway/webhooks/router.py`` (an alert). Both need the same two guarantees:
the run's identity exists — recorded — before the caller is told about it, and
the investigation itself never blocks the response that reports it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from config.constants.runs import RUN_METADATA_TEAM
from gateway.http.services import InvestigationRunner, InvestigationStart
from gateway.http.state import GatewayState
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RunRecorder


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
) -> str:
    """Record the run beginning, launch it in the background, and return its id.

    Returns as soon as the row exists — ``RunRecorder.start_run`` is one write
    — so a caller (a route, a webhook) can respond immediately (acceptance
    scenario 1) while the investigation itself runs after the response has
    gone out.
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
