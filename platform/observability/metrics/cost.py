"""What a run cost, attributed per run, per team, and per model at once.

**Attribution is per call.** That is the whole design, and it is a response to
one specific defect. If a run carries "its" model — whichever was active when it
finished — then a run that escalated from a cheap model to an expensive one
bills entirely to the expensive one. The cheap model looks unused, the
escalation looks free, and the operator asking "what does escalating cost me"
gets an answer that is wrong in the direction that makes escalation look
cheaper than it is.

So one record is written per model call, carrying the run, the team, the
provider, and the model. The three views are summations over those records. A
run's per-model records therefore sum to the run total by construction rather
than by anybody remembering to keep two counters in step.

**An unpriced call is counted, never billed at zero.** ``core.llm.usage`` already
holds that line; this preserves it upward, so a total is always readable beside
how much of itself it could not price.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.llm.usage import UsageRecord
from platform.observability.metrics.definitions import MetricRegistry


def _utc_now() -> datetime:
    """Return the current instant, in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CostEntry:
    """One model call, and everything it can be attributed to."""

    run_id: str
    team: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float | None
    at: datetime

    @property
    def is_priced(self) -> bool:
        """Return whether this call had a published price."""
        return self.cost_usd is not None


@dataclass(frozen=True, slots=True)
class CostTotal:
    """A summation over some set of entries, at whatever level was asked for."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0

    @property
    def is_complete(self) -> bool:
        """Return whether every call in this total carried a published price.

        Read ``cost_usd`` with this. On its own the money is a floor, not a
        total, and presenting a floor as a total is how a locally hosted model
        comes to look free.
        """
        return self.unpriced_calls == 0

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a surface prints."""
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "unpriced_calls": self.unpriced_calls,
            "complete": self.is_complete,
        }


def _total(entries: Iterable[CostEntry]) -> CostTotal:
    """Return the summation over ``entries``."""
    calls = input_tokens = output_tokens = cached_tokens = unpriced = 0
    cost = 0.0
    for entry in entries:
        calls += 1
        input_tokens += entry.input_tokens
        output_tokens += entry.output_tokens
        cached_tokens += entry.cached_tokens
        if entry.cost_usd is None:
            unpriced += 1
        else:
            cost += entry.cost_usd
    return CostTotal(
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cost_usd=cost,
        unpriced_calls=unpriced,
    )


@dataclass(frozen=True, slots=True)
class CostReport:
    """One window's spend, broken down the three ways an operator asks for."""

    since: datetime | None
    until: datetime | None
    total: CostTotal
    by_team: dict[str, CostTotal] = field(default_factory=dict)
    by_model: dict[tuple[str, str], CostTotal] = field(default_factory=dict)
    by_run: dict[str, CostTotal] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the CLI and the console both print."""
        return {
            "since": self.since.isoformat() if self.since else "",
            "until": self.until.isoformat() if self.until else "",
            "total": self.total.to_record(),
            "by_team": [
                {"team": team, **totals.to_record()}
                for team, totals in sorted(self.by_team.items())
            ],
            "by_model": [
                {"provider": provider, "model": model, **totals.to_record()}
                for (provider, model), totals in sorted(self.by_model.items())
            ],
            "by_run": [
                {"run_id": run_id, **totals.to_record()}
                for run_id, totals in sorted(self.by_run.items())
            ],
        }


@dataclass(slots=True)
class CostLedger:
    """Every model call this deployment made, and the metrics they wrote.

    The entries are held so a report can be summed at any level after the fact.
    The metrics are written as calls arrive, because a dashboard needs the
    numbers while the run is happening and a report needs them afterwards, and
    deriving one from the other in either direction loses something.
    """

    metrics: MetricRegistry
    entries: list[CostEntry] = field(default_factory=list)

    def record(
        self,
        usage: UsageRecord,
        *,
        run_id: str,
        team: str,
        at: datetime | None = None,
    ) -> CostEntry:
        """Attribute one model call, and return the entry it produced."""
        entry = CostEntry(
            run_id=run_id,
            team=team,
            provider=usage.provider_id,
            model=usage.model_id,
            input_tokens=usage.tokens.input_tokens,
            output_tokens=usage.tokens.output_tokens,
            cached_tokens=usage.tokens.cached_input_tokens,
            cost_usd=usage.cost_usd,
            at=at or _utc_now(),
        )
        self.entries.append(entry)
        self._write_metrics(entry)
        return entry

    def by_run(self) -> dict[str, CostTotal]:
        """Return the spend of every run."""
        return self._grouped(lambda entry: entry.run_id)

    def by_team(self) -> dict[str, CostTotal]:
        """Return the spend of every team."""
        return self._grouped(lambda entry: entry.team)

    def by_model(self, *, run_id: str = "") -> dict[tuple[str, str], CostTotal]:
        """Return the spend of every model, optionally within one run.

        The ``run_id`` filter is what makes a mid-run model switch legible: the
        entries it returns sum to that run's total and say what each model's
        share of it was.
        """
        entries = [entry for entry in self.entries if not run_id or entry.run_id == run_id]
        grouped: dict[tuple[str, str], list[CostEntry]] = {}
        for entry in entries:
            grouped.setdefault((entry.provider, entry.model), []).append(entry)
        return {key: _total(found) for key, found in grouped.items()}

    def report(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        team: str = "",
    ) -> CostReport:
        """Return the spend over a window, broken down by team, model, and run."""
        selected = [
            entry
            for entry in self.entries
            if (since is None or entry.at >= since)
            and (until is None or entry.at <= until)
            and (not team or entry.team == team)
        ]
        by_team: dict[str, list[CostEntry]] = {}
        by_model: dict[tuple[str, str], list[CostEntry]] = {}
        by_run: dict[str, list[CostEntry]] = {}
        for entry in selected:
            by_team.setdefault(entry.team, []).append(entry)
            by_model.setdefault((entry.provider, entry.model), []).append(entry)
            by_run.setdefault(entry.run_id, []).append(entry)

        return CostReport(
            since=since,
            until=until,
            total=_total(selected),
            by_team={key: _total(found) for key, found in by_team.items()},
            by_model={key: _total(found) for key, found in by_model.items()},
            by_run={key: _total(found) for key, found in by_run.items()},
        )

    def _grouped(self, key: Any) -> dict[str, CostTotal]:
        """Return totals grouped by whatever ``key`` extracts from an entry."""
        grouped: dict[str, list[CostEntry]] = {}
        for entry in self.entries:
            grouped.setdefault(key(entry), []).append(entry)
        return {name: _total(found) for name, found in grouped.items()}

    def _write_metrics(self, entry: CostEntry) -> None:
        """Write one call's tokens and money into the cost family."""
        labels = {"team": entry.team, "model": entry.model, "provider": entry.provider}
        self.metrics.counter("llm.input_tokens").add(entry.input_tokens, **labels)
        self.metrics.counter("llm.output_tokens").add(entry.output_tokens, **labels)
        self.metrics.counter("llm.cached_tokens").add(entry.cached_tokens, **labels)
        if entry.cost_usd is None:
            self.metrics.counter("llm.unpriced_calls").add(1, **labels)
        else:
            self.metrics.counter("llm.cost_usd").add(entry.cost_usd, **labels)


__all__ = ["CostEntry", "CostLedger", "CostReport", "CostTotal"]
