"""The verification document's checks, arriving somewhere a person will see them.

Feature 056 built the reading and said outright what was missing: "'Proposed'
needs somewhere for the proposal to arrive. Today it arrives in
``CorpusReport.candidates``, which is a return value: a caller has it, and there
is no scheduled corpus-sync job in this feature to be that caller."

This is the caller, and these are the two properties it has to have. The check
lands in the queue disabled, carrying the sentence its author wrote — and a
second pass over an unchanged document proposes nothing, because a queue that
regrows every morning is one people stop opening.
"""

from __future__ import annotations

import pytest

from config.constants.knowledge import CORPUS_SYNC_JOB_KIND
from platform.approvals.appliers import proposal_appliers_for
from platform.config_service.service import ConfigService
from platform.knowledge.base.detector_candidates import candidates_from
from platform.knowledge.base.sync.schedule import corpus_sync_job, node_of, source_of
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.proposals.corpus import DetectorProposals
from platform.proposals.service import ProposalQueue
from tests.unit.platform.proposals.conftest import TEAM, Clock, settings_of

pytestmark = pytest.mark.unit

#: The verification document, in the shape the real one is written in.
QUERIES = """# Cluster double-check queries

## No datastore is above its safe fill

A datastore past this cannot complete a snapshot of its largest guest.

- signal: `datastore.used_percent`
- fires when: above 85
"""

CANDIDATE_ID = "corpus-no-datastore-is-above-its-safe-fill"


def offered(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Clock
) -> DetectorProposals:
    """Return the composer that puts a corpus run's candidates in the queue."""
    return DetectorProposals(
        queue=ProposalQueue(
            gateway=gateway,
            scope=scope,
            appliers=proposal_appliers_for(config=config),
            clock=clock,
        ),
        node_id=TEAM,
    )


def candidates() -> list[dict[str, object]]:
    """Return what the document proposes, as the settings mappings 056 produces."""
    read = candidates_from(
        QUERIES,
        document_id="corpus:docs/verification.md",
        location="docs/verification.md",
    )
    assert read, "the document must actually propose something"
    return [
        {**candidate.to_settings(), "origin_excerpt": candidate.origin_excerpt}
        for candidate in read
    ]


async def test_a_documented_check_reaches_the_queue_with_its_authors_reason(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Clock
) -> None:
    result = await offered(gateway, scope, config, clock).offer(candidates(), run_id="corpus-1")

    assert [proposal.payload["detector_id"] for proposal in result.queued] == [CANDIDATE_ID]
    queued = result.queued[0]
    assert queued.payload["enabled"] is False
    assert any("safe fill" in item for item in queued.evidence)
    assert queued.effect.mechanism == "detector-dry-run"


async def test_nothing_is_watching_until_somebody_decides(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Clock
) -> None:
    """056's scope, held: a document cannot turn itself into something that pages."""
    await offered(gateway, scope, config, clock).offer(candidates(), run_id="corpus-1")

    assert await settings_of(gateway) == {}


async def test_a_second_pass_over_an_unchanged_document_proposes_nothing(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Clock
) -> None:
    composer = offered(gateway, scope, config, clock)
    await composer.offer(candidates(), run_id="corpus-1")

    again = await composer.offer(candidates(), run_id="corpus-2")

    assert again.queued == ()
    assert [name for name, _ in again.skipped] == [CANDIDATE_ID]


async def test_a_candidate_already_refused_is_not_offered_again(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Clock
) -> None:
    """A decision stands. Re-asking nightly is how a reason stops being read."""
    composer = offered(gateway, scope, config, clock)
    first = await composer.offer(candidates(), run_id="corpus-1")
    await composer.queue.reject(
        first.queued[0].proposal_id,
        reviewer="erik@example.com",
        reason="The snapshot runs nightly; 85 is normal on this datastore.",
    )

    again = await composer.offer(candidates(), run_id="corpus-2")

    assert again.queued == ()
    assert again.skipped[0][1] == "already in the queue or already answered"


def test_the_corpus_sync_is_a_registerable_job_naming_its_team() -> None:
    """Idempotent by construction: registering it twice replaces one definition."""
    job = corpus_sync_job(source="infra-repo", schedule="0 3 * * *", node_id=TEAM)

    assert job.kind == CORPUS_SYNC_JOB_KIND
    assert job.job_id == f"{CORPUS_SYNC_JOB_KIND}:infra-repo"
    assert source_of(job) == "infra-repo"
    assert node_of(job) == TEAM
    assert (
        job.job_id
        == corpus_sync_job(source="infra-repo", schedule="0 4 * * *", node_id=TEAM).job_id
    )
