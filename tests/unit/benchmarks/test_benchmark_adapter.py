"""The external-benchmark port, the canonical-runtime guard, and the published table.

Two of these tests are about a refusal, and the refusal is the point. Article V
allows alternative runtimes and allows exactly one of them to produce a published
number: a score that could have moved because the runtime changed measures
nothing, and publishing both invites precisely that comparison.

The rest is arithmetic and formatting, which matters more than it sounds. A
benchmark table is the artefact that leaves the repository, and a table that
cannot be regenerated from its own record is a screenshot in a README.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.constants.evaluation import (
    BENCHMARK_TABLE_BEGIN,
    BENCHMARK_TABLE_END,
    CLOUD_OPS_BENCH,
)
from config.constants.llm import SUPPORTED_PROVIDERS
from core.agent.guard import NonCanonicalRuntimeError
from tests.benchmarks.adapter import (
    BenchmarkCase,
    BenchmarkOutcome,
    BenchmarkRun,
    UnusableBenchmarkCase,
    run_benchmark,
)
from tests.benchmarks.cloudopsbench.dataset import (
    CloudOpsBenchAdapter,
    load_cases,
    write_dataset,
)
from tests.benchmarks.export import (
    markdown_table,
    splice,
    write_release_note,
)
from tests.benchmarks.models.comparison import ModelComparison, compare_models

pytestmark = pytest.mark.unit


class Canonical:
    """A runtime that says it may publish, which is what the guard reads."""

    name = "react_loop"
    is_canonical = True


class Experimental:
    """An alternative runtime. Legitimate to run; never legitimate to publish from."""

    name = "sdk_adapter"
    is_canonical = False


CASES = (
    BenchmarkCase(
        case_id="k8s-oom-1",
        objective="checkout pods are restarting",
        expected_category="resource_exhaustion",
        required_keywords=("memory", "limit"),
        difficulty=1,
    ),
    BenchmarkCase(
        case_id="net-timeout-2",
        objective="checkout is timing out against payments",
        expected_category="dependency_failure",
        required_keywords=("timeout",),
        difficulty=3,
    ),
)


async def solver(case: BenchmarkCase) -> BenchmarkOutcome:
    """Return a right answer for the easy case and a wrong one for the hard case."""
    if case.difficulty < 3:
        return BenchmarkOutcome(
            category=case.expected_category,
            answer="the container exceeded its memory limit",
            tokens=4_000,
            seconds=2.0,
        )
    return BenchmarkOutcome(category="unknown", answer="unclear", tokens=9_000, seconds=6.0)


# -- the port (T038, FR-022) ---------------------------------------------------


async def test_a_benchmark_run_scores_every_case_it_was_given() -> None:
    """The adapter's whole contract: cases in, a scored run out."""
    run = await run_benchmark(CASES, solve=solver, runtime=Canonical(), name="fixture")

    assert run.total == 2
    assert run.solved == 1
    assert run.score == pytest.approx(0.5)
    assert run.name == "fixture"


async def test_a_case_missing_its_ground_truth_is_refused_when_it_is_built() -> None:
    """A benchmark case nobody can score is a case that inflates or deflates silently."""
    with pytest.raises(UnusableBenchmarkCase):
        BenchmarkCase(case_id="", objective="something", expected_category="unknown")


async def test_the_run_records_which_cases_failed_and_why() -> None:
    """A benchmark number nobody can drill into is a number nobody can act on."""
    run = await run_benchmark(CASES, solve=solver, runtime=Canonical(), name="fixture")

    failed = [result for result in run.results if not result.solved]
    assert [result.case_id for result in failed] == ["net-timeout-2"]
    assert failed[0].detail


# -- the canonical-runtime guard (T041, FR-024, SC-007) ------------------------


async def test_benchmarking_a_non_canonical_runtime_is_refused() -> None:
    """SC-007. A number produced under other guardrails is not comparable to one under these."""
    with pytest.raises(NonCanonicalRuntimeError) as raised:
        await run_benchmark(CASES, solve=solver, runtime=Experimental(), name="fixture")

    assert "sdk_adapter" in str(raised.value)


async def test_the_guard_fires_before_a_single_case_is_run() -> None:
    """Refusing after spending the tokens would make the refusal a formality."""
    seen: list[str] = []

    async def counting(case: BenchmarkCase) -> BenchmarkOutcome:
        seen.append(case.case_id)
        return BenchmarkOutcome(category=case.expected_category, answer="x")

    with pytest.raises(NonCanonicalRuntimeError):
        await run_benchmark(CASES, solve=counting, runtime=Experimental(), name="fixture")

    assert seen == []


# -- the reference implementation (T039) ---------------------------------------


def test_a_cloud_opsbench_dataset_loads_into_cases(tmp_path: Path) -> None:
    """The reference adapter, over the shape the dataset actually ships in."""
    path = write_dataset(
        [
            {
                "id": "case-1",
                "prompt": "the checkout service is erroring",
                "root_cause_category": "resource_exhaustion",
                "keywords": ["memory"],
                "level": 2,
            }
        ],
        tmp_path / "cases.jsonl",
    )

    cases = load_cases(path)

    assert [case.case_id for case in cases] == ["case-1"]
    assert cases[0].expected_category == "resource_exhaustion"
    assert cases[0].difficulty == 2


def test_a_malformed_dataset_row_names_the_file_and_the_row(tmp_path: Path) -> None:
    """The person seeing this is fixing the dataset, so tell them where to look."""
    path = tmp_path / "cases.jsonl"
    path.write_text('{"prompt": "no identifier"}\n', encoding="utf-8")

    with pytest.raises(UnusableBenchmarkCase) as raised:
        load_cases(path)

    assert "cases.jsonl" in str(raised.value)
    assert "1" in str(raised.value)


async def test_the_reference_adapter_names_itself_and_runs(tmp_path: Path) -> None:
    """An adapter that could not say which benchmark it is would publish an unlabelled number."""
    path = write_dataset(
        [
            {
                "id": "case-1",
                "prompt": "checkout is erroring",
                "root_cause_category": "resource_exhaustion",
                "keywords": ["memory", "limit"],
                "level": 1,
            }
        ],
        tmp_path / "cases.jsonl",
    )
    adapter = CloudOpsBenchAdapter(dataset=path)

    assert adapter.name == CLOUD_OPS_BENCH

    run = await run_benchmark(adapter.cases(), solve=solver, runtime=Canonical(), name=adapter.name)
    assert run.score == pytest.approx(1.0)


# -- cross-model comparison (T040, T042, FR-023, SC-008) -----------------------


async def test_the_cross_model_table_covers_every_supported_provider() -> None:
    """SC-008: nine providers, and the nine the repository declares."""

    async def per_provider(provider: str, case: BenchmarkCase) -> BenchmarkOutcome:
        # Anthropic gets the hard one right; nobody else does. Enough to make the
        # table have shape without pretending to be a real measurement.
        correct = case.difficulty < 3 or provider == "anthropic"
        return BenchmarkOutcome(
            category=case.expected_category if correct else "unknown",
            answer="the container exceeded its memory limit" if correct else "unclear",
            tokens=4_000,
            seconds=2.0,
        )

    comparison = await compare_models(
        CASES, solve=per_provider, runtime=Canonical(), name="fixture"
    )

    assert tuple(run.provider_id for run in comparison.runs) == SUPPORTED_PROVIDERS
    assert len(comparison.runs) == 9
    assert comparison.best().provider_id == "anthropic"


async def test_a_cross_model_run_refuses_a_non_canonical_runtime() -> None:
    """The guard applies to every published number, not only the single-model one."""

    async def per_provider(provider: str, case: BenchmarkCase) -> BenchmarkOutcome:
        return BenchmarkOutcome(category=case.expected_category, answer="x")

    with pytest.raises(NonCanonicalRuntimeError):
        await compare_models(CASES, solve=per_provider, runtime=Experimental(), name="fixture")


def test_a_comparison_round_trips_through_its_record() -> None:
    """A published table has to be regenerable from the run that produced it."""
    comparison = ModelComparison(
        name="fixture",
        runs=(
            BenchmarkRun(name="fixture", provider_id="anthropic", model_id="claude", results=()),
        ),
    )

    assert ModelComparison.from_record(comparison.to_record()) == comparison


# -- export (T043, FR-025) -----------------------------------------------------


def test_the_table_is_markdown_a_readme_can_hold() -> None:
    """The artefact that leaves the repository."""
    runs = (
        BenchmarkRun(name="cloud_opsbench", provider_id="anthropic", model_id="claude-opus"),
        BenchmarkRun(name="cloud_opsbench", provider_id="ollama", model_id="llama"),
    )
    table = markdown_table(runs)

    assert table.startswith("| Provider ")
    assert "anthropic" in table
    assert table.count("\n") >= 3


def test_splicing_replaces_only_what_is_between_the_markers() -> None:
    """A README has other content, and an exporter that ate it would be used once."""
    document = f"# NinjaSRE\n\nsome prose\n\n{BENCHMARK_TABLE_BEGIN}\nold\n{BENCHMARK_TABLE_END}\n\nmore prose\n"

    spliced = splice(document, "new table")

    assert "some prose" in spliced
    assert "more prose" in spliced
    assert "old" not in spliced
    assert "new table" in spliced


def test_splicing_a_document_with_no_markers_appends_them() -> None:
    """The first export into a document that has never had one."""
    spliced = splice("# NinjaSRE\n", "a table")

    assert BENCHMARK_TABLE_BEGIN in spliced
    assert "a table" in spliced


def test_a_release_note_carries_the_runtime_and_the_corpus_it_measured(tmp_path: Path) -> None:
    """FR-025: a number without its provenance is a number nobody can defend."""
    runs = (BenchmarkRun(name="cloud_opsbench", provider_id="anthropic", model_id="claude"),)
    path = write_release_note(
        runs, tmp_path / "note.md", runtime="react_loop", corpus_version="abc123"
    )

    text = path.read_text(encoding="utf-8")
    assert "react_loop" in text
    assert "abc123" in text
    assert "anthropic" in text


def test_the_exported_record_is_json_a_ci_job_can_publish(tmp_path: Path) -> None:
    """The machine-readable half, so a dashboard does not scrape the markdown."""
    comparison = ModelComparison(
        name="fixture",
        runs=(BenchmarkRun(name="fixture", provider_id="anthropic", model_id="claude"),),
    )
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(comparison.to_record()), encoding="utf-8")

    assert ModelComparison.from_record(json.loads(path.read_text(encoding="utf-8"))) == comparison
