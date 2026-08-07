"""Render ``deploy/compose/.env.example`` from the settings catalogue.

FR-009 asks that every setting be documented with its default, whether it is
required, and what it affects. A hand-written file satisfies that on the day it
is written and not on any day after — the setting somebody adds in three months
is the one that goes undocumented, and nothing notices.

So the catalogue in ``platform/startup/settings.py`` is the source and this
renders it. ``--check`` fails the build when the shipped file has drifted, which
is the same shape as ``tools/generate_integration_docs.py`` and for the same
reason.

Usage::

    python tools/generate_env_example.py
    python tools/generate_env_example.py --check

Exits 0 when the file is current, 1 when it is not.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from platform.startup.settings import render_env_example

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the generated file lives. The Compose deployment reads it as ``.env``
#: after an operator copies it, which is why it sits beside the compose files
#: rather than at the repository root.
ENV_EXAMPLE_PATH = REPO_ROOT / "deploy" / "compose" / ".env.example"


def main(argv: Sequence[str] | None = None) -> int:
    """Write or check the generated file, and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the file is out of date",
    )
    parser.add_argument("--path", type=Path, default=ENV_EXAMPLE_PATH)
    arguments = parser.parse_args(argv)

    rendered = render_env_example()
    path: Path = arguments.path

    if arguments.check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == rendered:
            return 0
        print(  # noqa: T201 — this is a build check talking to a person
            f"{path} is out of date. Run `make env-example` to regenerate it "
            f"from platform/startup/settings.py.",
            file=sys.stderr,
        )
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(f"wrote {path}")  # noqa: T201 — this is a generator talking to a person
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
