"""Turning a benchmark run into the table that leaves the repository.

This is the last step and the one with the most ways to go quietly wrong, because
what it produces is read by people who will never see the run that produced it.
Three rules follow from that.

**Every table carries its provenance.** Which runtime, which corpus version, when.
A number without those is a number nobody can defend when somebody else measures
something different — and Article V's whole argument is that the runtime is part
of the measurement.

**Splicing never eats the document.** An export writes between two comment
markers and leaves everything else alone. An exporter that overwrote a README
would be used exactly once.

**Markdown and JSON, from one record.** The table is for a person; the record is
for whatever plots the trend. Generating the second from the first, or keeping two
sources, is how the plotted number and the published number drift apart.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from config.constants.evaluation import (
    BENCHMARK_TABLE_BEGIN,
    BENCHMARK_TABLE_END,
    DEFAULT_SCENARIO_ATTEMPTS,
)
from config.constants.investigation import RUNTIME_CANONICAL
from tests.benchmarks.adapter import BenchmarkRun
from tests.benchmarks.models.comparison import ModelComparison
from tests.harness.scoring.report import SuiteScore

#: The table's columns, in the order a reader wants them: who, how well, how
#: dearly. Score first after the identity, because that is what the table is for.
COLUMNS: tuple[str, ...] = ("Provider", "Model", "Solved", "Score", "Tokens", "Seconds")


def markdown_table(runs: Sequence[BenchmarkRun]) -> str:
    """Return ``runs`` as a Markdown table, best score first.

    Ordered by score rather than by provider name, because the question a reader
    brings to this table is "which one", and alphabetical order answers a
    question nobody asked.
    """
    header = f"| {' | '.join(COLUMNS)} |"
    divider = f"|{'|'.join('---' for _ in COLUMNS)}|"
    rows = [
        f"| {run.provider_id} | {run.model_id or '—'} | {run.solved}/{run.total} | "
        f"{run.score:.0%} | {run.tokens} | {run.seconds:.1f} |"
        for run in sorted(runs, key=lambda run: (-run.score, run.provider_id))
    ]
    return "\n".join([header, divider, *rows])


def provenance_line(
    *,
    runtime: str,
    corpus_version: str,
    model_set: Sequence[str] = (),
    at: datetime | None = None,
) -> str:
    """Return the one line every published table carries beneath it.

    ``model_set`` is every distinct model the measured runs used, and it is here
    because a deployment may route different kinds of call to different models: a
    run whose reasoning came from one model and whose summarisation came from
    another produced a number that neither of them produced alone. Naming one of
    them would be the wrong answer, and naming none of them would make the number
    unreproducible.
    """
    when = (at or datetime.now(UTC)).date().isoformat()
    models = ", ".join(f"`{name}`" for name in sorted(set(model_set)))
    return (
        f"_Measured on {when} on the `{runtime}` runtime"
        + (f", corpus `{corpus_version}`" if corpus_version else "")
        + (f", models {models}" if models else "")
        + ". Benchmark numbers are produced on the canonical runtime only._"
    )


def splice(document: str, table: str) -> str:
    """Return ``document`` with ``table`` between the markers, appending them if absent.

    Everything outside the markers survives untouched. That is the whole contract:
    a README has prose somebody wrote, and an exporter that replaced the file
    would be run once and then removed from the Makefile.
    """
    block = f"{BENCHMARK_TABLE_BEGIN}\n{table}\n{BENCHMARK_TABLE_END}"

    start = document.find(BENCHMARK_TABLE_BEGIN)
    end = document.find(BENCHMARK_TABLE_END)
    if start == -1 or end == -1 or end < start:
        separator = "" if document.endswith("\n") else "\n"
        return f"{document}{separator}\n{block}\n"

    return document[:start] + block + document[end + len(BENCHMARK_TABLE_END) :]


def model_set(runs: Sequence[BenchmarkRun]) -> tuple[str, ...]:
    """Return every distinct ``provider/model`` the measured runs used, sorted."""
    return tuple(sorted({f"{run.provider_id}/{run.model_id}" for run in runs if run.model_id}))


def write_table(
    runs: Sequence[BenchmarkRun],
    path: Path,
    *,
    runtime: str = "",
    corpus_version: str = "",
) -> Path:
    """Splice a benchmark table into the document at ``path`` and return it.

    Creates the document when it does not exist, so the first export into a fresh
    release-notes file is the same command as the hundredth into the README.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    body = (
        markdown_table(runs)
        + "\n\n"
        + provenance_line(runtime=runtime, corpus_version=corpus_version, model_set=model_set(runs))
    )
    path.write_text(splice(existing, body), encoding="utf-8")
    return path


def release_note(
    runs: Sequence[BenchmarkRun], *, runtime: str = "", corpus_version: str = ""
) -> str:
    """Return the section a release note carries, table and provenance together."""
    name = runs[0].name if runs else "benchmark"
    return "\n".join(
        [
            f"### {name}",
            "",
            markdown_table(runs),
            "",
            provenance_line(
                runtime=runtime, corpus_version=corpus_version, model_set=model_set(runs)
            ),
            "",
        ]
    )


def write_release_note(
    runs: Sequence[BenchmarkRun],
    path: Path,
    *,
    runtime: str = "",
    corpus_version: str = "",
) -> Path:
    """Write the release-note section to ``path`` and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        release_note(runs, runtime=runtime, corpus_version=corpus_version), encoding="utf-8"
    )
    return path


#: The corpus table's columns. A different question from the cross-model one:
#: not "which model" but "how far up the curriculum does this get".
CORPUS_COLUMNS: tuple[str, ...] = ("Level", "Definition", "Solved", "Pass rate")


def corpus_table(suite: SuiteScore) -> str:
    """Return the scenario corpus's own results as a Markdown table, by difficulty.

    The publishable claim this repository can make from its own corpus, and the
    stratification is the whole of it: "we solve 90% of scenarios" is a sentence
    about which scenarios somebody chose to write, and a per-level table is a
    sentence about the agent.
    """
    header = f"| {' | '.join(CORPUS_COLUMNS)} |"
    divider = f"|{'|'.join('---' for _ in CORPUS_COLUMNS)}|"
    rows = [
        f"| {level.difficulty} | {level.description} | {level.passes}/{level.attempts} | "
        f"{level.pass_rate:.0%} |"
        for level in suite.by_difficulty()
    ]
    axes = " · ".join(f"{axis.axis} {axis.pass_rate:.0%}" for axis in suite.axes if axis.asserted)
    return "\n".join([header, divider, *rows, "", f"Per axis: {axes}."])


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tests.benchmarks.export",
        description="Produce the benchmark tables a README and a release note carry.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="score this scenario corpus offline and print its table",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="a stored benchmark record to render instead of running anything",
    )
    parser.add_argument("--into", type=Path, default=None, help="splice the table into this file")
    parser.add_argument(
        "--attempts", type=int, default=DEFAULT_SCENARIO_ATTEMPTS, help="attempts per scenario"
    )
    parser.add_argument("--json", type=Path, default=None, help="write the record here as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Produce a benchmark table and return the process exit status."""
    import asyncio
    import json as json_module

    options = _arguments(argv)

    if options.record is not None:
        comparison = ModelComparison.from_record(
            json_module.loads(options.record.read_text(encoding="utf-8"))
        )
        table = markdown_table(comparison.runs)
        runtime = comparison.runtime
        corpus = ""
        models = model_set(comparison.runs)
    elif options.corpus is not None:
        from tests.harness.regression.ci import measure

        suite = asyncio.run(measure(options.corpus, attempts=options.attempts, label="corpus"))
        table = corpus_table(suite)
        runtime = RUNTIME_CANONICAL
        corpus = suite.corpus_version
        # The corpus is scored offline against a scripted agent, so no model
        # produced this number and naming one would be a claim nobody made.
        models = ()
        if options.json is not None:
            options.json.parent.mkdir(parents=True, exist_ok=True)
            options.json.write_text(
                json_module.dumps(suite.to_record(), indent=2), encoding="utf-8"
            )
    else:
        print(
            "nothing to render: pass --corpus to score the scenario corpus, or --record to "
            "render a stored benchmark run.",
            file=sys.stderr,
        )
        return 2

    body = (
        table + "\n\n" + provenance_line(runtime=runtime, corpus_version=corpus, model_set=models)
    )
    print(body)

    if options.into is not None:
        existing = options.into.read_text(encoding="utf-8") if options.into.exists() else ""
        options.into.parent.mkdir(parents=True, exist_ok=True)
        options.into.write_text(splice(existing, body), encoding="utf-8")
        print(f"\nspliced into {options.into}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point itself
    sys.exit(main())


__all__ = [
    "COLUMNS",
    "CORPUS_COLUMNS",
    "corpus_table",
    "main",
    "markdown_table",
    "model_set",
    "provenance_line",
    "release_note",
    "splice",
    "write_release_note",
    "write_table",
]
