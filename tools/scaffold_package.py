"""Create a new first-party package that starts out compliant (FR-019).

The tier a package belongs to decides what it may import, where its constants
live, and whether CI will let it merge. Getting that right by hand means reading
the tier table, the constitution, and two conventions documents first — so the
common outcome is that somebody guesses, and `make check-imports` tells them
several commits later.

This writes the package skeleton, its ``AGENTS.md``, and its test directory, with
the tier's rules already stated in the module docstring.

What it deliberately does **not** do is edit ``.importlinter``. Deciding which
boundaries a new package sits behind is a judgement, and a silent rewrite of the
file CI depends on is exactly how that judgement gets skipped. The follow-up
steps are printed instead, and repeated in the generated ``AGENTS.md``.

Usage::

    python tools/scaffold_package.py <name> --tier <1-4> [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Names that already mean something else at the repository root.
RESERVED_NAMES = frozenset({"tests", "tools", "docs", "specs", "deploy", "build", "dist"})

PACKAGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ScaffoldError(Exception):
    """The package cannot be created as asked."""


@dataclass(frozen=True)
class Tier:
    """One architectural tier and the rules that come with it."""

    number: int
    summary: str
    may_import: str
    must_never_import: str


TIERS: dict[int, Tier] = {
    1: Tier(
        1,
        "entry point",
        "`capabilities`, `integrations`, `core`, `platform`, `config`",
        "its tier 1 peer",
    ),
    2: Tier(
        2,
        "capability layer",
        "`integrations`, `core`, `platform`, `config`",
        "`surfaces`, `gateway`",
    ),
    3: Tier(
        3,
        "runtime and platform services",
        "`config`, and its tier 3 sibling",
        "`capabilities`, `integrations`, `surfaces`, `gateway`",
    ),
    4: Tier(4, "leaf", "nothing first-party", "no other first-party package"),
}

MODULE_TEMPLATE = '''"""Tier {tier} — {summary}.

May import: {may_import}. Must never import: {must_never_import}.

See the tier table in the root `AGENTS.md`, and `{package}/AGENTS.md` for this
package's own conventions.
"""

from __future__ import annotations
'''

AGENTS_TEMPLATE = """# {package}/ — TODO: one line on what this package owns

**Tier {tier}.** May import: {may_import}. Must never import: {must_never_import}.

TODO: two or three sentences on what belongs here, and what looks like it
belongs here but does not.

## Conventions

TODO: the rules specific to this package. Repository-wide rules are in the root
[`AGENTS.md`](../AGENTS.md); do not repeat them here.

## Where things go

TODO: the subpackage layout, once there is one.

## Before this package is enforced

{follow_up}
"""


def validate(repo_root: Path, package: str, tier: int) -> Tier:
    """Return the tier, or explain why the package cannot be created."""
    if tier not in TIERS:
        raise ScaffoldError(f"tier must be one of {sorted(TIERS)}, not {tier}")

    if not PACKAGE_NAME_PATTERN.match(package):
        raise ScaffoldError(
            f"{package!r} is not a usable package name: lowercase, starting with a "
            "letter, containing only letters, digits, and underscores"
        )

    if package in RESERVED_NAMES:
        raise ScaffoldError(f"{package!r} already means something else at the repository root")

    if (repo_root / package).exists():
        raise ScaffoldError(f"{repo_root / package} already exists")

    return TIERS[tier]


def follow_up_steps(package: str, tier: int) -> list[str]:
    """Return the steps that make the new package actually enforced."""
    return [
        f"Add `{package}` to `root_packages` in `.importlinter`, and place it in the "
        "`layers` contract at tier "
        f"{tier}.",
        f"Add the row for `{package}` to the tier table in the root `AGENTS.md`.",
        "Add a forbidden or independence contract for any boundary the tier table "
        "states but the layers ordering does not already cover.",
        "Register the new rule in `ARCHITECTURE_RULES` in "
        "`tests/architecture/test_contract_coverage.py`, and add a violation fixture "
        "under `tests/architecture/fixtures/` proving the contract fires.",
        f"Add `{package}` to `PYTHON_SOURCE_PATHS` in the `Makefile` and to the scan "
        "roots in `tools/check_constants.py` and `tools/check_protocol_bodies.py`.",
    ]


def scaffold_package(
    repo_root: Path,
    package: str,
    tier: int,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Create the package skeleton and return the paths written.

    Validation happens before anything is written, so a rejected scaffold leaves
    nothing behind — a half-created package is worse than a clear error.
    """
    tier_rules = validate(repo_root, package, tier)

    package_dir = repo_root / package
    module = package_dir / "__init__.py"
    agents = package_dir / "AGENTS.md"
    test_dir = repo_root / "tests" / "unit" / package

    planned = [module, agents, test_dir]
    if dry_run:
        return planned

    package_dir.mkdir(parents=True)
    module.write_text(
        MODULE_TEMPLATE.format(
            tier=tier,
            summary=tier_rules.summary,
            may_import=tier_rules.may_import,
            must_never_import=tier_rules.must_never_import,
            package=package,
        ),
        encoding="utf-8",
        newline="\n",
    )
    agents.write_text(
        AGENTS_TEMPLATE.format(
            package=package,
            tier=tier,
            may_import=tier_rules.may_import,
            must_never_import=tier_rules.must_never_import,
            follow_up="\n".join(
                f"{index}. {step}" for index, step in enumerate(follow_up_steps(package, tier), 1)
            ),
        ),
        encoding="utf-8",
        newline="\n",
    )
    test_dir.mkdir(parents=True, exist_ok=True)

    return planned


def main(argv: Sequence[str] | None = None) -> int:
    """Create a package and print the follow-up the scaffold must not automate."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="the package name, lowercase with underscores")
    parser.add_argument(
        "--tier",
        type=int,
        required=True,
        choices=sorted(TIERS),
        help="the architectural tier this package belongs to",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written without writing it",
    )
    arguments = parser.parse_args(argv)

    try:
        written = scaffold_package(
            REPO_ROOT, arguments.name, arguments.tier, dry_run=arguments.dry_run
        )
    except ScaffoldError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    verb = "would write" if arguments.dry_run else "wrote"
    for path in written:
        print(f"{verb} {path.relative_to(REPO_ROOT)}")

    if arguments.dry_run:
        return 0

    print(f"\n{arguments.name} is not enforced yet. Next:")
    for index, step in enumerate(follow_up_steps(arguments.name, arguments.tier), 1):
        print(f"  {index}. {step}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
