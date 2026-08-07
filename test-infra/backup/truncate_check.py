"""Prove that a truncated artefact is refused rather than restored quietly.

The happy path of a backup cycle proves the procedure works. This proves the
*check* works, which is the half that matters at three in the morning: an
archive cut short while it was being copied restores without complaint and is
discovered when a query comes back short, weeks later.

Takes a real archive, drops the last few rows out of its dump, leaves the
manifest alone — which is exactly what truncation looks like — and asserts that
``check.py`` refuses it and says why.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.constants.deployment import (  # noqa: E402
    BACKUP_DUMP_FILENAME,
    BACKUP_MANIFEST_FILENAME,
)

#: What ``deploy/ops/check.py`` exits with on a refusal.
REFUSED_EXIT = 3


def main(argv: Sequence[str] | None = None) -> int:
    """Truncate a copy of the archive's dump and check that the check refuses it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    arguments = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as work:
        with tarfile.open(arguments.archive) as bundle:
            bundle.extractall(work, filter="data")

        dump = next(Path(work).rglob(BACKUP_DUMP_FILENAME))
        manifest = next(Path(work).rglob(BACKUP_MANIFEST_FILENAME))

        lines = dump.read_text(encoding="utf-8").splitlines()
        dump.write_text("\n".join(lines[: -max(5, len(lines) // 10)]) + "\n", encoding="utf-8")

        result = subprocess.run(  # noqa: S603 — a fixed argument list, no shell
            [
                sys.executable,
                str(REPO_ROOT / "deploy" / "ops" / "check.py"),
                "--manifest",
                str(manifest),
                "--dump",
                str(dump),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != REFUSED_EXIT:
        print(  # noqa: T201
            f"A truncated archive was not refused: exit {result.returncode}.\n"
            f"{result.stdout}\n{result.stderr}",
            file=sys.stderr,
        )
        return 1
    if "truncated" not in result.stderr:
        print(  # noqa: T201
            f"It was refused without saying why:\n{result.stderr}", file=sys.stderr
        )
        return 1

    print("A truncated archive is refused, with the reason.")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
