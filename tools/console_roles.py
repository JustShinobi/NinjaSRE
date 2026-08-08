"""The role catalogue, written out where a console can read it.

The console is not a Python package and may not import one, so it cannot ask
``platform.identity.permissions`` what a role holds. It also must not decide:
a second copy of the catalogue, written in TypeScript, would be the copy that is
wrong on the day somebody adds a permission.

So the catalogue is *generated* into the fixture tree, which the console already
reads as data, and a contract test compares the committed file against a fresh
generation. A role gained or a permission moved fails the gate rather than
quietly changing what the console shows.

Usage::

    python -m tools.console_roles write
    python -m tools.console_roles check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from config.constants.fixtures import FIXTURE_CONTRACT_DIR_NAME, FIXTURE_ROOT_DIR_NAME
from platform.identity.permissions import ROLE_ORDER, Permission, permissions_for

#: Where the generated catalogue lives, beside the OpenAPI document that is
#: generated the same way and for the same reason.
ROLES_FILENAME: Final = "roles.json"

_COMMENT: Final = (
    "Generated from the platform's permission catalogue by "
    "`python -m tools.console_roles write`. The console reads this to prove that "
    "every navigation entry and every shell control a role cannot use is absent "
    "from the DOM — it never decides what a role holds. A contract test compares "
    "this file against a fresh generation, so editing it by hand fails the gate."
)


def repository_root() -> Path:
    """Return the repository root, from this file's location."""
    return Path(__file__).resolve().parents[1]


def roles_path(root: Path | None = None) -> Path:
    """Return where the generated catalogue is written."""
    base = root if root is not None else repository_root()
    return base / FIXTURE_ROOT_DIR_NAME / FIXTURE_CONTRACT_DIR_NAME / ROLES_FILENAME


def roles_document() -> dict[str, Any]:
    """Return the catalogue as the console reads it: least privileged first."""
    return {
        "$comment": _COMMENT,
        "order": [role.value for role in ROLE_ORDER],
        "permissions": sorted(permission.value for permission in Permission),
        "roles": {
            role.value: sorted(permission.value for permission in permissions_for(role))
            for role in ROLE_ORDER
        },
    }


def rendered() -> str:
    """Return the document as it is committed: sorted, indented, one trailing newline."""
    return json.dumps(roles_document(), indent=2, sort_keys=True) + "\n"


def write(root: Path | None = None) -> Path:
    """Write the catalogue and return where it went."""
    path = roles_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered(), encoding="utf-8")
    return path


def drifted(root: Path | None = None) -> bool:
    """Return whether the committed catalogue differs from a fresh generation."""
    path = roles_path(root)
    if not path.is_file():
        return True
    return path.read_text(encoding="utf-8") != rendered()


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_roles", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("write", help="regenerate the committed catalogue")
    commands.add_parser("check", help="fail if the committed catalogue has drifted")

    arguments = parser.parse_args(argv)
    if arguments.command == "write":
        print(f"wrote {write()}")
        return 0
    if drifted():
        print(
            f"{roles_path()} is not what the permission catalogue generates; "
            "run `python -m tools.console_roles write`",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
