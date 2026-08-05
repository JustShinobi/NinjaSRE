"""Run the repository's import contracts against an isolated module tree.

Invoked as a subprocess by ``test_import_contracts.py``. It exists as a separate
entry point because the fixture tree has to lead ``sys.path`` *before* anything
resolves a module name — in particular ``platform``, which the first-party
package shadows and which any earlier import would otherwise pin to the stdlib.

Usage::

    python tests/architecture/run_contracts.py <package_root> <config_file>

The process must be started with ``package_root`` as its working directory:
``lint_imports`` inserts ``os.getcwd()`` at the head of ``sys.path`` itself, so
running from anywhere else puts that directory ahead of the tree under test and
the real first-party packages get graphed instead of the fixture.

Exits 0 when every contract holds and 1 when any is broken, mirroring
``lint-imports``. The contract report goes to stdout.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    """Graph the tree at ``argv[1]`` and check the contracts in ``argv[2]``."""
    if len(argv) != 3:
        print(f"usage: {argv[0]} <package_root> <config_file>", file=sys.stderr)
        return 2

    package_root, config_filename = argv[1], argv[2]

    # Import before touching sys.path or sys.modules. On Linux, click pulls in
    # the stdlib uuid module, which does its own unguarded ``platform.system()``
    # at import time (Windows and macOS skip that branch, which is why this
    # never surfaced there). Resolving it now, while ``platform`` still means
    # the real stdlib module, lets that value get baked into uuid's namespace
    # before the fixture's inert platform stub is anywhere on the path.
    from importlinter.cli import lint_imports

    # Ahead of site-packages *and* ahead of the stdlib, so the fixture's own
    # seven packages are the ones graphed. ``lint_imports`` then inserts the
    # working directory ahead of this entry, which is why the caller must start
    # the process inside ``package_root``.
    sys.path.insert(0, package_root)
    for shadowed in ("config", "core", "platform", "integrations", "capabilities"):
        sys.modules.pop(shadowed, None)

    return int(lint_imports(config_filename=config_filename, no_cache=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
