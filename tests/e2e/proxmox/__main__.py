"""Run the destructive half and print what was real.

Prints the plan and the outcome, and returns nought unless the laboratory did
not come back. It is safe to run with no cluster: the recorded stand-in answers,
and the report says every scenario was simulated — which is the sentence a
release note needs and the sentence somebody would otherwise write wrongly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from tests.e2e.proxmox.rehearsal import describe as describe_rehearsals
from tests.e2e.proxmox.suite import run_laboratory, skip_reason
from tests.harness.proxmox.laboratory import LaboratoryUnusable

EXIT_OK = 0
EXIT_UNUSABLE = 1


def main(argv: list[str] | None = None) -> int:
    """Run the laboratory suite and return the exit code CI reads."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.e2e.proxmox",
        description="Run the destructive Proxmox scenarios against the laboratory cluster.",
    )
    parser.add_argument("--plan", action="store_true", help="print the rehearsals and stop")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    options = parser.parse_args(argv)

    if options.plan:
        print(describe_rehearsals())
        return EXIT_OK

    reason = skip_reason()
    if reason:
        print(f"note: {reason}", file=sys.stderr)

    try:
        report = asyncio.run(run_laboratory())
    except LaboratoryUnusable as unusable:
        print(str(unusable), file=sys.stderr)
        return EXIT_UNUSABLE

    print(
        json.dumps(report.to_record(), indent=2, sort_keys=True)
        if options.json
        else report.describe()
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    raise SystemExit(main())
