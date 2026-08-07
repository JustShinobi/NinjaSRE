"""The entry point a scheduled job runs: score the corpus, compare, exit non-zero.

One command does the whole thing — run the corpus offline, score every attempt on
all five axes, compare against a named baseline, and fail with the scenarios and
axes named. Splitting it across three commands and a temporary file would put the
interesting part (which baseline?) in a shell script nobody reviews.

Offline by default, and that is what makes the gate affordable enough to run at
all. A gate that spent tokens on every schedule is a gate somebody eventually
turns off, and a gate nobody runs gates nothing.

``--record`` is the other half of FR-021. Establishing a baseline is the same
measurement as checking against one, so it is the same command with a different
flag rather than a second path that could drift away from the first.

Usage::

    python -m tests.harness.regression.ci --record v0.28.0
    python -m tests.harness.regression.ci --baseline v0.28.0 --attempts 5
    python -m tests.harness.regression.ci --list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from config.constants.evaluation import DEFAULT_SCENARIO_ATTEMPTS
from tests.harness.loader import Scenario
from tests.harness.offline import TranscriptPlayer, load_transcript
from tests.harness.regression.baseline import Baseline, BaselineStore, UnknownBaseline
from tests.harness.regression.compare import compare
from tests.harness.regression.gate import GatePolicy, GateResult, evaluate
from tests.harness.scoring.composite import score_run
from tests.harness.scoring.report import SuiteScore, corpus_version, summarise
from tests.harness.suite import load_suite, run_suite

#: Where the corpus lives, relative to the repository root.
DEFAULT_CORPUS_ROOT = Path(__file__).resolve().parents[2] / "synthetic"

#: Where baselines live when nobody says otherwise. Beside the corpus, because a
#: baseline is only meaningful against the corpus it was measured over and the
#: two should move together in a checkout.
DEFAULT_BASELINE_ROOT = Path(__file__).resolve().parents[2] / "synthetic" / "baselines"


def _offline_provider(scenario: Scenario, attempt: int) -> TranscriptPlayer:
    """Return the recorded provider for ``scenario``."""
    if scenario.transcript_path is None:  # pragma: no cover - filtered before here
        raise SystemExit(f"{scenario.key}: no recorded transcript, so it cannot run offline")
    return TranscriptPlayer(load_transcript(scenario.transcript_path))


async def measure(
    root: Path, *, attempts: int = DEFAULT_SCENARIO_ATTEMPTS, label: str = ""
) -> SuiteScore:
    """Return the corpus under ``root``, run offline and scored on all five axes."""
    scenarios = [found for found in load_suite(root) if found.offline_ready]
    result = await run_suite(scenarios, provider=_offline_provider, attempts=attempts)
    return summarise(
        [score_run(run) for run in result.runs],
        label=label,
        corpus_version=corpus_version(found.key for found in scenarios),
        duration_seconds=result.duration_seconds,
    )


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tests.harness.regression.ci",
        description="Score the scenario corpus and gate it against a stored baseline.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT, help="corpus root")
    parser.add_argument(
        "--baselines", type=Path, default=DEFAULT_BASELINE_ROOT, help="where baselines are stored"
    )
    parser.add_argument("--baseline", default="", help="the stored baseline to gate against")
    parser.add_argument("--record", default="", help="store this run as a baseline under this name")
    parser.add_argument("--note", default="", help="what a recorded baseline is, in one sentence")
    parser.add_argument(
        "--attempts",
        type=int,
        default=DEFAULT_SCENARIO_ATTEMPTS,
        help="attempts per scenario, for variance",
    )
    parser.add_argument("--list", action="store_true", help="list stored baselines and stop")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument(
        "--allow-corpus-change",
        action="store_true",
        help="compare across a corpus change, which mixes fixture edits with agent behaviour",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the gate and return the process exit status."""
    options = _arguments(argv)
    store = BaselineStore(root=options.baselines)

    if options.list:
        for identifier in store.identifiers():
            stored = store.load(identifier)
            print(
                f"{identifier:<20}{stored.recorded_at:<26}corpus {stored.corpus_version} "
                f"{stored.note}"
            )
        return 0

    if not options.baseline and not options.record:
        print(
            "nothing to do: pass --baseline to gate against a stored run, or --record to "
            "establish one. A comparison with no baseline is a pass rate wearing a delta's name.",
            file=sys.stderr,
        )
        return 2

    current = asyncio.run(
        measure(
            options.root,
            attempts=options.attempts,
            label=options.record or "working tree",
        )
    )

    if options.record:
        path = store.save(Baseline(identifier=options.record, suite=current, note=options.note))
        print(current.render())
        print()
        print(f"recorded baseline {options.record!r} at {path}")
        return 0

    try:
        stored = store.load(options.baseline)
    except UnknownBaseline as error:
        print(str(error), file=sys.stderr)
        return 2

    result = _gate(stored, current, allow_corpus_change=options.allow_corpus_change)
    if options.json:
        print(json.dumps(result.to_record(), indent=2))
    else:
        print(current.render())
        print()
        print(result.render())
    return result.exit_code


def _gate(stored: Baseline, current: SuiteScore, *, allow_corpus_change: bool) -> GateResult:
    """Return the gate's decision, or a corpus-change failure it can report."""
    from tests.harness.regression.compare import CorpusMismatch

    try:
        comparison = compare(stored.suite, current, strict_corpus=not allow_corpus_change)
    except CorpusMismatch as error:
        raise SystemExit(
            f"{error}\n\nRe-record the baseline with --record once the corpus change is "
            f"intended, so the number a release publishes says which corpus produced it."
        ) from error
    return evaluate(comparison, GatePolicy())


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    sys.exit(main())
