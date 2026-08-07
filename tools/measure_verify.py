"""Time ``make verify`` and fail when it is slower than its declared budget.

A gate people stop running is a gate that does not exist, so the budget is
asserted rather than hoped for. Two numbers, because they answer two different
questions:

**Cold** is a clean checkout on a machine with nothing cached: the Node
distribution is fetched, the browser is fetched, every dependency is installed.
It is generous, and it is measured once per workflow run so that a change which
doubles provisioning is visible.

**Warm** is the gate on a machine that has already provisioned all of it. This
is the number that decides whether a contributor runs `make verify` before
pushing or pushes and waits, so it is the tighter of the two.

Usage::

    python -m tools.measure_verify --profile warm
    python -m tools.measure_verify --profile cold --json

Exits 0 when the run passed inside its budget, 1 when the run failed, and 2 when
it passed but took too long — a distinction that matters, because "the gate is
red" and "the gate is slow" are different problems for different people.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from config.constants.console import (
    CONSOLE_COLD_VERIFY_BUDGET_SECONDS,
    CONSOLE_WARM_VERIFY_BUDGET_SECONDS,
)
from tools.console_toolchain import REPO_ROOT

BUDGETS: Final[dict[str, float]] = {
    "cold": CONSOLE_COLD_VERIFY_BUDGET_SECONDS,
    "warm": CONSOLE_WARM_VERIFY_BUDGET_SECONDS,
}

EXIT_OVER_BUDGET: Final = 2


@dataclass(frozen=True, slots=True)
class Measurement:
    """One timed run of the gate."""

    profile: str
    seconds: float
    budget: float
    status: int

    @property
    def within_budget(self) -> bool:
        """Return whether the run finished inside its declared budget."""
        return self.seconds <= self.budget

    def as_json(self) -> str:
        """Return the measurement as one JSON object, for a workflow to publish."""
        return json.dumps(
            {
                "profile": self.profile,
                "seconds": round(self.seconds, 1),
                "budget_seconds": self.budget,
                "within_budget": self.within_budget,
                "gate_passed": self.status == 0,
            }
        )


def measure(profile: str, *, make: str | None = None) -> Measurement:
    """Run the gate once and return how long it took against its budget."""
    executable = make or shutil.which("make") or "make"
    started = time.monotonic()
    finished = subprocess.run([executable, "verify"], cwd=REPO_ROOT, check=False)
    elapsed = time.monotonic() - started
    return Measurement(
        profile=profile,
        seconds=elapsed,
        budget=BUDGETS[profile],
        status=finished.returncode,
    )


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="measure_verify", description=__doc__)
    parser.add_argument("--profile", choices=tuple(BUDGETS), default="warm")
    parser.add_argument(
        "--json", action="store_true", help="print one JSON object and nothing else"
    )
    arguments = parser.parse_args(argv)

    measurement = measure(arguments.profile)

    if arguments.json:
        print(measurement.as_json())
    else:
        print(
            f"{measurement.profile} `make verify`: {measurement.seconds:.0f}s "
            f"against a budget of {measurement.budget:.0f}s"
        )

    if measurement.status != 0:
        print("the gate failed; the timing above is not a verdict on its speed", file=sys.stderr)
        return 1
    if not measurement.within_budget:
        print(
            f"the {measurement.profile} gate took {measurement.seconds:.0f}s, over its "
            f"{measurement.budget:.0f}s budget. A gate people stop running is a gate that "
            f"does not exist.",
            file=sys.stderr,
        )
        return EXIT_OVER_BUDGET
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
