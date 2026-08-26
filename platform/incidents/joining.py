"""Whether a new incident joins an investigation already looking at its subject.

One shutdown of one container opened five incidents here and ran five
investigations. None of the five knew the other four existed, all five spent a
full model budget, and four of them reached the same wrong answer independently
— which is what five isolated views of one failure produces.

**The relation is a shared subject, not a shared arrival.** Of those five, four
resolved to the same estate resource and the fifth resolved to a different one
and was four days old. It arrived inside the same minute as the rest, so a rule
keyed on "these came in together" would have folded it in and taught the
investigation something false. Alert resolution already recorded what each
incident is about, before any of this runs; that recording is the relation.

**And deliberately not a shared parent.** ``platform.incidents.correlation``
opens by naming the risk this module inherits — grouping too aggressively hides
a second cause — and two conditions on one node are two problems with two
answers. A guest and the node under it are related in the estate and are not
the same incident.

**Joining is not merging.** The incidents stay separate, each with its own
correlation key, its own timeline, and its own state. What is shared is the
investigation: the arriving incident is attached to the run already in flight
and its alert is handed to that run as more evidence. Five incidents, one
investigation, five symptoms in front of it instead of one.

When there is nothing live to join — the run finished, the incident that
started it is closed, the subject is somebody else's — this returns ``None``
and the caller investigates as it always did. A message queued for a run nobody
is driving would be delivered at a turn boundary that never comes, and an
incident left silent because of it is worse than an incident investigated
twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.surfaces import ALERT_DEDUP_WINDOW_SECONDS
from platform.persistence.ports.incident_store import Incident, IncidentQuery, IncidentStore
from platform.persistence.ports.run_trace_store import RunStatus, RunTraceStore

#: The run states that can still take more evidence. The same pair the reaper
#: treats as unfinished, named from there rather than restated: a run this
#: module thought was live and the reaper thought was abandoned would be an
#: alert handed to nobody.
LIVE_RUN_STATES: tuple[RunStatus, ...] = (RunStatus.RUNNING, RunStatus.SUSPENDED)


@dataclass(frozen=True, slots=True)
class JoinTarget:
    """The investigation an arriving incident should join, and whose it is."""

    run_id: str
    #: The incident that started it. Named so the arriving incident's timeline
    #: can say which one it joined rather than only that it joined something.
    incident_id: str
    #: What the two have in common, as the estate identifies it. The whole of
    #: the reason, in the form an operator can check.
    subject_id: str


async def investigation_to_join(
    incident: Incident,
    *,
    incidents: IncidentStore,
    runs: RunTraceStore,
    now: datetime,
    window: timedelta = timedelta(seconds=ALERT_DEDUP_WINDOW_SECONDS),
) -> JoinTarget | None:
    """Return the live investigation ``incident`` shares a subject with, or ``None``.

    ``window`` bounds how stale a run may be and still be joined. It is the
    deduplication window because that is the answer this deployment already
    gives to "how long do two alerts count as one arrival"; a second number
    here would be a second answer to one question.
    """
    for subject_id in incident.subject_ids:
        for candidate in await incidents.query(
            IncidentQuery(subject_id=subject_id, live_only=True)
        ):
            if candidate.incident_id == incident.incident_id:
                continue
            run_id = await _live_run_of(candidate, runs=runs, now=now, window=window)
            if run_id:
                return JoinTarget(
                    run_id=run_id,
                    incident_id=candidate.incident_id,
                    subject_id=subject_id,
                )
    return None


async def _live_run_of(
    incident: Incident,
    *,
    runs: RunTraceStore,
    now: datetime,
    window: timedelta,
) -> str:
    """Return this incident's run that is still going, or the empty string.

    Newest first, because an incident that has been investigated more than once
    is being asked about the investigation happening now.
    """
    for run_id in reversed(incident.run_ids):
        run = await runs.get_run(run_id)
        if run is None or run.status not in LIVE_RUN_STATES:
            continue
        if run.started_at is not None and now - run.started_at > window:
            # Marked running and older than the window is what an abandoned run
            # looks like — the process that was driving it is gone and the
            # reaper has not been round yet. Handing it an alert would be
            # handing it to nobody.
            continue
        return run_id
    return ""


__all__ = ["LIVE_RUN_STATES", "JoinTarget", "investigation_to_join"]
