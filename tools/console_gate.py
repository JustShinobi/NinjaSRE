"""The console's half of ``make verify``, one check at a time.

Every check is individually runnable, because a contributor iterating on a type
error should not have to sit through a browser suite to see whether they fixed
it. ``all`` runs them in the order that reports the cheapest failure first,
which is the same principle the Python half of the gate is ordered by.

**Skipping, and why it is bounded.** Two checks need infrastructure a machine
may not have: the browser suite needs a Node toolchain that has to be fetched
once, and the visual suite needs a container runtime. On a machine without them
this reports a named skip and returns success, in the same way the chaos and
cloud suites already do — a gate that goes red for a reason the contributor
cannot act on is a gate they learn to bypass. CI sets
``NINJASRE_CONSOLE_TOOLCHAIN=required``, and then a skip is a failure. So the
gate is complete where it is enforced and honest where it is not.

Three things are never skipped, whatever the environment:

- a lockfile that has drifted from its manifest;
- a committed API client that differs from a fresh generation;
- a check that ran and failed.

Usage::

    python -m tools.console_gate all
    python -m tools.console_gate typecheck

Exits 0 when the requested checks passed or were skipped by policy, 1 when one
of them failed.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from config.constants.console import (
    CONSOLE_GENERATED_CLIENT_PATH,
    NINJASRE_CONSOLE_TOOLCHAIN_ENV,
)
from tools.console_budget import EXIT_NOTHING_TO_MEASURE
from tools.console_toolchain import (
    StaleLockfile,
    Toolchain,
    ToolchainError,
    console_root,
    install_dependencies,
    resolve,
    run_pnpm,
)

#: The value of ``NINJASRE_CONSOLE_TOOLCHAIN`` that turns a skip into a failure.
REQUIRED: Final = "required"


@dataclass(frozen=True, slots=True)
class Check:
    """One check, the pnpm script behind it, and what it is called at the gate."""

    name: str
    script: str
    describes: str


#: The checks that are a pnpm script and nothing more, cheapest first.
SCRIPTED: Final[tuple[Check, ...]] = (
    Check("format-check", "format:check", "formatting"),
    Check("lint", "lint", "lint rules"),
    Check("typecheck", "typecheck", "types"),
    Check("test", "test", "unit tests and coverage"),
    Check("build", "build", "the production build"),
)

#: Every check name ``all`` runs, in order.
ORDER: Final[tuple[str, ...]] = (
    "lockfile",
    "format-check",
    "lint",
    "typecheck",
    "test",
    "client-check",
    "build",
    "budget",
    "e2e",
    "visual",
)


def toolchain_required() -> bool:
    """Return whether a missing toolchain is a failure rather than a skip."""
    return os.environ.get(NINJASRE_CONSOLE_TOOLCHAIN_ENV, "").strip().lower() == REQUIRED


def _skip(reason: str) -> int:
    """Report a check that could not run, and return the status the policy demands."""
    if toolchain_required():
        print(
            f"console gate: {reason}\n"
            f"  {NINJASRE_CONSOLE_TOOLCHAIN_ENV}={REQUIRED} is set, so this is a failure.",
            file=sys.stderr,
        )
        return 1
    print(
        f"console gate: skipped — {reason}\n"
        f"  Run `make console-setup` to provision it, or set "
        f"{NINJASRE_CONSOLE_TOOLCHAIN_ENV}={REQUIRED} to make this a failure.",
        file=sys.stderr,
    )
    return 0


def _fail(check: str, detail: str) -> int:
    """Report a check that ran and failed, naming it."""
    print(f"console gate: {check} failed — {detail}", file=sys.stderr)
    return 1


def _toolchain() -> Toolchain | None:
    """Return the provisioned toolchain, or ``None`` when there is not one."""
    try:
        return resolve()
    except ToolchainError:
        return None


def lockfile(toolchain: Toolchain) -> int:
    """Install from the committed lockfile, frozen. A drifted lockfile fails here."""
    try:
        install_dependencies(toolchain)
    except StaleLockfile as error:
        return _fail("lockfile", str(error))
    except ToolchainError as error:
        return _skip(f"the console's dependencies could not be installed: {error}")
    return 0


def scripted(check: Check, toolchain: Toolchain) -> int:
    """Run one pnpm script and return the gate's verdict on it."""
    status = run_pnpm(["run", check.script], toolchain, check=False)
    if status != 0:
        return _fail(check.name, f"{check.describes} — see the output above")
    return 0


def client_check(toolchain: Toolchain) -> int:
    """Fail when the committed API client differs from a fresh generation.

    Generated from the committed copy of the gateway's OpenAPI document, so this
    runs with no network and no running gateway. The document itself is kept
    equal to what the application produces by the fixture suite, which means a
    route that changed shape reaches the console as a failing build rather than
    as a client that compiles and 404s.
    """
    committed = console_root() / CONSOLE_GENERATED_CLIENT_PATH
    before = committed.read_text(encoding="utf-8") if committed.is_file() else ""

    status = run_pnpm(["run", "client"], toolchain, check=False)
    if status != 0:
        return _fail("client-check", "the client could not be generated")

    after = committed.read_text(encoding="utf-8")
    if after == before:
        return 0

    committed.write_text(before, encoding="utf-8")
    difference = "\n".join(
        list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"{CONSOLE_GENERATED_CLIENT_PATH} (committed)",
                tofile=f"{CONSOLE_GENERATED_CLIENT_PATH} (generated)",
                lineterm="",
            )
        )[:40]
    )
    return _fail(
        "client-check",
        f"{CONSOLE_GENERATED_CLIENT_PATH} is not what the API document generates. "
        f"Run `make console-client` and commit the result.\n{difference}",
    )


def _module(name: str, arguments: Sequence[str]) -> int:
    """Run one of this repository's own modules and return its exit status."""
    finished = subprocess.run(
        [sys.executable, "-m", name, *arguments],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    return finished.returncode


def budget() -> int:
    """Fail when the compiled stylesheet or the icon set is over its budget.

    Needs the build, so it runs straight after it. A design system whose
    stylesheet has doubled is a design system whose components have started
    writing their own values, and that shows up here before it shows up as two
    cards with different padding.
    """
    status = _module("tools.console_budget", [])
    if status == EXIT_NOTHING_TO_MEASURE:
        return _skip("there is no console build to measure")
    if status != 0:
        return _fail("budget", "a bundle is over its declared budget — see the output above")
    return 0


def end_to_end() -> int:
    """Drive a browser against the built console and the committed dataset."""
    status = _module("tools.console_e2e", ["run"])
    if status == 2:
        return _skip("the end-to-end backing could not be started")
    if status != 0:
        return _fail("e2e", "a browser test failed — see the output above")
    return 0


def visual() -> int:
    """Compare every registered screen against its committed baseline."""
    if shutil.which("docker") is None:
        return _skip(
            "the visual baselines are captured in one pinned container image and this "
            "machine has no container runtime, so there is nothing meaningful to compare"
        )
    status = _module("tools.console_visual", ["compare"])
    if status == 2:
        return _skip("the capture image could not be run")
    if status != 0:
        return _fail("visual", "a screen differs from its baseline — see the diff artefacts")
    return 0


def one(name: str) -> int:
    """Run the check called ``name`` and return the gate's verdict."""
    if name == "visual":
        return visual()

    toolchain = _toolchain()
    if toolchain is None:
        return _skip("the console toolchain is not provisioned")

    if name == "lockfile":
        return lockfile(toolchain)
    if name == "client-check":
        return client_check(toolchain)
    if name == "budget":
        return budget()
    if name == "e2e":
        return end_to_end()
    for check in SCRIPTED:
        if check.name == name:
            return scripted(check, toolchain)
    raise SystemExit(f"console gate: {name} is not a check")


def every() -> int:
    """Run the whole console gate, stopping at the first failure."""
    for name in ORDER:
        status = one(name)
        if status != 0:
            return status
    return 0


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_gate", description=__doc__)
    parser.add_argument("check", choices=("all", *ORDER))
    arguments = parser.parse_args(argv)
    return every() if arguments.check == "all" else one(arguments.check)


if __name__ == "__main__":
    raise SystemExit(_main())
