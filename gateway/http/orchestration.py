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
from platform.guardrails.engine import GuardrailEngine
from platform.incidents.lifecycle import IncidentLifecycle
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.headline import headline_for, report_body, resource_from_labels
from platform.runs.recorder import RunRecorder


def _utc_now() -> datetime:
    return datetime.now(UTC)


def redact_text(text: str, guardrails: GuardrailEngine) -> str:
    """Return ``text`` with anything the ruleset matches already removed.

    Computed once, here, and then used for **every** consumer of an
    objective or a label this function reaches — the provisional headline,
    the row ``start_run`` writes, the incident timeline (``attach_run``,
    ``record_alert_received``), and the ``InvestigationStart`` the runtime
    actually reasons over. A caller that sanitised only the value it passed
    to ``start_run`` and then reused the raw parameter for anything else
    would have redacted the row and leaked everywhere else the same text
    goes — which is exactly the shape convergence found here: the runtime's
    own prompt and the incident's timeline were both still reading the raw
    parameter after this function had already computed a clean one.
    Exported so ``gateway/webhooks/router.py`` — which builds its own
    incident-timeline entry from the same untrusted alert data, in a
    second, redundant ``attach_run`` call this module's docstring already
    explains — redacts with the identical rule rather than a second
    hand-rolled pass.
    """
    if not text:
        return text
    return guardrails.scan(text).text


def redact_labels(labels: Mapping[str, str], guardrails: GuardrailEngine) -> dict[str, str]:
    """Return ``labels`` with every value scanned, for the same reason as ``redact_text``."""
    return {key: redact_text(value, guardrails) for key, value in labels.items()}


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
    sanitized_objective = redact_text(objective, state.guardrails)
    sanitized_labels = redact_labels(alert_labels or {}, state.guardrails)
    async with state.gateway.begin(scope) as uow:
        if not team_node_id:
            # A local sign-in issues a token that stands for the person across
            # the whole organisation rather than for one team of it, so an
            # operator starting an investigation from the console arrives here
            # with no team at all. Nothing downstream could tell that apart
            # from "this run belongs to nobody", and the one mechanism that
            # acts on it — episodic memory — correctly refuses to write an
            # episode it cannot scope, because an unscoped episode is one
            # every team can retrieve. The result was fifty finished
            # investigations, an empty corpus, and a screen saying none had
            # ended.
            #
            # The root is the honest answer rather than a guess: it is the one
            # node a deployment with any configuration at all is certain to
            # have, and it is the same node the console falls back to when
            # nothing more specific is named. It also cannot hide a run from
            # anybody — an organisation-wide caller sees every run whatever
            # team it carries (`routes/tenancy.py`), and a team-scoped caller
            # could never see an unstamped one in the first place. So this
            # only ever reveals a run to the team it actually belongs to.
            team_node_id = (await uow.config.root()).node_id
        recorder = RunRecorder(
            store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
        )
        run = await recorder.start_run(
            trigger=trigger,
            principal_id=principal_id,
            team_node_id=team_node_id,
            alert_id=alert_id,
            objective=sanitized_objective,
            alert_labels=sanitized_labels,
            metadata={RUN_METADATA_TEAM: team_node_id},
        )
        if incident_id:
            # Attached in the same transaction that reserves the run's
            # identity, so "this run exists" and "this incident points at it"
            # become true together. Attaching afterwards leaves a window in
            # which the incident is under investigation and nothing can tell:
            # a second alert on the same subject looks for a live run to join,
            # finds none, and starts its own. The burst that motivated the
            # joining rule arrived three deliveries inside eighty-two
            # milliseconds, which is well inside a window like that.
            #
            # Idempotent in the run, so the caller that also attaches — the
            # webhook router, which does it to record the objective on the
            # timeline — is not a second link.
            lifecycle = IncidentLifecycle(store=uow.incidents)
            await lifecycle.attach_run(
                incident_id, run.run_id, objective=sanitized_objective, now=_utc_now()
            )
            if credential_name:
                await lifecycle.record_alert_received(
                    incident_id,
                    labels=sanitized_labels,
                    credential_name=credential_name,
                    now=_utc_now(),
                )

    task = asyncio.create_task(
        _drive(
            state,
            scope=scope,
            request=InvestigationStart(
                run_id=run.run_id,
                objective=sanitized_objective,
                team_node_id=team_node_id,
                principal_id=principal_id,
                org_id=scope.org_id,
                alert_source=alert_source,
                context=dict(context or {}),
                incident_id=incident_id,
                alert_labels=dict(sanitized_labels),
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
        # Extracted from what the model wrote when it followed the delivery
        # prompt's instruction; synthesised from the run's own subject —
        # never from ``summary`` — when it did not.
        headline = headline_for(
            summary,
            alert_name=request.alert_labels.get("alertname", ""),
            resource=resource_from_labels(request.alert_labels),
            objective=request.objective,
        )
        # The marker line is spent by the extraction above, so it does not
        # travel on into the document. Leaving it there gave every report a
        # last paragraph repeating the heading the page already carried.
        summary = report_body(summary)
        async with state.gateway.begin(scope) as uow:
            recorder = RunRecorder(
                store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
            )
            await recorder.complete_run(
                request.run_id, status=status, summary=summary, headline=headline
            )


__all__ = ["redact_labels", "redact_text", "start_investigation"]
