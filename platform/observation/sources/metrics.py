"""Asking somebody else's metrics system a question, and storing the answer.

Most estates already have a time-series database. Re-collecting what it holds
would be a second collection pipeline, a second set of scrape intervals, and two
numbers for one measurement — so this source *queries* rather than collects, and
what it stores is the answer at the instant it was asked.

That is also why storing the answer is not a second copy of the metrics
database. One sample per query per interval is what a detector needs to say
"this has held for ten minutes", and it is bounded by the same retention as every
other signal. Copying the underlying series would be the second datastore
Article XI refuses.

**The query is opaque here on purpose.** PromQL, a Datadog query, an InfluxQL
statement — this package neither parses nor validates one, because a detector
that could express arbitrary computation in a query string would be the second
programming language the plan's risks name. The *detector* still declares a
condition over the result; the query only says which number to read.

The protocol is the shape a metrics integration fills in.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReading,
)
from platform.persistence.ports.signal_store import SignalKind


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One number a metrics system returned, and what it is about.

    ``resource_id`` is the estate's identifier rather than the metrics system's
    label set: the mapping from one to the other belongs to the integration that
    knows both, and doing it here would mean this package inventing a join it
    has no way to validate.
    """

    resource_id: str
    value: float
    observed_at: datetime | None = None
    labels: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class MetricsBackend(Protocol):
    """A metrics system that can answer one query about a set of resources."""

    async def evaluate(
        self,
        expression: str,
        *,
        resource_ids: tuple[str, ...],
        at: datetime,
    ) -> tuple[MetricSample, ...]:
        """Return the value of ``expression`` for each resource it covers.

        Raises whatever the integration's client raises when the metrics system
        is unreachable. A resource the query has no data for is *absent from the
        result* rather than present with a zero — a nought that meant "no data"
        would fire every below-threshold detector in the deployment.
        """


@dataclass(frozen=True, slots=True)
class MetricsQuerySource:
    """One named signal, backed by one query against one metrics system."""

    backend: MetricsBackend
    #: What the resulting signal is called. Named here rather than derived from
    #: the expression, because an operator reads the name and nobody wants a
    #: signal called ``sum(rate(node_cpu_seconds_total[5m]))``.
    signal_name: str
    expression: str
    source: str = "metrics"
    interval_seconds: int = 60
    rate_limit_per_minute: int = 60

    @property
    def declaration(self) -> SignalDeclaration:
        """Return what this source says about itself."""
        return SignalDeclaration(
            source=self.source,
            signals=(self.signal_name,),
            interval_seconds=self.interval_seconds,
            rate_limit_per_minute=self.rate_limit_per_minute,
            max_provider_calls=1,
        )

    async def read(
        self,
        *,
        resource_ids: tuple[str, ...],
        at: datetime,
        budget: PollBudget,
    ) -> SignalPage:
        """Return one reading per resource the query covers.

        One provider call whatever the estate's size: a query is asked about the
        whole set at once, which is the property that keeps this source's cost
        independent of how many resources a detector watches.
        """
        del budget  # one query covers the whole set, so there is nothing to ration
        samples = await self.backend.evaluate(self.expression, resource_ids=resource_ids, at=at)
        return SignalPage(
            readings=tuple(
                SignalReading(
                    name=self.signal_name,
                    resource_id=sample.resource_id,
                    kind=SignalKind.NUMBER,
                    value=sample.value,
                    labels=sample.labels,
                    observed_at=sample.observed_at,
                )
                for sample in samples
            ),
            provider_calls=1,
        )


__all__ = ["MetricSample", "MetricsBackend", "MetricsQuerySource"]
