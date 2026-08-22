"""Write the manifest that travels with a backup, and count what the dump holds.

Two facts go in, and they answer different questions on the way back out.

**What release wrote this.** The schema revision, the PostgreSQL major version,
and the extension versions. ``platform.startup.backup.decide_restore`` turns
those into restore, migrate-forward, or a refusal with a reason — before
anything is written.

**Whether the artefact is whole.** A count per table, read out of the dump
itself rather than out of the database. A dump truncated by a full disk is the
failure this catches, and it is the one that otherwise restores quietly and is
discovered when a query comes back short. Counting the dump means the check
also works on an artefact that has been copied between machines, which is when
truncation actually happens.

**The encryption key's fingerprint, never the key.** Twelve hex characters of a
digest — enough to tell two hosts apart, useless to an attacker. A restore into
a deployment holding a different key succeeds perfectly and leaves every stored
credential unreadable, and this is what makes that refusable rather than
discoverable.

Usage::

    python deploy/ops/manifest.py --dump backup/database.sql --output backup/manifest.json
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    # The scripts under deploy/ run from an operator's shell and from a
    # container, neither of which has necessarily installed the wheel.
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.persistence import NINJASRE_DATABASE_URL_ENV  # noqa: E402
from platform.persistence.postgres.gateway import PostgresPersistence  # noqa: E402
from platform.startup.backup import (  # noqa: E402
    BackupManifest,
    dump_digest,
    row_counts_in,
)
from platform.startup.keys import configured_key, key_fingerprint  # noqa: E402


async def _facts(url: str) -> tuple[str, int | None, dict[str, str]]:
    """Return the schema revision, server version, and extension versions."""
    store = PostgresPersistence.from_url(url)
    try:
        health = await store.health()
    finally:
        await store.close()
    revision = "" if health.migrations is None else (health.migrations.applied_revision or "")
    extensions = {
        status.name: status.version or "" for status in health.extensions if status.available
    }
    return revision, health.server_version, extensions


def main(argv: Sequence[str] | None = None) -> int:
    """Write the manifest and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True, help="the plain-format pg_dump")
    parser.add_argument("--output", type=Path, required=True, help="where the manifest goes")
    parser.add_argument("--app-version", default=os.environ.get("NINJASRE_VERSION", ""))
    arguments = parser.parse_args(argv)

    url = os.environ.get(NINJASRE_DATABASE_URL_ENV, "")
    if not url:
        print(  # noqa: T201 — an operator is reading a terminal
            f"{NINJASRE_DATABASE_URL_ENV} is not set, so the manifest cannot record "
            f"which schema this backup was taken at. A backup without that cannot be "
            f"version-checked on the way back in.",
            file=sys.stderr,
        )
        return 2

    revision, server_version, extensions = asyncio.run(_facts(url))
    key = configured_key()

    manifest = BackupManifest(
        schema_revision=revision,
        taken_at=datetime.now(UTC),
        app_version=arguments.app_version,
        postgres_version=server_version,
        extensions=extensions,
        row_counts=row_counts_in(arguments.dump),
        encryption_key_fingerprint="" if key is None else key_fingerprint(key),
        dump_sha256=dump_digest(arguments.dump),
    )
    manifest.write(arguments.output)
    print(arguments.output)  # noqa: T201 — the shell script consumes this
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
