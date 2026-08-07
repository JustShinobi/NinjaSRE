"""Capture and compare the console's screenshots, in one image and only that one.

Font rasterisation differs between operating systems, between font packages on
the same operating system, and between two versions of the same font package. A
baseline captured anywhere but one pinned image therefore produces differences
that mean nothing — and a visual gate that reports differences meaning nothing
is a visual gate people stop reading.

So there is exactly one image, pinned by digest rather than by tag, and this is
the only way in. ``compare`` runs the suite against the committed baselines and
fails on any difference, writing the difference out as an image. ``accept``
recaptures them, which produces a diff of PNG files somebody has to review and
commit — the acceptance is the commit, not a flag on a command.

Usage::

    python -m tools.console_visual compare
    python -m tools.console_visual accept

Exits 0 when every screen matches, 1 when one does not, and 2 when the image
could not be run — which is a different thing and says so.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from config.constants.console import (
    CONSOLE_DIR_NAME,
    CONSOLE_VISUAL_IMAGE,
    NINJASRE_CONSOLE_TOOLCHAIN_ENV,
)
from tools.console_toolchain import REPO_ROOT

#: Where the repository is mounted inside the image.
_WORKDIR: Final = "/work"

#: What the container writes that is not a test artefact. Kept inside the
#: toolchain directory so a run leaves nothing outside what git already ignores.
_HOME: Final = f"{_WORKDIR}/{CONSOLE_DIR_NAME}/.toolchain/container-home"


class VisualError(RuntimeError):
    """The capture image could not be run, so nothing was compared."""


def container_runtime() -> str:
    """Return the container runtime to use.

    Raises:
        VisualError: there is none.
    """
    found = shutil.which("docker")
    if found is None:
        raise VisualError(
            "no container runtime found. The visual baselines are captured in one pinned "
            f"image ({CONSOLE_VISUAL_IMAGE.split('@')[0]}) and compared only against captures "
            f"from it, so there is nothing useful to compare on a machine that cannot run it."
        )
    return found


def _command(runtime: str, arguments: Sequence[str]) -> list[str]:
    """Return the full container invocation for ``arguments``."""
    Path(REPO_ROOT / CONSOLE_DIR_NAME / ".toolchain" / "container-home").mkdir(
        parents=True, exist_ok=True
    )
    return [
        runtime,
        "run",
        "--rm",
        "--init",
        # As the invoking user, so the baselines and diffs a run writes are not
        # left owned by root in somebody's working tree.
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        f"{REPO_ROOT}:{_WORKDIR}",
        "--workdir",
        f"{_WORKDIR}/{CONSOLE_DIR_NAME}",
        "--env",
        f"HOME={_HOME}",
        "--env",
        "CI=1",
        # No route off the host. The console under test is served inside the
        # container and every asset it needs is bundled, so a capture that
        # needed the network would be a defect this is here to catch.
        "--network",
        "none",
        CONSOLE_VISUAL_IMAGE,
        *arguments,
    ]


def run(*, accept: bool = False) -> int:
    """Capture the console's screens inside the pinned image and return the status.

    Raises:
        VisualError: the image could not be run.
    """
    runtime = container_runtime()
    inner = [
        "node",
        "scripts/visual.mjs",
        "--accept" if accept else "--compare",
    ]
    finished = subprocess.run(_command(runtime, inner), cwd=REPO_ROOT, check=False)
    return finished.returncode


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_visual", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("compare", help="fail on any difference from the committed baselines")
    commands.add_parser("accept", help="recapture the baselines, for review as a commit")

    arguments = parser.parse_args(argv)
    try:
        return run(accept=arguments.command == "accept")
    except VisualError as error:
        if os.environ.get(NINJASRE_CONSOLE_TOOLCHAIN_ENV) == "required":
            print(f"console visual: {error}", file=sys.stderr)
            return 2
        print(f"console visual: skipped — {error}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(_main())
