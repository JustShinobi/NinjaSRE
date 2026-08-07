"""Re-encrypt every stored credential under a new key, while the platform runs.

The no-downtime property comes from holding both keys at once. The new key
writes; the old key is installed as a read-only fallback, so a credential the
rotation has not reached yet is still readable and a request arriving mid-run
notices nothing. Batches keep any single transaction short enough that a reader
never waits on one.

Run it with the *new* key in ``NINJASRE_DATABASE_ENCRYPTION_KEY`` and the old
one in ``--previous-key``, then restart the deployment with the new key alone.
Keep the old key until a run reports every credential rewritten — the summary
says so explicitly, because "probably finished" is not a state to drop a key on.

Usage::

    NINJASRE_DATABASE_ENCRYPTION_KEY=<new> \\
        python deploy/ops/rotate_key.py --previous-key <old> --org acme

Exits 0 when every credential is under the new key, 1 when any is not.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.deployment import KEY_ROTATION_BATCH_SIZE  # noqa: E402
from config.constants.persistence import (  # noqa: E402
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from platform.persistence.ports import TenantScope  # noqa: E402
from platform.persistence.postgres.crypto import KEY_RING  # noqa: E402
from platform.persistence.postgres.gateway import PostgresPersistence  # noqa: E402
from platform.persistence.rotation import VaultReEncryptor  # noqa: E402
from platform.startup.keys import (  # noqa: E402
    decode_encryption_key,
    key_fingerprint,
    require_encryption_key,
)
from platform.startup.rotation import KeyRotationReport, rotate_encryption_key  # noqa: E402


async def _rotate(*, org_id: str, previous: bytes, batch_size: int) -> KeyRotationReport:
    """Install both keys, rewrite everything, and return what happened."""
    current = require_encryption_key()
    KEY_RING.configure(current)
    KEY_RING.configure_previous(previous)

    store = PostgresPersistence.from_url(os.environ[NINJASRE_DATABASE_URL_ENV])
    try:
        report = await rotate_encryption_key(
            VaultReEncryptor(gateway=store, scope=TenantScope(org_id=org_id)),
            batch_size=batch_size,
            key_fingerprint=key_fingerprint(current),
            on_batch=lambda running: print(  # noqa: T201 — progress, for a person watching
                f"  {len(running.rewritten)}/{running.total}", file=sys.stderr
            ),
        )
    finally:
        await store.close()
        # The fallback exists for the duration of the rotation and no longer.
        # A process that kept it would keep a key an operator believes is gone.
        KEY_RING.clear_previous()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Rotate the encryption key and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org", required=True, help="the organisation whose credentials to rewrite"
    )
    parser.add_argument(
        "--previous-key",
        required=True,
        help="the base64 key the stored credentials were written under",
    )
    parser.add_argument("--batch-size", type=int, default=KEY_ROTATION_BATCH_SIZE)
    arguments = parser.parse_args(argv)

    if not os.environ.get(NINJASRE_DATABASE_URL_ENV):
        print(f"{NINJASRE_DATABASE_URL_ENV} is not set.", file=sys.stderr)  # noqa: T201
        return 2
    if not os.environ.get(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV):
        print(  # noqa: T201
            f"Set {NINJASRE_DATABASE_ENCRYPTION_KEY_ENV} to the *new* key before "
            f"running this, and pass the old one as --previous-key.",
            file=sys.stderr,
        )
        return 2

    report = asyncio.run(
        _rotate(
            org_id=arguments.org,
            previous=decode_encryption_key(arguments.previous_key),
            batch_size=arguments.batch_size,
        )
    )
    print(report.summary())  # noqa: T201 — the answer, for the operator
    return 0 if report.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
