"""Time the path from a clean machine to a deployment that can investigate.

That path has a ten-minute budget on a clean machine, on all three platforms.
Most of it is deterministic and can be measured in CI on every pull request; one
leg is not, and this script is explicit about which is which rather than
reporting a number that quietly excludes the slow part.

**Measured here.** Building the distribution, installing it into an empty
environment, and the four things an operator does before they can investigate
anything: the command runs, it reports its version, it can describe its own
failure modes, and it can diagnose a deployment. Every one of these is a
subprocess against a real install, because an in-process import proves the
package imports and proves nothing about whether the console script works —
which is exactly the thing that breaks, on Windows, in a way nothing else
notices.

**Not measured here.** Entering a provider credential and running an
investigation that comes back. That leg spends real tokens against an
operator's own endpoint, which is why this repository keeps it in
``make preflight`` rather than in the gate. What this script reports is the
budget *remaining* for it, which is the number an operator actually needs: "you
have nine minutes and forty seconds left for the part that depends on your
provider" is an answer, and a total that pretended to include it is not.

Usage::

    python tools/measure_first_investigation.py
    python tools/measure_first_investigation.py --json

Exits 0 when the measured path fits its share of the budget, 1 when it does not.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The whole budget for the path, in seconds.
TOTAL_BUDGET_SECONDS = 600.0

#: What the deterministic legs may take. The remainder is left for the operator
#: choosing a provider, finding their key, and running the first investigation —
#: which is where the time should go, and where a slow install steals it from.
SETUP_BUDGET_SECONDS = 300.0

#: Exit codes this script treats as "the command worked". ``doctor`` against a
#: machine with nothing configured is *supposed* to report that it cannot
#: investigate yet; a zero there would mean the diagnosis is not diagnosing.
CONFIGURATION_EXIT = 3
GENERIC_FAILURE_EXIT = 1


@dataclass(frozen=True, slots=True)
class Leg:
    """One measured step of the path."""

    name: str
    seconds: float
    ok: bool
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this leg as a JSON-serialisable document."""
        return {
            "name": self.name,
            "seconds": round(self.seconds, 3),
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass(slots=True)
class Measurement:
    """Every leg, and what the whole path came to."""

    legs: list[Leg] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        """Return the total measured time."""
        return sum(leg.seconds for leg in self.legs)

    @property
    def ok(self) -> bool:
        """Return whether every leg worked and the total fits its budget."""
        return all(leg.ok for leg in self.legs) and self.seconds <= SETUP_BUDGET_SECONDS

    @property
    def remaining_seconds(self) -> float:
        """Return what is left of the budget for the provider-dependent leg."""
        return max(TOTAL_BUDGET_SECONDS - self.seconds, 0.0)

    def to_record(self) -> dict[str, Any]:
        """Return this measurement as a JSON-serialisable document."""
        return {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "legs": [leg.to_record() for leg in self.legs],
            "measured_seconds": round(self.seconds, 3),
            "setup_budget_seconds": SETUP_BUDGET_SECONDS,
            "total_budget_seconds": TOTAL_BUDGET_SECONDS,
            "remaining_for_first_investigation_seconds": round(self.remaining_seconds, 3),
            "ok": self.ok,
        }

    def render(self) -> str:
        """Return the human report."""
        width = max(len(leg.name) for leg in self.legs) if self.legs else 0
        lines = [f"{'leg'.ljust(width)}  seconds  outcome", ""]
        for leg in self.legs:
            mark = "ok" if leg.ok else "FAILED"
            lines.append(
                f"{leg.name.ljust(width)}  {leg.seconds:7.2f}  {mark} {leg.detail}".rstrip()
            )
        lines.extend(
            (
                "",
                f"measured   {self.seconds:7.2f}s  (budget {SETUP_BUDGET_SECONDS:.0f}s)",
                f"remaining  {self.remaining_seconds:7.2f}s  for entering a credential and "
                f"running the first investigation",
                "",
                "The remaining leg spends real tokens against your own provider and is "
                "measured by 'make preflight'.",
            )
        )
        return "\n".join(lines)


def _time(name: str, work: Sequence[str], *, expect: Sequence[int] = (0,)) -> Leg:
    """Run ``work`` and return how long it took and whether it worked."""
    started = time.perf_counter()
    result = subprocess.run(work, capture_output=True, text=True, check=False)
    elapsed = time.perf_counter() - started

    ok = result.returncode in expect
    detail = "" if ok else f"exit {result.returncode}: {result.stderr.strip()[:200]}"
    return Leg(name=name, seconds=elapsed, ok=ok, detail=detail)


def _script(environment: Path) -> Path:
    """Return the path of the installed ``ninjasre`` command."""
    if sys.platform == "win32":
        return environment / "Scripts" / "ninjasre.exe"
    return environment / "bin" / "ninjasre"


def _python(environment: Path) -> Path:
    """Return the path of the environment's interpreter."""
    if sys.platform == "win32":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def measure(*, keep: bool = False) -> Measurement:
    """Return how long the deterministic part of the path takes on this machine."""
    measurement = Measurement()
    workspace = Path(tempfile.mkdtemp(prefix="ninjasre-first-run-"))

    try:
        # An empty environment. The whole point of "a clean machine": an install
        # that only works where the developer's site-packages already has six of
        # its dependencies is not an install anybody else can reproduce.
        #
        # Built with ``with_pip`` because the environment's own pip is what does
        # the install below. Reaching for the *running* interpreter's pip would
        # measure whatever the developer happens to have, and this repository's
        # own environment is managed by uv and has none.
        started = time.perf_counter()
        environment = workspace / "env"
        venv.create(environment, with_pip=True, clear=True)
        measurement.legs.append(
            Leg(name="create an empty environment", seconds=time.perf_counter() - started, ok=True)
        )

        # Build and install in one step, because that is one step for the person
        # doing it. Splitting them would report two numbers for something nobody
        # experiences as two things.
        measurement.legs.append(
            _time(
                "build and install",
                [
                    str(_python(environment)),
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--disable-pip-version-check",
                    str(REPO_ROOT),
                ],
            )
        )

        command = str(_script(environment))
        if not Path(command).exists():
            measurement.legs.append(
                Leg(
                    name="the command runs",
                    seconds=0.0,
                    ok=False,
                    detail=f"no console script at {command}",
                )
            )
            return measurement

        measurement.legs.append(_time("the command runs", [command, "--version"]))
        measurement.legs.append(_time("it documents its exit codes", [command, "--exit-codes"]))
        measurement.legs.append(_time("it describes itself", [command, "--help"]))

        # ``doctor`` on a machine with nothing configured has to *say so*
        # rather than succeed. A zero here would mean the diagnosis is not
        # diagnosing, which is the failure mode that matters most.
        measurement.legs.append(
            _time(
                "it diagnoses an unconfigured machine",
                [command, "--json", "doctor"],
                expect=(CONFIGURATION_EXIT, GENERIC_FAILURE_EXIT),
            )
        )
        return measurement
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the path and report it. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the measurement as JSON.")
    parser.add_argument("--keep", action="store_true", help="Leave the workspace behind.")
    arguments = parser.parse_args(argv)

    measurement = measure(keep=arguments.keep)

    if arguments.json:
        print(json.dumps(measurement.to_record(), indent=2, sort_keys=True))
    else:
        print(measurement.render())

    return 0 if measurement.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
