"""The console's size budgets, measured against the build that just ran.

Two numbers, both from ``config/constants/console.py`` so that raising one is a
change to the constants tier and shows up in review rather than in a flag.

**The stylesheet.** A design system that has stopped being a system shows up
here first. Every component that writes its own values instead of naming a token
adds rules nothing else shares, and the compiled sheet grows faster than the
console does — long before anybody notices that two cards have different
padding. So the sheet has a ceiling, and crossing it is a failure rather than a
statistic.

**The icon set.** Every icon is a named export drawn in this repository, so a
page carries the icons it imports and nothing else; there is no font, no sprite
and no request, which is what keeps first paint independent of the set. This
measures the ceiling instead — the whole set, as it would ship to a page that
used all of it — because that is the number that stays true regardless of which
page you look at.

Usage::

    python -m tools.console_budget

Exits 0 when both are within budget, 1 when either is over, and 2 when there is
no build to measure — which is a skip rather than a failure, in the same way the
rest of the console gate treats a missing toolchain.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from config.constants.console import (
    CONSOLE_ICON_BUDGET_BYTES,
    CONSOLE_STYLESHEET_BUDGET_BYTES,
)
from tools.console_toolchain import console_root

#: The status that means "there was nothing to measure", not "it failed".
EXIT_NOTHING_TO_MEASURE = 2


@dataclass(frozen=True, slots=True)
class Budget:
    """One thing that is measured, what it measured, and what it may be."""

    what: str
    measured: int
    allowed: int

    @property
    def within(self) -> bool:
        """Whether the measurement is inside the budget."""
        return self.measured <= self.allowed

    def describe(self) -> str:
        """Return one line a contributor can act on."""
        verdict = "within" if self.within else "OVER"
        return (
            f"{self.what}: {self.measured} bytes, budget {self.allowed} "
            f"({verdict}, {self.measured * 100 // max(self.allowed, 1)}% of it)"
        )


def stylesheet_bytes(root: Path) -> int | None:
    """Return the total size of the compiled stylesheets, or ``None`` if unbuilt."""
    static = root / ".next" / "static"
    if not static.is_dir():
        return None
    sheets = list(static.rglob("*.css"))
    if not sheets:
        return None
    return sum(sheet.stat().st_size for sheet in sheets)


def icon_bytes(root: Path) -> int | None:
    """Return the size of the icon set as written, or ``None`` when it is missing.

    The source rather than a bundle chunk: the bundler inlines these components
    into whichever chunk imports them, so there is no one file to weigh, and the
    source is both stable and the thing a contributor adding an icon changes.
    """
    icons = root / "src" / "design" / "icons.tsx"
    if not icons.is_file():
        return None
    return icons.stat().st_size


def measure(root: Path) -> tuple[Budget, ...] | None:
    """Return every budget measured against ``root``, or ``None`` if unbuilt."""
    sheet = stylesheet_bytes(root)
    icons = icon_bytes(root)
    if sheet is None or icons is None:
        return None
    return (
        Budget("the compiled stylesheet", sheet, CONSOLE_STYLESHEET_BUDGET_BYTES),
        Budget("the icon set", icons, CONSOLE_ICON_BUDGET_BYTES),
    )


def main() -> int:
    """Measure both budgets and report the verdict."""
    measured = measure(console_root())
    if measured is None:
        print(
            "console budget: there is no build to measure. Run `make console-build` first.",
            file=sys.stderr,
        )
        return EXIT_NOTHING_TO_MEASURE

    for budget in measured:
        print(budget.describe())

    over = [budget for budget in measured if not budget.within]
    if over:
        for budget in over:
            print(
                f"console budget: {budget.what} is {budget.measured - budget.allowed} bytes "
                f"over its budget. Raising the number is a change to "
                f"config/constants/console.py, which is where the argument for it belongs.",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
