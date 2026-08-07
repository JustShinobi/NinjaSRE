"""The ``ninjasre`` console script, and the one thing it has to do first.

``platform/`` deliberately shadows the stdlib module, and it only wins the name
when the package root leads ``sys.path``. Every NinjaSRE process runs that way
— except a console script, which Python starts with the interpreter's own path
and the stdlib ahead of site-packages. Importing the application directly from
the entry point therefore finds the *stdlib* ``platform`` and fails on
``platform.observability``, which is a confusing way for a freshly installed
CLI to greet somebody.

So this module is deliberately import-light: it takes no first-party import at
module scope, fixes the path, and only then loads the application. The order is
the whole point, and it is why this is a separate module rather than a function
in ``app.py`` — a module that imported the app at the top would have already
lost by the time its function ran.

``tests/conftest.py`` solves the same problem for pytest, for the same reason
and in the same way.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

#: The directory holding the seven first-party packages. Two levels up from
#: this file: ``<root>/surfaces/entrypoint.py``.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def lead_sys_path() -> None:
    """Move the package root to the head of ``sys.path``.

    Merely being present is not enough. An editable install already puts the
    root on the path, but behind the stdlib — which would leave the stdlib
    ``platform`` module owning the name the first-party package must have.
    """
    root = str(PACKAGE_ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)


def bind_first_party_platform() -> None:
    """Make ``import platform`` reach the repository package.

    Rebinding is safe: the package re-exports the stdlib module's entire public
    API, and anything that imported the stdlib earlier holds its own reference
    to that module object. A package already bound is left alone, which is what
    makes this idempotent and cheap to call.
    """
    cached = sys.modules.get("platform")
    if cached is not None and getattr(cached, "__path__", None) is not None:
        return

    sys.modules.pop("platform", None)
    importlib.invalidate_caches()
    importlib.import_module("platform")


def main() -> None:
    """Run the ``ninjasre`` command.

    What ``pyproject.toml``'s console script points at.
    """
    lead_sys_path()
    bind_first_party_platform()

    # Imported here, after the path is right. A module-scope import would run
    # before ``main`` and defeat the whole of this file.
    from surfaces.cli.app import app

    app()


if __name__ == "__main__":
    main()
