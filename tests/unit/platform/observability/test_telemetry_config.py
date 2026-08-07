"""Disabled by default, and enabled by exactly one setting.

The property worth testing is not that a boolean defaults to ``False``. It is
that there is no state in which the deployment believes it is exporting and has
nowhere to export to, because that state produces an error per investigation and
reads to an operator as a broken collector rather than as a missing setting.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import NINJASRE_OTEL_ENDPOINT_ENV
from config.constants.observability import (
    DEFAULT_TELEMETRY_SERVICE_NAME,
    NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV,
    NINJASRE_TELEMETRY_SERVICE_NAME_ENV,
    TelemetrySignal,
)
from platform.observability.config import TelemetryConfig

pytestmark = pytest.mark.unit


def test_the_default_is_off() -> None:
    assert TelemetryConfig().enabled is False


def test_an_empty_environment_is_off() -> None:
    assert TelemetryConfig.from_environment({}).enabled is False


def test_one_setting_turns_it_on() -> None:
    config = TelemetryConfig.from_environment(
        {NINJASRE_OTEL_ENDPOINT_ENV: "https://collector.internal:4318"}
    )

    assert config.enabled is True
    assert config.url_for(TelemetrySignal.TRACES) == "https://collector.internal:4318/v1/traces"
    assert config.url_for(TelemetrySignal.METRICS) == "https://collector.internal:4318/v1/metrics"
    assert config.url_for(TelemetrySignal.LOGS) == "https://collector.internal:4318/v1/logs"


def test_a_trailing_slash_does_not_produce_a_doubled_path() -> None:
    config = TelemetryConfig(endpoint="http://collector:4318/")

    assert config.url_for(TelemetrySignal.TRACES) == "http://collector:4318/v1/traces"


@pytest.mark.parametrize("endpoint", ["", "   ", "collector:4318", "ftp://collector", "http://"])
def test_an_endpoint_that_is_not_a_url_leaves_the_deployment_off(endpoint: str) -> None:
    """Refusing to start would make telemetry able to stop an investigation."""
    config = TelemetryConfig.from_environment({NINJASRE_OTEL_ENDPOINT_ENV: endpoint})

    assert config.enabled is False


def test_asking_a_disabled_deployment_where_it_exports_is_an_error() -> None:
    with pytest.raises(ValueError, match="no telemetry endpoint"):
        TelemetryConfig().url_for(TelemetrySignal.TRACES)


def test_the_service_name_defaults_and_is_overridable() -> None:
    assert TelemetryConfig().service_name == DEFAULT_TELEMETRY_SERVICE_NAME

    config = TelemetryConfig.from_environment(
        {
            NINJASRE_OTEL_ENDPOINT_ENV: "http://collector:4318",
            NINJASRE_TELEMETRY_SERVICE_NAME_ENV: "ninjasre-eu",
        }
    )

    assert config.service_name == "ninjasre-eu"
    assert config.resource_attributes() == {"service.name": "ninjasre-eu"}


def test_the_resource_carries_no_unbounded_identifier() -> None:
    """A host or pod name in the resource evades the label bounds entirely."""
    attributes = TelemetryConfig(endpoint="http://collector:4318").resource_attributes()

    assert set(attributes) == {"service.name"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.1", 0.1), ("1", 1.0), ("0", 0.0), ("-3", 0.0), ("17", 1.0), ("", 1.0), ("half", 1.0)],
)
def test_the_sample_ratio_is_clamped_and_never_refuses_to_start(raw: str, expected: float) -> None:
    config = TelemetryConfig.from_environment(
        {
            NINJASRE_OTEL_ENDPOINT_ENV: "http://collector:4318",
            NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV: raw,
        }
    )

    assert config.sample_ratio == expected


def test_sampling_never_fires_while_disabled() -> None:
    assert TelemetryConfig().samples(0.0) is False


def test_sampling_admits_the_share_it_was_asked_for() -> None:
    config = TelemetryConfig(endpoint="http://collector:4318", sample_ratio=0.25)

    assert config.samples(0.2) is True
    assert config.samples(0.3) is False
