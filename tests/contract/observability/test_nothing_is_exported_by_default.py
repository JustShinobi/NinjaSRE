"""A default deployment opens no socket, and ships no library that would want to.

Two halves of one claim, both checked the only way that is worth anything.

The first half is watched rather than reasoned about: every socket the standard
library can open is intercepted, a fully instrumented workload runs, and the
interceptor's ledger has to be empty. Asserting "the exporter was not called"
would prove that the exporter was not called, which is a weaker statement than
the one being made.

The second half walks the resolved dependency tree, because the telemetry
package nobody would approve in review is the one pulled in three levels down.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter
from platform.observability.metrics.definitions import MetricRegistry
from platform.observability.tracing import SpanKind, Tracer
from tools.check_dependencies import PROJECT_NAME, find_banned_dependencies

pytestmark = pytest.mark.contract


class NetworkMonitor:
    """Records every connection attempt and refuses all of them."""

    def __init__(self) -> None:
        self.attempts: list[Any] = []

    def observe(self, address: Any) -> None:
        """Record one attempted destination and refuse it."""
        self.attempts.append(address)
        raise AssertionError(f"a default deployment tried to reach {address!r}")


@pytest.fixture
def monitor(monkeypatch: pytest.MonkeyPatch) -> Iterator[NetworkMonitor]:
    """Intercept every outbound connection the standard library can make."""
    watcher = NetworkMonitor()

    def refuse(self: socket.socket, address: Any) -> None:
        watcher.observe(address)

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)

    def refuse_create(address: Any, *arguments: Any, **keywords: Any) -> None:
        watcher.observe(address)

    monkeypatch.setattr(socket, "create_connection", refuse_create)
    yield watcher


def _run_an_instrumented_workload(config: TelemetryConfig) -> None:
    """Do everything an investigation does that touches telemetry."""
    exporter = OtlpExporter(config=config)
    tracer = Tracer(config=config, exporter=exporter)
    registry = MetricRegistry(config=config, exporter=exporter)

    with tracer.span("pipeline.triage", SpanKind.PIPELINE_STAGE, team="platform"):
        with (
            tracer.span("loop.iteration", SpanKind.LOOP_ITERATION, iteration="1"),
            tracer.span("grafana.query", SpanKind.CAPABILITY, capability="grafana.query"),
        ):
            pass
        with tracer.span("episodes.search", SpanKind.STORAGE, store="episodes"):
            pass

    registry.counter("investigation.count").add(1, team="platform", trigger="alert", outcome="ok")
    registry.histogram("investigation.duration").record(
        4.2, team="platform", trigger="alert", outcome="ok"
    )
    registry.gauge("scheduler.queue_depth").set(3)
    tracer.flush()
    registry.flush()


def test_a_default_deployment_opens_no_socket(monitor: NetworkMonitor) -> None:
    """SC-001, watched rather than asserted about."""
    config = TelemetryConfig.from_environment({})

    assert not config.enabled

    _run_an_instrumented_workload(config)

    assert monitor.attempts == []


def test_the_monitor_would_catch_an_export(monitor: NetworkMonitor) -> None:
    """A negative test that never fires is a test that proves nothing."""
    config = TelemetryConfig(endpoint="http://collector.internal:4318")

    _run_an_instrumented_workload(config)

    assert monitor.attempts, "the monitor did not see the export it was supposed to catch"


def test_no_telemetry_package_is_in_the_runtime_dependency_tree() -> None:
    """SC-008. The same walk ``make check-deps`` runs, so a drift fails here too."""
    from pathlib import Path

    lock = Path(__file__).resolve().parents[3] / "uv.lock"

    assert find_banned_dependencies(lock.read_text(encoding="utf-8"), PROJECT_NAME) == []


def test_the_exporter_needs_no_dependency_outside_the_standard_library() -> None:
    """Article X, held by construction rather than by review.

    The OTLP encoder and its transport import nothing but the standard library,
    so there is no telemetry package for the dependency scan to find and no
    library deciding on its own what to send.
    """
    import ast
    from pathlib import Path

    module = Path(__file__).resolve().parents[3] / "platform" / "observability" / "export.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    first_party = {"config", "platform"}

    assert imported - first_party <= set(__import__("sys").stdlib_module_names)
