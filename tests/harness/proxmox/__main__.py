"""The command line the gate and a contributor both use.

One entry point, three things it does: run the corpus and print the report, gate
that run against the committed baseline, or re-record the baseline so the change
can be reviewed as a change. Anything a contributor can do here, CI does with the
same code, because two paths to one number is two numbers.

Exit codes are the interface CI reads: nought when the run is at or above its
baseline, one when it regressed, two when a scenario's fixtures no longer match
the system. The third is separate on purpose — a stale fixture is not a
regression in the agent and telling somebody it is sends them to the wrong file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from tests.harness.proxmox.baseline import Regressed, baseline_path, gate, read_baseline
from tests.harness.proxmox.baseline import write_baseline as store_baseline
from tests.harness.proxmox.coverage import describe as describe_coverage
from tests.harness.proxmox.coverage import uncovered
from tests.harness.proxmox.readings import StaleFixture
from tests.harness.proxmox.report import SuiteReport
from tests.harness.proxmox.suite import CORPUS_ROOT, load_corpus, run_suite

EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_STALE = 2


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.harness.proxmox",
        description="Run the Proxmox scenario suite from recorded fixtures.",
    )
    parser.add_argument("--corpus", default=str(CORPUS_ROOT), help="where the scenarios live")
    parser.add_argument("--domain", default="", help="only scenarios whose domain matches")
    parser.add_argument("--scenario", default="", help="only scenarios whose identifier matches")
    parser.add_argument("--record", action="store_true", help="store this run as the baseline")
    parser.add_argument("--note", default="", help="why the baseline moved, stored with it")
    parser.add_argument("--coverage", action="store_true", help="print the capability coverage")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser.parse_args(argv)


def _print_report(report: SuiteReport) -> None:
    """Print the run in the shape somebody reads at a terminal."""
    print(
        f"{report.passes}/{report.total} scored runs passed "
        f"({report.pass_rate:.1%}) in {report.duration_seconds:.2f}s"
    )
    for cell in report.cells():
        print(
            f"  {cell.model}/{cell.arm}: {cell.passes}/{cell.scored} "
            f"({cell.pass_rate:.1%}), harmful {cell.harmful}, could not finish {cell.incomplete}"
        )
    for mode, names in report.modes().items():
        print(f"  {mode}: {len(names)} scenario(s)")
    for score in report.scenarios:
        if score.passed:
            continue
        print(f"  FAILED {score.scenario_id} [{score.cell}] {score.diagnosis}/{score.action}")
        for line in score.reasoning:
            print(f"      {line}")


def main(argv: list[str] | None = None) -> int:
    """Run the suite and return the exit code CI reads."""
    options = _arguments(argv)
    root = Path(options.corpus)

    if options.coverage:
        corpus = load_corpus(root)
        print(describe_coverage(corpus))
        missing = uncovered(corpus)
        if missing:
            print(f"\nno scenario exercises: {', '.join(missing)}", file=sys.stderr)
            return EXIT_REGRESSED
        return EXIT_OK

    try:
        report = asyncio.run(run_suite(root, domain=options.domain, scenario=options.scenario))
    except StaleFixture as stale:
        print(f"stale fixture: {stale}", file=sys.stderr)
        return EXIT_STALE

    if options.json:
        print(json.dumps(report.to_artifact(), indent=2, sort_keys=True))
    else:
        _print_report(report)

    if options.record:
        written = store_baseline(report, baseline_path(root), note=options.note)
        print(f"baseline written to {written}")
        return EXIT_OK

    try:
        gate(report, read_baseline(baseline_path(root)))
    except Regressed as regressed:
        print(str(regressed), file=sys.stderr)
        return EXIT_REGRESSED
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    raise SystemExit(main())
