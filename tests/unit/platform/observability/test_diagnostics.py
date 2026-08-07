"""The bundle an operator can read before deciding to share it.

There is no telemetry, so nothing sends a crash report on its own. What replaces
it is a local archive the operator produces deliberately, reads, and then hands
over — or does not. That only works if the archive is genuinely safe to hand
over, which is the property this file is about.

The dangerous half is the configuration. An operator's environment holds the
database URL with a password in it, a vault key, and a provider token, and a
bundle that dumped ``os.environ`` would be the single worst artefact this
project could produce. So the rule is an allow-list on names *and* a scan of
every value, and the tests assert both — because either one alone fails on the
setting nobody anticipated.
"""

from __future__ import annotations

import json

import pytest

from config.constants.deployment import NINJASRE_OTEL_ENDPOINT_ENV
from config.constants.persistence import (
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from config.constants.security import NINJASRE_VAULT_MASTER_KEY_ENV
from platform.observability.config import TelemetryConfig
from platform.observability.diagnostics import (
    REDACTED,
    DiagnosticBundle,
    IntegrationHealth,
    build_bundle,
    health_summary,
    record_integration_health,
)
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.definitions import MetricRegistry

pytestmark = pytest.mark.unit

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")

DANGEROUS_ENVIRONMENT = {
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre:hunter2@db.internal:5432/ninjasre",
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "3f9a1c8e5b2d7f04a6c9e1b3d5f7091a",
    NINJASRE_VAULT_MASTER_KEY_ENV: "c1d2e3f4a5b60718293a4b5c6d7e8f90",
    NINJASRE_OTEL_ENDPOINT_ENV: "http://collector.internal:4318",
    # Documented — a provider credential the catalogue names, so it is included
    # and redacted rather than absent.
    "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    # Undocumented. Whatever else happens to be exported in the operator's
    # shell, which is exactly what an allow-list has to keep out.
    "SOME_VENDOR_API_TOKEN": "tok-9f3c1b7e5a2d4086",
    "HOME": "/home/sre",
}


def bundle(**kwargs: object) -> DiagnosticBundle:
    """Return a bundle built from an environment that holds real secrets."""
    return build_bundle(environ=DANGEROUS_ENVIRONMENT, **kwargs)  # type: ignore[arg-type]


# -- what a bundle holds -------------------------------------------------------


def test_a_bundle_holds_the_four_things_it_was_asked_for() -> None:
    """Configuration without secrets, recent logs, health, and versions."""
    assert set(bundle().to_record()) == {
        "generated_at",
        "version",
        "configuration",
        "logs",
        "health",
        "telemetry",
        "integrations",
    }


def test_the_version_is_recorded_so_a_report_names_what_it_is_about() -> None:
    assert bundle().version


def test_recent_logs_are_carried_verbatim_after_the_scan() -> None:
    lines = ["investigation.started run=inv-1", "evidence.collected entries=17"]

    assert bundle(logs=lines).logs == tuple(lines)


def test_health_output_is_carried() -> None:
    assert bundle(health={"ready": True, "checks": 4}).health == {"ready": True, "checks": 4}


def test_the_telemetry_counters_are_carried_so_a_missing_dashboard_is_explicable() -> None:
    exporter = OtlpExporter(ENABLED, RecordingTransport())
    exporter.dropped = 3

    record = bundle(exporter=exporter).to_record()

    assert record["telemetry"]["endpoint"] == ENABLED.endpoint
    assert record["telemetry"]["dropped"] == 3


# -- no secret, ever (T026) ----------------------------------------------------


def test_no_secret_setting_reaches_the_bundle() -> None:
    configuration = bundle().configuration

    assert configuration[NINJASRE_DATABASE_ENCRYPTION_KEY_ENV] == REDACTED
    assert configuration[NINJASRE_VAULT_MASTER_KEY_ENV] == REDACTED


def test_a_password_inside_a_non_secret_setting_is_redacted_too() -> None:
    """The database URL is not marked secret and carries one anyway."""
    url = bundle().configuration[NINJASRE_DATABASE_URL_ENV]

    assert "hunter2" not in url


def test_a_setting_the_catalogue_does_not_name_is_absent_entirely() -> None:
    """An allow-list, so the variable nobody anticipated cannot leak by default."""
    configuration = bundle().configuration

    assert "SOME_VENDOR_API_TOKEN" not in configuration
    assert "HOME" not in configuration


def test_a_documented_provider_credential_is_redacted_rather_than_dropped() -> None:
    """Present and withheld, because "never set" is a different diagnosis."""
    assert bundle().configuration["AWS_SECRET_ACCESS_KEY"] == REDACTED


def test_a_harmless_setting_survives_so_the_bundle_is_worth_reading() -> None:
    assert bundle().configuration[NINJASRE_OTEL_ENDPOINT_ENV] == "http://collector.internal:4318"


def test_a_secret_in_a_log_line_is_redacted() -> None:
    carried = bundle(logs=["vendor.error key=AKIAIOSFODNN7EXAMPLE"]).logs

    assert "AKIAIOSFODNN7EXAMPLE" not in carried[0]


def test_a_secret_in_the_health_output_is_redacted() -> None:
    carried = bundle(health={"detail": "refused for AKIAIOSFODNN7EXAMPLE"}).health

    assert "AKIAIOSFODNN7EXAMPLE" not in str(carried)


def test_the_whole_serialised_bundle_holds_no_secret_this_test_planted() -> None:
    """The assertion that matters: one scan of the finished artefact."""
    document = json.dumps(
        bundle(
            logs=["vendor.error key=AKIAIOSFODNN7EXAMPLE"],
            health={"detail": "postgresql://ninjasre:hunter2@db.internal:5432/ninjasre"},
        ).to_record()
    )

    for planted in (
        "hunter2",
        "3f9a1c8e5b2d7f04a6c9e1b3d5f7091a",
        "c1d2e3f4a5b60718293a4b5c6d7e8f90",
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "tok-9f3c1b7e5a2d4086",
    ):
        assert planted not in document, f"{planted} reached the bundle"


def test_a_bundle_renders_as_a_document_an_operator_reads_before_sharing() -> None:
    text = bundle(logs=["investigation.started"]).render()

    assert text.startswith("# NinjaSRE diagnostic bundle")
    assert "investigation.started" in text
    assert "hunter2" not in text


def test_nothing_is_transmitted_by_building_one() -> None:
    """Article X: this is the local alternative to a crash reporter, not one."""
    import socket

    class Refuse:
        def __call__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("building a bundle opened a socket")

    original = socket.socket.connect
    socket.socket.connect = Refuse()  # type: ignore[method-assign]
    try:
        bundle(logs=["a"])
    finally:
        socket.socket.connect = original  # type: ignore[method-assign]


# -- integration health, visible without a dashboard (FR-024) ------------------


STATUSES = (
    {"integration": "grafana", "healthy": True, "configured": True, "detail": ""},
    {"integration": "pagerduty", "healthy": False, "configured": True, "detail": "401 from vendor"},
    {"integration": "datadog", "healthy": False, "configured": False, "detail": "no credential"},
)


def test_the_summary_separates_broken_from_not_configured() -> None:
    """ "Nobody set it up" and "it stopped working" need different actions."""
    summary = health_summary(STATUSES)

    assert summary.healthy == ("grafana",)
    assert summary.unhealthy == ("pagerduty",)
    assert summary.unconfigured == ("datadog",)


def test_the_summary_reads_as_one_line_at_a_shell_prompt() -> None:
    assert health_summary(STATUSES).headline() == "1 healthy, 1 unhealthy, 1 not configured"


def test_a_deployment_with_nothing_wrong_says_so() -> None:
    summary = health_summary([{"integration": "grafana", "healthy": True, "configured": True}])

    assert summary.all_healthy is True
    assert summary.headline() == "1 healthy"


def test_an_unhealthy_integration_makes_the_summary_not_healthy() -> None:
    assert health_summary(STATUSES).all_healthy is False


def test_health_is_recorded_as_a_gauge_per_integration() -> None:
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, RecordingTransport()))

    record_integration_health(metrics, STATUSES)
    gauge = metrics.gauge("integration.health")

    assert gauge.value(integration="grafana", status="healthy") == 1.0
    assert gauge.value(integration="pagerduty", status="unhealthy") == 0.0
    assert gauge.value(integration="datadog", status="unconfigured") == 0.0


def test_the_summary_is_carried_in_the_bundle() -> None:
    record = bundle(integrations=health_summary(STATUSES)).to_record()

    assert record["integrations"]["unhealthy"] == ["pagerduty"]
    assert record["integrations"]["headline"] == "1 healthy, 1 unhealthy, 1 not configured"


def test_an_empty_catalogue_is_a_sentence_rather_than_a_crash() -> None:
    assert health_summary(()).headline() == "no integrations configured"
    assert IntegrationHealth().all_healthy is True
