"""Registering a sync and a discovery run as scheduled jobs.

Neither store stays useful without a schedule. A wiki that was synced once is a
corpus that describes last quarter; a topology discovered once is a graph that
describes the estate before the last three deploys. So both belong on the
scheduler, and this module is the two job *definitions* — not the running of
them, which is the worker's job and lives with the worker.

The definitions are functions rather than a class because there is no state.
Each returns a ``ScheduledJob`` an operator's configuration or a console can hand
straight to ``ScheduleStore.upsert_job``, with the payload carrying the one thing
the worker cannot infer: which source to run.

Job ids are derived from the kind and the source name, which makes registration
idempotent. Re-registering a Confluence sync replaces the definition rather than
producing a second job that syncs the same space twice a night — and two syncs of
one space racing each other is a corpus where the winner is whichever transaction
committed last.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from config.constants.knowledge import KNOWLEDGE_SYNC_JOB_KIND, TOPOLOGY_DISCOVERY_JOB_KIND
from platform.persistence.ports.schedule_store import ScheduledJob

#: How a job id is built. Deterministic, so registering the same source twice
#: replaces one definition rather than creating a second job racing the first.
JOB_ID = "{kind}:{source}"

#: The payload key naming which adapter a job runs. The scheduler stores an
#: opaque payload; this is the one key both halves have to agree on, so it is
#: named here rather than spelled out at each end.
SOURCE_KEY = "source"


def knowledge_sync_job(
    *,
    source: str,
    schedule: str,
    next_run_at: datetime | None = None,
    enabled: bool = True,
    payload: Mapping[str, Any] | None = None,
) -> ScheduledJob:
    """Return the scheduled job that syncs one document source.

    ``schedule`` is the operator's cron expression, unparsed here — the scheduler
    owns that vocabulary, and a second parser in this module would be a second
    thing to disagree about what "nightly" means.
    """
    return ScheduledJob(
        job_id=JOB_ID.format(kind=KNOWLEDGE_SYNC_JOB_KIND, source=source),
        name=f"Knowledge sync: {source}",
        kind=KNOWLEDGE_SYNC_JOB_KIND,
        schedule=schedule,
        next_run_at=next_run_at,
        enabled=enabled,
        payload={SOURCE_KEY: source, **(payload or {})},
    )


def topology_discovery_job(
    *,
    source: str,
    schedule: str,
    next_run_at: datetime | None = None,
    enabled: bool = True,
    payload: Mapping[str, Any] | None = None,
) -> ScheduledJob:
    """Return the scheduled job that runs one discovery source and reconciles it.

    Reconciliation is part of the job rather than a second one. A discovery run
    whose result is never applied has observed the estate and told nobody, and
    splitting the two would create a window in which a healthy run's findings sit
    unapplied while an operator wonders why the graph is stale.
    """
    return ScheduledJob(
        job_id=JOB_ID.format(kind=TOPOLOGY_DISCOVERY_JOB_KIND, source=source),
        name=f"Topology discovery: {source}",
        kind=TOPOLOGY_DISCOVERY_JOB_KIND,
        schedule=schedule,
        next_run_at=next_run_at,
        enabled=enabled,
        payload={SOURCE_KEY: source, **(payload or {})},
    )


def source_of(job: ScheduledJob) -> str:
    """Return the source a scheduled job's payload names, or ``""``."""
    return str(job.payload.get(SOURCE_KEY, ""))


__all__ = [
    "JOB_ID",
    "SOURCE_KEY",
    "knowledge_sync_job",
    "source_of",
    "topology_discovery_job",
]
