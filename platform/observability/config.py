"""What telemetry is pointed at, and the fact that by default it is nothing.

One setting turns this on: the collector's base URL. Unset — which is what a
fresh deployment has — nothing is built, nothing is queued, and no socket is
opened. That is not a policy applied at export time; it is the absence of a
destination, which is a much harder thing to accidentally undo.

The asymmetry is deliberate. An operator who wants observability configures a
collector, and gets traces, metrics, and logs on the same endpoint. An operator
who wants nothing to leave their host does nothing, and nothing does.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from config.constants.deployment import NINJASRE_OTEL_ENDPOINT_ENV
from config.constants.observability import (
    DEFAULT_TELEMETRY_SAMPLE_RATIO,
    DEFAULT_TELEMETRY_SERVICE_NAME,
    NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV,
    NINJASRE_TELEMETRY_SERVICE_NAME_ENV,
    OTLP_SIGNAL_PATHS,
    TELEMETRY_EXPORT_TIMEOUT_SECONDS,
    TelemetrySignal,
)

#: The schemes a collector may be reached over. Anything else is a
#: misconfiguration that would otherwise fail once per export rather than once.
_PERMITTED_SCHEMES = ("http", "https")


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """Where telemetry goes, and how much of it.

    Frozen, because a deployment that could change its export target mid-run
    would produce a trace split across two collectors with no record of when it
    moved.
    """

    endpoint: str = ""
    service_name: str = DEFAULT_TELEMETRY_SERVICE_NAME
    sample_ratio: float = DEFAULT_TELEMETRY_SAMPLE_RATIO
    timeout_seconds: float = TELEMETRY_EXPORT_TIMEOUT_SECONDS

    @property
    def enabled(self) -> bool:
        """Return whether anything is exported at all.

        A configured endpoint *is* the enable switch. A separate boolean would
        allow the state nobody wants — enabled with nowhere to go, which fails
        once per export and reads as a broken collector.
        """
        return bool(self._base())

    def url_for(self, signal: TelemetrySignal) -> str:
        """Return the collector URL for one signal.

        Raises:
            ValueError: no endpoint is configured. Asking where a disabled
                deployment exports to is a caller that skipped ``enabled``.
        """
        base = self._base()
        if not base:
            raise ValueError(
                "no telemetry endpoint is configured; check `enabled` before asking for a URL"
            )
        return f"{base}{OTLP_SIGNAL_PATHS[signal.value]}"

    def samples(self, draw: float) -> bool:
        """Return whether a trace whose sampling draw is ``draw`` is exported."""
        if not self.enabled:
            return False
        return draw < self.sample_ratio

    def _base(self) -> str:
        """Return the endpoint without its trailing slash, or nothing."""
        return self.endpoint.strip().rstrip("/")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> TelemetryConfig:
        """Return the configuration this process's environment describes.

        A malformed sample ratio falls back to the default rather than refusing
        to start. Telemetry is the subsystem that must never be the reason an
        investigation does not happen, and that has to hold at configuration
        time as well as at export time.
        """
        source = os.environ if environ is None else environ
        endpoint = source.get(NINJASRE_OTEL_ENDPOINT_ENV, "").strip()
        if endpoint and not _is_reachable(endpoint):
            endpoint = ""

        service_name = (
            source.get(NINJASRE_TELEMETRY_SERVICE_NAME_ENV, "").strip()
            or DEFAULT_TELEMETRY_SERVICE_NAME
        )
        return cls(
            endpoint=endpoint,
            service_name=service_name,
            sample_ratio=_ratio(source.get(NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV, "")),
        )

    def resource_attributes(self) -> dict[str, str]:
        """Return the resource every exported record carries.

        Deliberately three fields and no more. A resource that named the host,
        the pod, and the container would put an unbounded identifier on every
        metric stream, which is exactly what the cardinality bounds exist to
        prevent — and doing it in the resource would evade them.
        """
        return {"service.name": self.service_name}


def _is_reachable(endpoint: str) -> bool:
    """Return whether ``endpoint`` is a URL an exporter could post to."""
    parsed = urlsplit(endpoint)
    return parsed.scheme in _PERMITTED_SCHEMES and bool(parsed.netloc)


def _ratio(raw: str) -> float:
    """Return the sampling ratio ``raw`` asks for, clamped into range."""
    try:
        value = float(raw.strip())
    except ValueError:
        return DEFAULT_TELEMETRY_SAMPLE_RATIO
    return min(1.0, max(0.0, value))


__all__ = ["TelemetryConfig"]
