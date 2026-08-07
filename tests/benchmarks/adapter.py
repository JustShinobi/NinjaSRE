"""Running somebody else's benchmark through this agent, under this agent's rules.

An external benchmark asks a different question from the scenario corpus. The
corpus is ours: we wrote the incidents, we wrote the answer keys, and a number
from it is only as honest as the people who chose the fixtures. A published
benchmark is somebody else's, which is exactly what makes it worth running — and
exactly why it needs an adapter rather than a fork.

So this is a port. A benchmark is a source of cases with ground truth; a case is
an objective, an expected category, and the words a correct answer contains. What
runs a case is injected, for the same reason it is injected in the ablation
runner: composing a deployment is not this harness's job, and a harness that did
it would be a second composition root drifting away from the real one.

**The guard is the load-bearing part.** Article V allows alternative runtimes and
allows exactly one of them to publish. It fires before the first case runs, not
after: refusing once the tokens are spent would make the refusal a formality, and
the person who set the environment variable would have paid for the number they
are not allowed to use.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.agent.guard import require_canonical_runtime
from core.agent.runtime_port import Runtime

#: What this harness calls the act of publishing a benchmark number, in the
#: refusal message. Named so the person who sees it knows which command to change.
BENCHMARK_CONTEXT = "an external benchmark"


class UnusableBenchmarkCase(ValueError):
    """A benchmark case cannot be scored, so running it would inflate or deflate a number."""


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One case from an external benchmark, with the ground truth to score it."""

    case_id: str
    objective: str
    expected_category: str
    required_keywords: tuple[str, ...] = ()
    difficulty: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise UnusableBenchmarkCase(
                "a benchmark case must carry an identifier, or a failing case cannot be named"
            )
        if not self.objective.strip():
            raise UnusableBenchmarkCase(f"{self.case_id}: a case must state what to investigate")
        if not self.expected_category.strip():
            raise UnusableBenchmarkCase(
                f"{self.case_id}: a case with no expected category cannot be scored, and a "
                f"case nobody can score moves the published number without measuring anything"
            )


@dataclass(frozen=True, slots=True)
class BenchmarkOutcome:
    """What the agent concluded on one case, and what reaching it cost."""

    category: str = "unknown"
    answer: str = ""
    tokens: int = 0
    seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One case, scored, with enough detail to look into a failure."""

    case_id: str
    solved: bool
    expected_category: str = ""
    observed_category: str = ""
    missing_keywords: tuple[str, ...] = ()
    tokens: int = 0
    seconds: float = 0.0
    difficulty: int = 1
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this case."""
        return {
            "case_id": self.case_id,
            "solved": self.solved,
            "expected_category": self.expected_category,
            "observed_category": self.observed_category,
            "missing_keywords": list(self.missing_keywords),
            "tokens": self.tokens,
            "seconds": round(self.seconds, 3),
            "difficulty": self.difficulty,
            "detail": self.detail,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> CaseResult:
        """Return the case a stored record describes."""
        return cls(
            case_id=str(record["case_id"]),
            solved=bool(record.get("solved", False)),
            expected_category=str(record.get("expected_category", "")),
            observed_category=str(record.get("observed_category", "")),
            missing_keywords=tuple(str(item) for item in record.get("missing_keywords") or ()),
            tokens=int(record.get("tokens", 0)),
            seconds=float(record.get("seconds", 0.0)),
            difficulty=int(record.get("difficulty", 1)),
            detail=str(record.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """One benchmark, run once, by one model."""

    name: str
    provider_id: str = ""
    model_id: str = ""
    results: tuple[CaseResult, ...] = ()
    runtime: str = ""

    @property
    def total(self) -> int:
        """Return how many cases were attempted."""
        return len(self.results)

    @property
    def solved(self) -> int:
        """Return how many were solved."""
        return sum(1 for result in self.results if result.solved)

    @property
    def score(self) -> float:
        """Return the share solved."""
        return self.solved / self.total if self.total else 0.0

    @property
    def tokens(self) -> int:
        """Return what the whole run cost in tokens."""
        return sum(result.tokens for result in self.results)

    @property
    def seconds(self) -> float:
        """Return what the whole run cost in wall clock."""
        return sum(result.seconds for result in self.results)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this run."""
        return {
            "name": self.name,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "runtime": self.runtime,
            "total": self.total,
            "solved": self.solved,
            "score": round(self.score, 4),
            "tokens": self.tokens,
            "seconds": round(self.seconds, 3),
            "results": [result.to_record() for result in self.results],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> BenchmarkRun:
        """Return the run a stored record describes."""
        return cls(
            name=str(record["name"]),
            provider_id=str(record.get("provider_id", "")),
            model_id=str(record.get("model_id", "")),
            runtime=str(record.get("runtime", "")),
            results=tuple(CaseResult.from_record(item) for item in record.get("results") or ()),
        )


class BenchmarkAdapter(Protocol):
    """A source of external benchmark cases, named so a number can be labelled."""

    @property
    def name(self) -> str:
        """Return which benchmark this is."""

    def cases(self) -> tuple[BenchmarkCase, ...]:
        """Return every case this benchmark holds, in its own order."""


#: How a caller runs one case. Injected, because composing a deployment is a
#: deployment concern and a benchmark harness that did it would be a second
#: composition root drifting away from the real one.
CaseSolver = Callable[[BenchmarkCase], Awaitable[BenchmarkOutcome]]


def score_case(case: BenchmarkCase, outcome: BenchmarkOutcome) -> CaseResult:
    """Return ``outcome`` scored against ``case``'s ground truth.

    Category and keywords, which is what an external benchmark's ground truth
    gives. Deliberately not the five axes: those need an answer key that asserts
    evidence sources and a golden trajectory, and inventing them for somebody
    else's dataset would be scoring against ground truth we made up.
    """
    right_category = outcome.category == case.expected_category
    said = outcome.answer.lower()
    missing = tuple(word for word in case.required_keywords if word.lower() not in said)

    if not right_category and missing:
        detail = (
            f"expected {case.expected_category!r}, got {outcome.category!r}, and "
            f"{list(missing)} never appeared in the answer"
        )
    elif not right_category:
        detail = f"expected {case.expected_category!r}, got {outcome.category!r}"
    elif missing:
        detail = f"the category was right and {list(missing)} never appeared in the answer"
    else:
        detail = "the category matched and every required word appeared"

    return CaseResult(
        case_id=case.case_id,
        solved=right_category and not missing,
        expected_category=case.expected_category,
        observed_category=outcome.category,
        missing_keywords=missing,
        tokens=outcome.tokens,
        seconds=outcome.seconds,
        difficulty=case.difficulty,
        detail=detail,
    )


async def run_benchmark(
    cases: Sequence[BenchmarkCase],
    *,
    solve: CaseSolver,
    runtime: Runtime,
    name: str,
    provider_id: str = "",
    model_id: str = "",
) -> BenchmarkRun:
    """Return ``cases`` run and scored, on the canonical runtime only.

    Raises:
        NonCanonicalRuntimeError: ``runtime`` may not produce a published number.
    """
    require_canonical_runtime(runtime, context=BENCHMARK_CONTEXT)

    results = [score_case(case, await solve(case)) for case in cases]
    return BenchmarkRun(
        name=name,
        provider_id=provider_id,
        model_id=model_id,
        runtime=runtime.name,
        results=tuple(results),
    )


__all__ = [
    "BENCHMARK_CONTEXT",
    "BenchmarkAdapter",
    "BenchmarkCase",
    "BenchmarkOutcome",
    "BenchmarkRun",
    "CaseResult",
    "CaseSolver",
    "UnusableBenchmarkCase",
    "run_benchmark",
    "score_case",
]
