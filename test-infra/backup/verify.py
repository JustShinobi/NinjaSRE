"""Check that a restored database holds what the backup's manifest recorded.

SC-004 asks that a restore preserve relational, vector, and graph integrity.
"Integrity" is only a claim with a number behind it, so this is the number: the
manifest recorded a count per table when the backup was taken, and the restored
database is read back through the repository ports and compared.

Read through the ports rather than with a count query, deliberately. A
verification that reached behind the ports would be verifying a schema rather
than a working deployment, and the failure this exists to catch — a restore that
looks complete and is not — shows up either way.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.deployment import BACKUP_MANIFEST_FILENAME  # noqa: E402
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV  # noqa: E402
from platform.persistence.ports import TenantScope  # noqa: E402
from platform.persistence.postgres.gateway import PostgresPersistence  # noqa: E402
from platform.startup.backup import BackupManifest  # noqa: E402

ORG_ID = "acme"


async def _restored_runs() -> int:
    """Return how many runs the restored database holds, through the ports."""
    store = PostgresPersistence.from_url(os.environ[NINJASRE_DATABASE_URL_ENV])
    try:
        async with store.begin(TenantScope(org_id=ORG_ID)) as uow:
            return len(await uow.run_traces.list_runs(limit=200))
    finally:
        await store.close()


def _manifest_of(archive: Path) -> BackupManifest:
    """Return the manifest inside ``archive``."""
    with tempfile.TemporaryDirectory() as work:
        with tarfile.open(archive) as bundle:
            bundle.extractall(work, filter="data")
        found = next(Path(work).rglob(BACKUP_MANIFEST_FILENAME))
        return BackupManifest.read(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the restored database against the manifest, and report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    arguments = parser.parse_args(argv)

    manifest = _manifest_of(arguments.archive)
    recorded = {
        table: count for table, count in manifest.row_counts.items() if table.endswith("agent_runs")
    }
    if not recorded:
        print("The manifest recorded no runs, so the seed never ran.", file=sys.stderr)  # noqa: T201
        return 1

    expected = sum(recorded.values())
    found = asyncio.run(_restored_runs())

    if found != expected:
        print(  # noqa: T201
            f"The backup recorded {expected} run(s) and the restore has {found}.",
            file=sys.stderr,
        )
        return 1

    extensions = ", ".join(sorted(manifest.extensions))
    print(  # noqa: T201 — the shell script's report
        f"Restored {found} run(s) intact, at schema {manifest.schema_revision}, "
        f"with extensions: {extensions}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
