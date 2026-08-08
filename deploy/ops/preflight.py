"""Check a deployment's configuration before starting it, and say what is wrong.

The same validation the boot sequence runs, run on its own. That is the point:
an operator editing ``.env`` should not have to start four containers to find
out they have a typo, and a check that duplicated the rules would be a check
that eventually disagrees with the thing it stands in for.

Reports everything at once — one restart per problem is how a ten-minute setup
becomes an hour — and names the setting and the remedy for each.

Also prints what the configuration implies about egress, which is the question
Article X makes worth answering before anything runs: every destination this
deployment may reach, derived from a setting, with the setting named.

And it runs the self-check — the same one the console and ``ninjasre setup
self-check`` run, extended here rather than reimplemented, because a third
checker is a third thing to keep in step. The checks that need no store run
whatever the state of the machine; the ones that do are reported as "not
checked" rather than as passes, since a green tick for something nobody looked
at is worse than an honest gap.

Usage::

    python deploy/ops/preflight.py
    python deploy/ops/preflight.py --json

Exits 0 when the configuration will start, 3 when it will not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.startup.egress import configured_destinations  # noqa: E402
from platform.startup.errors import UnknownDeploymentProfile  # noqa: E402
from platform.startup.profiles import resolve_topology  # noqa: E402
from platform.startup.selfcheck import (  # noqa: E402
    SelfCheckReport,
    clock_skew_check,
    disk_space_check,
    run_checks,
)
from platform.startup.setup import first_run_plan  # noqa: E402
from platform.startup.validation import validate  # noqa: E402

#: What a configuration that will not start exits with. Matches the server's
#: own, so a wrapper can treat the two the same way.
CONFIGURATION_EXIT = 3


def _self_check_findings() -> SelfCheckReport:
    """Return the part of the self-check that needs nothing running.

    Preflight runs before the deployment does, so the store, the proxy and the
    provider are all legitimately absent — reporting them as problems here would
    make every clean preflight red. What is left is the pair that is about the
    *host*, and the host is exactly what preflight is for.
    """
    return asyncio.run(run_checks((disk_space_check(), clock_skew_check())))


def main(argv: Sequence[str] | None = None) -> int:
    """Print the preflight report and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the documented JSON shape")
    arguments = parser.parse_args(argv)

    report = validate()
    destinations = configured_destinations()
    findings = _self_check_findings()

    try:
        topology = resolve_topology()
    except UnknownDeploymentProfile:
        topology = None

    if arguments.json:
        print(  # noqa: T201 — a machine is reading this
            json.dumps(
                {
                    "validation": report.to_record(),
                    "topology": None if topology is None else topology.to_record(),
                    "egress": [destination.to_record() for destination in destinations],
                    "self_check": findings.to_record(),
                },
                indent=2,
            )
        )
        return 0 if report.ok and findings.ok else CONFIGURATION_EXIT

    if topology is not None:
        print(topology.summary())  # noqa: T201 — a person is reading this
        print()  # noqa: T201
    print(report.summary())  # noqa: T201
    print()  # noqa: T201
    print(findings.summary())  # noqa: T201
    print()  # noqa: T201
    print("This configuration permits outbound connections to:")  # noqa: T201
    for destination in destinations:
        marker = "on-host" if destination.on_host else "LEAVES THE HOST"
        print(f"  [{marker}] {destination}")  # noqa: T201

    if report.ok and topology is not None:
        print()  # noqa: T201
        print(first_run_plan(topology.profile).summary())  # noqa: T201

    return 0 if report.ok and findings.ok else CONFIGURATION_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
