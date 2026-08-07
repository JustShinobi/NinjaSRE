"""Putting the demo application and its observability stack on a cluster.

Declarative, and one command each way. The install is a chart with a
values document; the uninstall is the release name. Everything that could differ
between a laptop and CI — the namespace, the chart version, how long readiness
is given — is a field on the spec rather than a flag somebody has to remember.

Readiness is checked rather than waited out. A fixed sleep is the wrong shape
twice: too short on a cold cluster pulling images, and pure waste on a warm one.
So installation asks the cluster whether the deployments it created are
available, which is also the check that tells an operator *which* service did
not come up.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from config.constants.chaos import (
    OTEL_DEMO_INSTALL_TIMEOUT_SECONDS,
    OTEL_DEMO_NAMESPACE,
)
from tests.support.commands import CommandFailed, CommandResult, CommandRunner

#: The command the installation is expressed in. A package manager rather than a
#: pile of manifests, because the demo ships one and reproducing it here would
#: be a copy that goes stale on the first upstream release.
HELM = "helm"

#: The chart repository the demo is published in.
DEMO_REPOSITORY = "open-telemetry"

#: Where that repository lives.
DEMO_REPOSITORY_URL = "https://open-telemetry.github.io/opentelemetry-helm-charts"

#: The chart, and the release the suite installs it under.
DEMO_CHART = "open-telemetry/opentelemetry-demo"
DEMO_RELEASE = "ninjasre-otel-demo"

#: The workloads the suite waits for, and the ones whose absence it reports.
#: Not the whole demo: these are the services the five faults act on plus the
#: observability stack the investigation reads through.
DEMO_WORKLOADS: tuple[str, ...] = (
    "cart",
    "productcatalog",
    "recommendation",
    "ad",
    "checkout",
    "payment",
    "flagd",
    "frontend",
    "otel-collector",
    "prometheus",
    "grafana",
)


@dataclass(frozen=True, slots=True)
class DemoInstallation:
    """Everything the suite needs to install, wait for, and remove the demo."""

    namespace: str = OTEL_DEMO_NAMESPACE
    release: str = DEMO_RELEASE
    chart: str = DEMO_CHART
    repository: str = DEMO_REPOSITORY
    repository_url: str = DEMO_REPOSITORY_URL
    chart_version: str = ""
    values: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = OTEL_DEMO_INSTALL_TIMEOUT_SECONDS
    workloads: tuple[str, ...] = DEMO_WORKLOADS

    def install_argv(self) -> tuple[str, ...]:
        """Return the one command that installs the demo and its stack."""
        argv = [
            HELM,
            "upgrade",
            "--install",
            self.release,
            self.chart,
            "--namespace",
            self.namespace,
            "--create-namespace",
            "--wait",
            "--timeout",
            f"{int(self.timeout_seconds)}s",
        ]
        if self.chart_version:
            argv += ["--version", self.chart_version]
        for name, value in sorted(self.values.items()):
            argv += ["--set", f"{name}={value}"]
        return tuple(argv)

    def uninstall_argv(self) -> tuple[str, ...]:
        """Return the one command that removes it again."""
        return (
            HELM,
            "uninstall",
            self.release,
            "--namespace",
            self.namespace,
            "--ignore-not-found",
            "--wait",
        )

    def repository_argv(self) -> tuple[tuple[str, ...], ...]:
        """Return the commands that make the chart findable."""
        return (
            (HELM, "repo", "add", self.repository, self.repository_url, "--force-update"),
            (HELM, "repo", "update", self.repository),
        )


@dataclass(frozen=True, slots=True)
class InstallReport:
    """What an installation did, and which workloads did not come up."""

    installed: bool
    missing: tuple[str, ...] = ()
    detail: str = ""

    @property
    def ready(self) -> bool:
        """Return whether the demo is installed and every workload is available."""
        return self.installed and not self.missing


def install(
    runner: CommandRunner, installation: DemoInstallation = DemoInstallation()
) -> InstallReport:
    """Install the demo and its observability stack, and report what came up.

    Raises:
        CommandFailed: the package manager refused; nothing is half-installed
            that ``uninstall`` will not remove.
    """
    for argv in installation.repository_argv():
        result = runner.run(argv, timeout=installation.timeout_seconds)
        if not result.ok:
            raise CommandFailed(result)

    result = runner.run(installation.install_argv(), timeout=installation.timeout_seconds)
    if not result.ok:
        raise CommandFailed(result)

    return InstallReport(installed=True, missing=missing_workloads(runner, installation))


def uninstall(
    runner: CommandRunner, installation: DemoInstallation = DemoInstallation()
) -> CommandResult:
    """Remove the demo, returning what the package manager said.

    Does not raise. Teardown that raised would leave the *rest* of a suite's
    teardown unrun, which is how one failed uninstall becomes a namespace full
    of pods nobody owns.
    """
    return runner.run(installation.uninstall_argv(), timeout=installation.timeout_seconds)


def missing_workloads(
    runner: CommandRunner, installation: DemoInstallation = DemoInstallation()
) -> tuple[str, ...]:
    """Return the demo workloads that are not available on the cluster.

    Names them rather than reporting a count. "The demo is not ready" sends
    somebody to look at eleven deployments; "recommendation is not ready" sends
    them to one.
    """
    import json

    result = runner.run(
        ("kubectl", "get", "deployments", "-n", installation.namespace, "-o", "json"),
        timeout=installation.timeout_seconds,
    )
    if not result.ok:
        return installation.workloads

    try:
        document = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return installation.workloads

    available = {
        _name(item): _available(item)
        for item in document.get("items") or []
        if isinstance(item, dict)
    }
    return tuple(
        workload
        for workload in installation.workloads
        if not any(name.endswith(workload) and ready for name, ready in available.items())
    )


def _name(item: Mapping[str, object]) -> str:
    metadata = item.get("metadata")
    return str((metadata or {}).get("name", "")) if isinstance(metadata, dict) else ""


def _available(item: Mapping[str, object]) -> bool:
    status = item.get("status")
    if not isinstance(status, dict):
        return False
    conditions: Sequence[object] = status.get("conditions") or ()
    return any(
        isinstance(condition, dict)
        and condition.get("type") == "Available"
        and condition.get("status") == "True"
        for condition in conditions
    )


__all__ = [
    "DEMO_CHART",
    "DEMO_RELEASE",
    "DEMO_REPOSITORY",
    "DEMO_REPOSITORY_URL",
    "DEMO_WORKLOADS",
    "HELM",
    "DemoInstallation",
    "InstallReport",
    "install",
    "missing_workloads",
    "uninstall",
]
