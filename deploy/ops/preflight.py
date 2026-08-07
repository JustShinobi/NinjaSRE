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

Usage::

    python deploy/ops/preflight.py
    python deploy/ops/preflight.py --json

Exits 0 when the configuration will start, 3 when it will not.
"""

from __future__ import annotations

import argparse
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
from platform.startup.setup import first_run_plan  # noqa: E402
from platform.startup.validation import validate  # noqa: E402

#: What a configuration that will not start exits with. Matches the server's
#: own, so a wrapper can treat the two the same way.
CONFIGURATION_EXIT = 3


def main(argv: Sequence[str] | None = None) -> int:
    """Print the preflight report and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the documented JSON shape")
    arguments = parser.parse_args(argv)

    report = validate()
    destinations = configured_destinations()

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
                },
                indent=2,
            )
        )
        return 0 if report.ok else CONFIGURATION_EXIT

    if topology is not None:
        print(topology.summary())  # noqa: T201 — a person is reading this
        print()  # noqa: T201
    print(report.summary())  # noqa: T201
    print()  # noqa: T201
    print("This configuration permits outbound connections to:")  # noqa: T201
    for destination in destinations:
        marker = "on-host" if destination.on_host else "LEAVES THE HOST"
        print(f"  [{marker}] {destination}")  # noqa: T201

    if report.ok and topology is not None:
        print()  # noqa: T201
        print(first_run_plan(topology.profile).summary())  # noqa: T201

    return 0 if report.ok else CONFIGURATION_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
