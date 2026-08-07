"""The local archive that stands in for a crash reporter, and never sends itself.

There is no telemetry here, so nothing produces a report on its own when
something breaks. What replaces it is an artefact the operator builds
deliberately, reads, and then decides what to do with. That only has value if it
is genuinely safe to hand over, which is a much stronger requirement than
"probably fine".

Two independent controls, because either alone fails on the case nobody thought
of:

**An allow-list on names.** Only settings the catalogue in
``platform/startup/settings.py`` documents are included at all. A cloud
credential the operator exported into the same shell is not in the catalogue, so
it is not in the bundle — and it stays out when somebody adds a new one, which is
the part a deny-list would get wrong.

**A scan on every value.** A setting can be non-secret and still carry one: the
database URL is documented, is not marked secret, and has a password in the
middle of it. Every value goes through the guardrail engine on the way in.

Integration health lives here too, because it answers the same question at the
same moment. An operator whose investigations stopped working wants "which
vendor is refusing us" in a sentence, without opening a dashboard — and the
distinction between *broken* and *never set up* is the whole answer, since one
is an outage and the other is a task.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version
from typing import Any, Final

from platform.observability.export import OtlpExporter
from platform.observability.metrics.definitions import MetricRegistry
from platform.startup.settings import SETTINGS

#: What a secret setting is replaced by. Not an empty string: the difference
#: between "set and withheld" and "never set" is often the whole diagnosis.
REDACTED: Final = "[REDACTED]"

#: What the version reads when the package is not installed — a source checkout,
#: which is a real way to run this and not a failure.
UNKNOWN_VERSION: Final = "unknown (running from a source checkout)"

#: The three states an integration can be in from an operator's point of view.
#: "Not configured" is deliberately not "unhealthy": one is a task and the other
#: is an outage, and merging them is how a deployment reports 60 problems on its
#: first day.
STATUS_HEALTHY: Final = "healthy"
STATUS_UNHEALTHY: Final = "unhealthy"
STATUS_UNCONFIGURED: Final = "unconfigured"


def _utc_now() -> datetime:
    """Return the current instant, in UTC."""
    return datetime.now(UTC)


def installed_version() -> str:
    """Return the installed distribution's version, or a sentence saying there is none."""
    try:
        return _distribution_version("ninjasre")
    except PackageNotFoundError:
        return UNKNOWN_VERSION


_ENGINE: Any = None


def _scan(value: str) -> str:
    """Return ``value`` with every guardrail match redacted.

    The engine is built on first use rather than at import: it loads an
    operator-editable ruleset, which is not work an import should do.
    """
    global _ENGINE
    if _ENGINE is None:
        from platform.guardrails.engine import GuardrailEngine

        _ENGINE = GuardrailEngine()
    result: Any = _ENGINE.scan(value)
    return str(result.text)


def _scrubbed(value: Any) -> Any:
    """Return ``value`` with every string inside it scanned."""
    if isinstance(value, str):
        return _scan(value)
    if isinstance(value, Mapping):
        return {key: _scrubbed(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_scrubbed(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class IntegrationHealth:
    """Which integrations work, which are broken, and which were never set up."""

    healthy: tuple[str, ...] = ()
    unhealthy: tuple[str, ...] = ()
    unconfigured: tuple[str, ...] = ()

    @property
    def all_healthy(self) -> bool:
        """Return whether anything is actually broken.

        An unconfigured integration is not broken. A deployment that reported
        sixty problems on its first day would be one whose health output nobody
        reads by the second.
        """
        return not self.unhealthy

    def headline(self) -> str:
        """Return the one line a shell prompt or a status bar shows."""
        parts = [
            f"{len(self.healthy)} healthy" if self.healthy else "",
            f"{len(self.unhealthy)} unhealthy" if self.unhealthy else "",
            f"{len(self.unconfigured)} not configured" if self.unconfigured else "",
        ]
        stated = [part for part in parts if part]
        return ", ".join(stated) if stated else "no integrations configured"

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a surface prints."""
        return {
            "headline": self.headline(),
            "all_healthy": self.all_healthy,
            "healthy": list(self.healthy),
            "unhealthy": list(self.unhealthy),
            "unconfigured": list(self.unconfigured),
        }


def health_summary(statuses: Iterable[Mapping[str, Any]]) -> IntegrationHealth:
    """Return the three-way split of ``statuses``, each group sorted by name."""
    healthy: list[str] = []
    unhealthy: list[str] = []
    unconfigured: list[str] = []
    for status in statuses:
        name = str(status.get("integration", ""))
        if not status.get("configured", False):
            unconfigured.append(name)
        elif status.get("healthy", False):
            healthy.append(name)
        else:
            unhealthy.append(name)
    return IntegrationHealth(
        healthy=tuple(sorted(healthy)),
        unhealthy=tuple(sorted(unhealthy)),
        unconfigured=tuple(sorted(unconfigured)),
    )


def record_integration_health(
    metrics: MetricRegistry,
    statuses: Iterable[Mapping[str, Any]],
) -> None:
    """Write one gauge point per integration, labelled with its state.

    The integration name is a label and the catalogue bounds it, which is why
    this is a metric at all: eighty-five is a dimension, and a pod name is not.
    """
    gauge = metrics.gauge("integration.health")
    for status in statuses:
        name = str(status.get("integration", ""))
        if not status.get("configured", False):
            gauge.set(0.0, integration=name, status=STATUS_UNCONFIGURED)
        elif status.get("healthy", False):
            gauge.set(1.0, integration=name, status=STATUS_HEALTHY)
        else:
            gauge.set(0.0, integration=name, status=STATUS_UNHEALTHY)


@dataclass(frozen=True, slots=True)
class DiagnosticBundle:
    """Everything an operator would otherwise have collected by hand, redacted."""

    generated_at: datetime
    version: str
    configuration: dict[str, str] = field(default_factory=dict)
    logs: tuple[str, ...] = ()
    health: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    integrations: IntegrationHealth = field(default_factory=IntegrationHealth)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form of the whole bundle."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "version": self.version,
            "configuration": dict(self.configuration),
            "logs": list(self.logs),
            "health": dict(self.health),
            "telemetry": dict(self.telemetry),
            "integrations": self.integrations.to_record(),
        }

    def render(self) -> str:
        """Return the bundle as a document a person reads before sharing it.

        Markdown rather than JSON, because the decision this artefact exists to
        support — "am I willing to send this" — is one somebody makes by reading
        it, and a wall of JSON is one they make by not reading it.
        """
        lines = [
            "# NinjaSRE diagnostic bundle",
            "",
            f"Generated: {self.generated_at.isoformat()}",
            f"Version: {self.version}",
            "",
            "Nothing here was transmitted. Read it, then decide.",
            "",
            "## Configuration",
            "",
        ]
        lines.extend(f"- `{name}` = {value}" for name, value in sorted(self.configuration.items()))
        lines.extend(["", "## Integrations", "", self.integrations.headline(), ""])
        if self.integrations.unhealthy:
            lines.extend(f"- unhealthy: `{name}`" for name in self.integrations.unhealthy)
            lines.append("")
        lines.extend(["## Telemetry", ""])
        lines.extend(f"- {name}: {value}" for name, value in sorted(self.telemetry.items()))
        lines.extend(["", "## Health", ""])
        lines.extend(f"- {name}: {value}" for name, value in sorted(self.health.items()))
        lines.extend(["", "## Recent logs", "", "```"])
        lines.extend(self.logs)
        lines.extend(["```", ""])
        return "\n".join(lines)


def build_bundle(
    *,
    environ: Mapping[str, str] | None = None,
    logs: Sequence[str] = (),
    health: Mapping[str, Any] | None = None,
    exporter: OtlpExporter | None = None,
    integrations: IntegrationHealth | None = None,
    at: datetime | None = None,
) -> DiagnosticBundle:
    """Return a bundle from what this process can see, with nothing sensitive in it.

    Every argument is injected rather than discovered, because a bundle is an
    artefact the operator produced from a specific moment and a function that
    went looking for its own inputs would produce a different one each time it
    was called.
    """
    source = os.environ if environ is None else environ
    return DiagnosticBundle(
        generated_at=at or _utc_now(),
        version=installed_version(),
        configuration=_configuration(source),
        logs=tuple(_scan(line) for line in logs),
        health=dict(_scrubbed(dict(health or {}))),
        telemetry=dict(_scrubbed(exporter.to_record())) if exporter else {},
        integrations=integrations or IntegrationHealth(),
    )


def _configuration(source: Mapping[str, str]) -> dict[str, str]:
    """Return the documented settings this environment sets, redacted.

    Allow-listed by the settings catalogue, so the variable nobody anticipated
    is absent rather than filtered — which is the difference between a control
    that holds for what exists today and one that holds for what is added
    tomorrow.
    """
    documented = {}
    for setting in SETTINGS:
        value = source.get(setting.name)
        if value is None:
            continue
        documented[setting.name] = REDACTED if setting.secret else _scan(value)
    return documented


__all__ = [
    "REDACTED",
    "STATUS_HEALTHY",
    "STATUS_UNCONFIGURED",
    "STATUS_UNHEALTHY",
    "UNKNOWN_VERSION",
    "DiagnosticBundle",
    "IntegrationHealth",
    "build_bundle",
    "health_summary",
    "installed_version",
    "record_integration_health",
]
