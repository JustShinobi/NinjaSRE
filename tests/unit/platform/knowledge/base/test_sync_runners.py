"""The two knowledge job kinds, as the scheduler now runs them.

Both jobs have been definable since ``schedule.py`` was written and neither has
ever run: there was no runner, so registering a nightly Confluence sync produced
a row that came due for ever and did nothing. These are the adapters that close
that, and they are tested on the three things an adapter of this shape gets
wrong.

**The source is looked up, not trusted.** A job naming a source this deployment
does not have fails with the name in the message, rather than syncing nothing and
reporting success — which is the same silence one layer down.

**The team comes off the payload.** A corpus is read *for a team*: its checks
become that team's detectors. A run that ingested into the organisation root
because nobody read ``node_id`` would put one team's runbooks in front of
another's.

**The record is the report.** What the runner returns is what an operator reads
in the morning, so it carries the refusals per document rather than a count.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from config.constants.knowledge import CORPUS_SYNC_JOB_KIND, KNOWLEDGE_SYNC_JOB_KIND
from platform.knowledge.base.detector_candidates import DetectorCandidate
from platform.knowledge.base.sync.corpus_run import CorpusReport
from platform.knowledge.base.sync.port import SourceDocument, SyncReport
from platform.knowledge.base.sync.runner import (
    CorpusSyncRunner,
    KnowledgeSyncRunner,
    UnknownSource,
)
from platform.persistence.ports import JobClaim, ScheduledJob, TenantScope
from platform.scheduler.dispatch import JobContext

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "team-payments"
EPOCH = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)


@dataclass(slots=True)
class StubSource:
    """A document source with a name and nothing behind it."""

    name: str = "wiki"

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return no documents; what the sync does with them is its own suite."""
        return ()


@dataclass(slots=True)
class StubSync:
    """A document sync that records the source it was handed."""

    report: SyncReport = field(
        default_factory=lambda: SyncReport(source="wiki", at=EPOCH, stored=("wiki:1",))
    )
    ran: list[str] = field(default_factory=list)

    async def run(self, source: StubSource) -> SyncReport:
        """Record ``source`` and answer with a fixed report."""
        self.ran.append(source.name)
        return self.report


@dataclass(slots=True)
class StubCorpus:
    """A corpus pass that records the source it was handed."""

    report: CorpusReport = field(
        default_factory=lambda: CorpusReport(
            sync=SyncReport(source="infra", at=EPOCH, stored=("infra:README.md",)),
            candidates=(
                DetectorCandidate(
                    detector_id="disk-pressure",
                    name="Disk pressure",
                    description="the runbook says under ten per cent is a page",
                    signal="disk_free_ratio",
                    comparison="lt",
                    fire_value=0.1,
                    origin="infra:README.md",
                ),
            ),
        )
    )
    ran: list[str] = field(default_factory=list)

    async def run(self, source: StubSource) -> CorpusReport:
        """Record ``source`` and answer with a fixed report."""
        self.ran.append(source.name)
        return self.report


def context(
    *,
    kind: str = KNOWLEDGE_SYNC_JOB_KIND,
    payload: Mapping[str, object] | None = None,
) -> JobContext:
    """Return the context a worker hands a runner for one claimed firing."""
    job = ScheduledJob(
        job_id=f"{kind}:wiki",
        name="A job under test",
        kind=kind,
        schedule="0 2 * * *",
        payload=dict({"source": "wiki"} if payload is None else payload),
    )
    claim = JobClaim(
        claim_id="claim-1",
        job_id=job.job_id,
        org_id=ORG,
        worker_id="replica-a",
        claimed_at=EPOCH,
        lease_expires_at=EPOCH,
        payload=job.payload,
    )
    return JobContext(claim=claim, job=job, scope=TenantScope(org_id=ORG), fire_time=EPOCH)


# -- the document sync ---------------------------------------------------------


async def test_the_sync_runs_the_source_the_payload_names() -> None:
    sync = StubSync()
    runner = KnowledgeSyncRunner(sources={"wiki": StubSource()}, sync_for=lambda _scope: sync)

    record = await runner.run(context())

    assert sync.ran == ["wiki"]
    assert record["stored"] == ["wiki:1"]


async def test_a_source_this_deployment_does_not_have_fails_by_name() -> None:
    runner = KnowledgeSyncRunner(sources={"wiki": StubSource()}, sync_for=lambda _scope: StubSync())

    with pytest.raises(UnknownSource, match="confluence"):
        await runner.run(context(payload={"source": "confluence"}))


async def test_a_job_that_names_no_source_at_all_fails_rather_than_guessing() -> None:
    """One configured source is not licence to sync it from a job about another."""
    runner = KnowledgeSyncRunner(sources={"wiki": StubSource()}, sync_for=lambda _scope: StubSync())

    with pytest.raises(UnknownSource):
        await runner.run(context(payload={}))


# -- the corpus pass -----------------------------------------------------------


async def test_the_corpus_pass_reads_for_the_team_its_payload_names() -> None:
    seen: list[TenantScope] = []
    corpus = StubCorpus()

    def corpus_for(scope: TenantScope) -> StubCorpus:
        seen.append(scope)
        return corpus

    runner = CorpusSyncRunner(sources={"infra": StubSource(name="infra")}, corpus_for=corpus_for)
    await runner.run(
        context(kind=CORPUS_SYNC_JOB_KIND, payload={"source": "infra", "node_id": TEAM})
    )

    assert seen == [TenantScope(org_id=ORG, team_node_id=TEAM)]


async def test_the_corpus_record_carries_the_detectors_it_only_proposes() -> None:
    """Returned, never written: a detector is a configuration change."""
    runner = CorpusSyncRunner(
        sources={"infra": StubSource(name="infra")}, corpus_for=lambda _scope: StubCorpus()
    )

    record = await runner.run(
        context(kind=CORPUS_SYNC_JOB_KIND, payload={"source": "infra", "node_id": TEAM})
    )

    assert record["candidates"] == ["disk-pressure"]
