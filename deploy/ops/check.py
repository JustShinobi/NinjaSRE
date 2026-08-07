"""Decide whether a backup may be restored into this release, and say why.

Prints one word on stdout — ``restore``, ``migrate_forward``, or ``refuse`` —
for ``restore.sh`` to branch on, and the reason on stderr for the person
watching. Exits non-zero on a refusal, so a script that forgot to read the word
still stops.

The decision itself is ``platform.startup.backup.decide_restore``. Nothing is
decided here: this reads a manifest, gathers what this release ships, and
prints the answer. Keeping the rule in the package rather than in the script is
what lets it be unit-tested against every combination, including the ones that
are hard to produce on a real database.

Usage::

    python deploy/ops/check.py --manifest backup/manifest.json --dump backup/database.sql
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.persistence import REQUIRED_POSTGRES_EXTENSIONS  # noqa: E402
from platform.persistence.postgres.migrations import (  # noqa: E402
    head_revision,
    ordered_revisions,
)
from platform.startup.backup import (  # noqa: E402
    BackupIncompatible,
    BackupManifest,
    RestoreAction,
    decide_restore,
    row_counts_in,
    verify_row_counts,
)
from platform.startup.keys import configured_key, key_fingerprint  # noqa: E402

#: What a refusal exits with. Distinct from a crash so a wrapper can tell
#: "this backup must not be restored" from "the check itself broke".
REFUSED_EXIT = 3


def main(argv: Sequence[str] | None = None) -> int:
    """Print the decision and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dump", type=Path, required=False)
    arguments = parser.parse_args(argv)

    try:
        manifest = BackupManifest.read(arguments.manifest)
    except BackupIncompatible as error:
        print(str(error), file=sys.stderr)  # noqa: T201 — an operator is reading this
        print(str(RestoreAction.REFUSE))  # noqa: T201 — restore.sh branches on this
        return REFUSED_EXIT

    key = configured_key()
    decision = decide_restore(
        manifest,
        expected_revision=head_revision(),
        ordered_revisions=ordered_revisions(),
        available_extensions=REQUIRED_POSTGRES_EXTENSIONS,
        encryption_key_fingerprint="" if key is None else key_fingerprint(key),
    )

    if decision.permitted and arguments.dump is not None:
        problems = verify_row_counts(manifest, row_counts_in(arguments.dump))
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)  # noqa: T201
            print(  # noqa: T201
                "The archive holds fewer rows than the manifest recorded, so it was "
                "truncated after it was written. Restoring it would lose whatever is "
                "missing, silently.",
                file=sys.stderr,
            )
            print(str(RestoreAction.REFUSE))  # noqa: T201
            return REFUSED_EXIT

    print(decision.reason, file=sys.stderr)  # noqa: T201 — the reason is for a person
    print(str(decision.action))  # noqa: T201 — the word is for restore.sh
    return 0 if decision.permitted else REFUSED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
