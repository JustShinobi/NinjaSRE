"""The command-line front door, over the same loader and the same executor.

``make test-synthetic`` and the pytest gate run one corpus through one code
path. A CLI that assembled its own would be a second number nobody could
reconcile with the first, and the first time they disagreed the argument would
be about which one to believe rather than about the agent.

Offline by default. Running the suite should cost nothing unless somebody asked
for it to cost something, and the scenarios that carry no transcript are
reported as skipped rather than silently dropped — a corpus that quietly shrank
is a score that quietly moved.

Usage::

    python -m tests.harness                       # the whole corpus, offline
    python -m tests.harness --difficulty 4        # one rung of the ladder
    python -m tests.harness --scenario liveness   # one scenario
    python -m tests.harness --attempts 5          # variance
    python -m tests.harness --json                # for a CI job to publish
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from config.constants.evaluation import DEFAULT_SCENARIO_ATTEMPTS
from tests.harness.loader import Scenario
from tests.harness.offline import TranscriptPlayer, load_transcript
from tests.harness.runner import ScenarioRun, scenario_summary
from tests.harness.suite import SuiteReport, load_suite, report_for, run_suite

#: Where the corpus lives, relative to the repository root.
DEFAULT_CORPUS_ROOT = Path(__file__).resolve().parents[1] / "synthetic"


def _offline_provider(scenario: Scenario, attempt: int) -> TranscriptPlayer:
    """Return the recorded provider for ``scenario``."""
    if scenario.transcript_path is None:  # pragma: no cover - filtered before here
        raise SystemExit(f"{scenario.key}: no recorded transcript, so it cannot run offline")
    return TranscriptPlayer(load_transcript(scenario.transcript_path))


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tests.harness",
        description="Run the synthetic scenario corpus.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT, help="corpus root")
    parser.add_argument("--suite", default="", help="only suites whose name contains this")
    parser.add_argument("--scenario", default="", help="only scenarios whose id contains this")
    parser.add_argument("--difficulty", type=int, default=None, help="only this curriculum level")
    parser.add_argument("--integration", default="", help="only scenarios using this integration")
    parser.add_argument(
        "--attempts",
        type=int,
        default=DEFAULT_SCENARIO_ATTEMPTS,
        help="attempts per scenario, for variance",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="write a JSONL verdict record per attempt to this file",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--list", action="store_true", help="list what would run and stop")
    return parser.parse_args(argv)


def _print_report(report: SuiteReport) -> None:
    """Print the run, by level then by scenario, so the gradient reads first."""
    print()
    print(f"{'level':<6}{'solve rate':<12}{'attempts':<10}definition")
    for level in report.by_difficulty():
        rate = f"{level.solve_rate:.0%}"
        print(f"{level.difficulty:<6}{rate:<12}{level.attempts:<10}{level.description}")

    print()
    for found in report.scenarios:
        mark = "ok  " if found.passes == found.attempts else "FAIL"
        rate = f"{found.passes}/{found.attempts}"
        detail = ", ".join(found.failed_axes) if found.failed_axes else ""
        print(f"  {mark} [{found.difficulty}] {found.key:<48}{rate:<8}{detail}")

    print()
    print(
        f"{report.passes}/{report.attempts} attempts passed "
        f"({report.solve_rate:.0%}) in {report.duration_seconds:.1f}s"
    )
    for found in report.permanently_unsolved:
        print(f"  never solved: {found.key} — a target once, and noise afterwards")
    # Only meaningful once a scenario has been attempted more than once: at one
    # attempt every passing scenario is "always solved", which says nothing.
    for found in report.trivially_solved:
        if found.attempts > 1:
            print(f"  always solved: {found.key} — no longer discriminating")


async def _run(options: argparse.Namespace) -> SuiteReport:
    scenarios = load_suite(
        options.root,
        suite=options.suite,
        scenario_id=options.scenario,
        difficulty=options.difficulty,
        integration=options.integration,
    )
    runnable = [found for found in scenarios if found.offline_ready]
    for skipped in [found for found in scenarios if not found.offline_ready]:
        print(f"  skipped: {skipped.key} — no recorded transcript, so it cannot run offline")

    def observe(run: ScenarioRun) -> None:
        summary: dict[str, Any] = scenario_summary(run)
        print(
            f"  ran {summary['scenario']} attempt {summary['attempt']} "
            f"in {summary['duration_seconds']}s"
        )

    from tests.harness.artifacts import ArtifactWriter

    writer = ArtifactWriter(path=options.artifacts) if options.artifacts else None
    result = await run_suite(
        runnable, provider=_offline_provider, attempts=options.attempts, observer=observe
    )
    return report_for(result, writer=writer)


def main(argv: list[str] | None = None) -> int:
    """Run the corpus and return the process exit status."""
    options = _arguments(argv)

    if options.list:
        for found in load_suite(
            options.root,
            suite=options.suite,
            scenario_id=options.scenario,
            difficulty=options.difficulty,
            integration=options.integration,
        ):
            print(f"[{found.difficulty}] {found.key:<48}{found.failure_mode}")
        return 0

    report = asyncio.run(_run(options))
    if options.json:
        print(json.dumps(report.to_record(), indent=2))
    else:
        _print_report(report)
    return 0 if report.attempts and report.passes == report.attempts else 1


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    sys.exit(main())
