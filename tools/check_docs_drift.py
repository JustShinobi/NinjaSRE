"""Fail the build when the generated documentation has drifted from the code.

Generation without a drift check is a convention, and a convention is something
somebody skips on the afternoon they are in a hurry. This is the enforcement:
regenerate in memory, compare against the tree, and fail naming what moved.

Three failures, and the third is the one a plain diff would miss:

``missing``
    A page the declarations produce and the tree does not have.

``out of date``
    A page whose content the declarations no longer agree with — a capability
    whose side-effect level changed, a permission added to an integration.

``stale reference``
    A page under a generated directory that nothing produces any more. This is
    what a *removed* capability leaves behind, and a reference to something that
    no longer exists is worse than a missing one: it sends somebody to use a
    tool that is gone.

Usage::

    python -m tools.check_docs_drift [--root docs/site]

Exits 0 when the tree is current, 1 when it is not. Run as a module from the
repository root; ``tools/verify_integrations.py`` explains why.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from tools.generate_docs import DEFAULT_ROOT
from tools.generate_docs import main as generate


def main(argv: Sequence[str] | None = None) -> int:
    """Check the generated tree against the declarations."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    arguments = parser.parse_args(argv)

    return generate(["--check", "--root", str(arguments.root)])


if __name__ == "__main__":
    raise SystemExit(main())
