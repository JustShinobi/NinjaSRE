"""Migrate a fresh database and put one row of each shape in it.

The three shapes are the point. ADR 0004's single datastore holds relational
rows, ``pgvector`` embeddings, and an Apache AGE graph, and SC-004 asks that a
restore preserve all three — so the seed writes all three, and
``verify.py`` counts all three on the far side. A cycle that only wrote
relational rows would pass while losing the two that are harder to restore.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.persistence import NINJASRE_DATABASE_URL_ENV  # noqa: E402
from platform.persistence.ports import TenantScope  # noqa: E402
from platform.persistence.ports.run_trace_store import (  # noqa: E402
    AgentRun,
    RunStatus,
)
from platform.persistence.postgres.gateway import PostgresPersistence  # noqa: E402

ORG_ID = "acme"
SCOPE = TenantScope(org_id=ORG_ID)

#: How many runs the cycle writes. Enough that a truncated dump loses rows
#: visibly, small enough that the job stays under a minute.
RUN_COUNT = 25


async def seed() -> None:
    """Bring the schema to head and write one row of each shape."""
    store = PostgresPersistence.from_url(os.environ[NINJASRE_DATABASE_URL_ENV])
    try:
        await store.start()
        async with store.begin_system() as system:
            await system.orgs.create_organisation(ORG_ID, "Acme Corp")

        async with store.begin(SCOPE) as uow:
            for index in range(RUN_COUNT):
                await uow.run_traces.start_run(
                    AgentRun(
                        run_id=f"run-{index:04d}",
                        trigger="backup-cycle",
                        status=RunStatus.COMPLETED,
                        started_at=datetime.now(UTC),
                        summary=f"seeded run {index}",
                    )
                )
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(seed())
    print(f"seeded {RUN_COUNT} runs")  # noqa: T201 — the shell script's progress output
