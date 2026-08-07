"""The same corpus across every provider, so "which model" has an answer per deployment.

Article VI says every provider is a first-class target, and that only means
something if somebody has measured them. A comparison table is what turns
"supported" into a number an operator can choose on: the cheap local model that
solves the level-one incidents may be the right default for a team whose
incidents are level one.

Every provider runs, including the ones expected to do badly. A table that
quietly omitted the weak entries would be marketing; the point of the exercise is
that a reader can see the shape of the trade-off, and the shape is made of the
low rows as much as the high ones.

The canonical-runtime guard applies here exactly as it does to a single run
(FR-024). A cross-model table is the most publishable artefact this repository
produces, which makes it the one most worth refusing to produce dishonestly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.llm import SUPPORTED_PROVIDERS
from core.agent.guard import require_canonical_runtime
from core.agent.runtime_port import Runtime
from tests.benchmarks.adapter import (
    BENCHMARK_CONTEXT,
    BenchmarkCase,
    BenchmarkOutcome,
    BenchmarkRun,
    score_case,
)

#: How a caller runs one case against one provider. The provider identifier is
#: passed rather than a composed client, because composing nine clients is a
#: deployment concern and eight of them need credentials this harness must not
#: read.
ProviderSolver = Callable[[str, BenchmarkCase], Awaitable[BenchmarkOutcome]]


@dataclass(frozen=True, slots=True)
class ModelComparison:
    """One benchmark, across every provider, in provider order."""

    name: str = ""
    runs: tuple[BenchmarkRun, ...] = ()
    runtime: str = ""

    @property
    def providers(self) -> tuple[str, ...]:
        """Return every provider the table covers."""
        return tuple(run.provider_id for run in self.runs)

    def run_for(self, provider_id: str) -> BenchmarkRun | None:
        """Return one provider's run, or ``None`` when it did not run."""
        return next((run for run in self.runs if run.provider_id == provider_id), None)

    def best(self) -> BenchmarkRun:
        """Return the highest-scoring run, ties broken by the cheaper one.

        Raises:
            ValueError: nothing ran, so there is no best.
        """
        if not self.runs:
            raise ValueError("this comparison holds no runs, so nothing is best")
        return max(self.runs, key=lambda run: (run.score, -run.tokens))

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this comparison."""
        return {
            "name": self.name,
            "runtime": self.runtime,
            "runs": [run.to_record() for run in self.runs],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ModelComparison:
        """Return the comparison a stored record describes."""
        return cls(
            name=str(record.get("name", "")),
            runtime=str(record.get("runtime", "")),
            runs=tuple(BenchmarkRun.from_record(item) for item in record.get("runs") or ()),
        )


async def compare_models(
    cases: Sequence[BenchmarkCase],
    *,
    solve: ProviderSolver,
    runtime: Runtime,
    name: str,
    providers: Sequence[str] = SUPPORTED_PROVIDERS,
    models: Mapping[str, str] | None = None,
) -> ModelComparison:
    """Return one run per provider over ``cases``, on the canonical runtime only.

    ``models`` names which model stood for each provider. Supplied by the caller
    rather than defaulted here: which model a deployment points at is a
    deployment's choice, and a table that named one this harness picked would be
    reporting a measurement of something nobody ran.

    Raises:
        NonCanonicalRuntimeError: ``runtime`` may not produce a published number.
    """
    require_canonical_runtime(runtime, context=BENCHMARK_CONTEXT)

    runs: list[BenchmarkRun] = []
    for provider in providers:
        results = [score_case(case, await solve(provider, case)) for case in cases]
        runs.append(
            BenchmarkRun(
                name=name,
                provider_id=provider,
                model_id=(models or {}).get(provider, ""),
                runtime=runtime.name,
                results=tuple(results),
            )
        )
    return ModelComparison(name=name, runs=tuple(runs), runtime=runtime.name)


__all__ = ["ModelComparison", "ProviderSolver", "compare_models"]
