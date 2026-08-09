"""Pointing the deployment at a metrics system, and finding out what is really there.

An operator who configures Prometheus has said where it is. They have not said
what is publishing into it, and that is the fact everything else in this feature
depends on: a mapping for the Proxmox exporter is worth nothing against a
Prometheus that only has a node exporter, and the failure mode is silence.

So verification asks a real question and reports the answer per exporter. The
tests below are mostly about the difference between "we looked and it is not
there" and "we could not look", which is the same distinction the rest of
observation is built on.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from config.constants.observability_bridge import (
    EXPORTER_NODE,
    EXPORTER_PROXMOX,
    EXPORTER_TEXTFILE,
)
from platform.observation.bridge.errors import MetricsSourceUnreachable
from platform.observation.bridge.ports import MetricPoint, MetricSeries, MetricsSource
from platform.observation.bridge.verification import (
    SHIPPED_EXPORTERS,
    verify_metrics_source,
)

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)

BRIDGE_PACKAGE = Path(__file__).resolve().parents[5] / "platform" / "observation" / "bridge"


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def series(metric: str, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=1.0),),
    )


@dataclass
class StubMetrics:
    """A metrics system that answers whatever a test tells it to."""

    answers: dict[str, tuple[MetricSeries, ...]] = field(default_factory=dict)
    fails: Exception | None = None
    asked: list[tuple[str, ...]] = field(default_factory=list)

    async def series(self, *, matchers: tuple[str, ...], at: datetime) -> tuple[MetricSeries, ...]:
        """Return whatever was configured for ``matchers``."""
        del at
        self.asked.append(matchers)
        if self.fails is not None:
            raise self.fails
        found: list[MetricSeries] = []
        for matcher in matchers:
            found.extend(self.answers.get(matcher, ()))
        return tuple(found)

    async def history(
        self,
        *,
        matchers: tuple[str, ...],
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> tuple[MetricSeries, ...]:
        """Return whatever was configured, ignoring the window."""
        del start, end, step_seconds
        return await self.series(matchers=matchers, at=EPOCH)


def test_a_stub_metrics_source_satisfies_the_port() -> None:
    """The protocol is structural, so a test double proves the shape is reachable."""
    assert isinstance(StubMetrics(), MetricsSource)


@pytest.mark.asyncio
async def test_verification_asks_a_real_query_and_names_the_exporters_present() -> None:
    """SC-001: verification against a real Prometheus reports which exporters are there."""
    source = StubMetrics(
        answers={
            expectation.matcher: (series("pve_up", id="node/pve01"),)
            for expectation in SHIPPED_EXPORTERS
            if expectation.exporter == EXPORTER_PROXMOX
        }
    )

    verification = await verify_metrics_source(source, at=at())

    assert source.asked, "verification that made no query has verified nothing"
    assert verification.reachable
    assert [presence.exporter for presence in verification.present] == [EXPORTER_PROXMOX]


@pytest.mark.asyncio
async def test_verification_names_the_exporters_that_are_absent() -> None:
    """T-002: the absent ones are named, with what would publish them."""
    source = StubMetrics(
        answers={
            expectation.matcher: (series("pve_up"),)
            for expectation in SHIPPED_EXPORTERS
            if expectation.exporter == EXPORTER_PROXMOX
        }
    )

    verification = await verify_metrics_source(source, at=at())

    absent = {presence.exporter for presence in verification.absent}
    assert absent == {EXPORTER_NODE, EXPORTER_TEXTFILE}
    for presence in verification.absent:
        assert presence.install_hint, f"{presence.exporter} is absent with no next step"


@pytest.mark.asyncio
async def test_an_unreachable_source_reports_nothing_absent_rather_than_everything() -> None:
    """A source that could not be asked has not established that anything is missing."""
    source = StubMetrics(fails=MetricsSourceUnreachable("prometheus", reason="connection refused"))

    verification = await verify_metrics_source(source, at=at())

    assert not verification.reachable
    assert verification.absent == ()
    assert verification.present == ()
    assert "connection refused" in verification.failure


@pytest.mark.asyncio
async def test_an_unexpected_failure_is_reported_rather_than_swallowed() -> None:
    """Whatever the transport raised, the verification says so instead of looking clean."""
    source = StubMetrics(fails=TimeoutError("took too long"))

    verification = await verify_metrics_source(source, at=at())

    assert not verification.reachable
    assert "took too long" in verification.failure
    assert "TimeoutError" in verification.failure
    assert verification.exporters == ()


def test_every_shipped_expectation_says_what_would_publish_it() -> None:
    """An expectation with no install hint is a dead end for whoever reads the report."""
    assert SHIPPED_EXPORTERS
    for expectation in SHIPPED_EXPORTERS:
        assert expectation.matcher
        assert expectation.describes
        assert expectation.install_hint


def test_no_module_in_the_bridge_can_hold_a_credential() -> None:
    """T-003: the bridge reaches its sources through the proxy and holds nothing.

    Structural rather than by convention. A name that could hold a token is the
    first step towards one being held, and the check is over the whole package
    so a later module cannot quietly opt out.
    """
    forbidden = ("token", "password", "secret", "api_key", "apikey", "credential", "bearer")
    offences: list[str] = []

    for module in sorted(BRIDGE_PACKAGE.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.arg):
                named = node.arg
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                named = node.id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                named = node.target.id
            else:
                continue
            if any(word in named.lower() for word in forbidden):
                offences.append(f"{module.name}:{named}")

    assert offences == []


def test_the_bridge_imports_no_integration_and_reads_no_environment() -> None:
    """Tier 3 reaches tier 2 through a protocol, and reads no process environment."""
    offences: list[str] = []

    for module in sorted(BRIDGE_PACKAGE.glob("*.py")):
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("integrations"):
                offences.append(f"{module.name}: imports {node.module}")
            if isinstance(node, ast.Import):
                offences.extend(
                    f"{module.name}: imports {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("integrations")
                )
        if "os.environ" in source or "getenv" in source:
            offences.append(f"{module.name}: reads the process environment")

    assert offences == []
