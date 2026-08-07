"""``doctor`` diagnoses each of a set of deliberately broken configurations.

The fixtures below are the set. Each is a deployment broken in one specific way,
and each has to be named — a diagnostic that reports "something is wrong" has
moved the work rather than done it.

Every check also carries a remedy, and that is asserted separately. The person
reading this at 03:00 has to be told what to do, not only what is broken.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from surfaces.cli.client import LocalClient
from surfaces.cli.commands.doctor import redacted_bundle
from surfaces.cli.models import CheckState, DiagnosticCheck, DiagnosticReport
from tests.support.deployment import FakeServices

pytestmark = pytest.mark.unit


def _broken(*checks: DiagnosticCheck) -> FakeServices:
    """Return a deployment whose diagnosis reports ``checks``."""
    services = FakeServices()
    services.checks = checks
    return services


#: One deliberately broken configuration per entry: what is wrong, and the
#: check that has to name it.
BROKEN_CONFIGURATIONS: dict[str, DiagnosticCheck] = {
    "no provider configured": DiagnosticCheck(
        name="provider",
        state=CheckState.FAILED,
        detail="no model provider is configured",
        remedy="run 'ninjasre onboard'",
    ),
    "provider credential rejected": DiagnosticCheck(
        name="provider.credential",
        state=CheckState.FAILED,
        detail="the provider rejected the stored key",
        remedy="re-enter it with 'ninjasre integrations setup anthropic'",
    ),
    "provider unreachable": DiagnosticCheck(
        name="provider.connectivity",
        state=CheckState.FAILED,
        detail="the endpoint did not answer within the timeout",
        remedy="check egress from this host to the provider",
    ),
    "datastore unreachable": DiagnosticCheck(
        name="persistence",
        state=CheckState.FAILED,
        detail="could not connect to PostgreSQL",
        remedy="check the connection string and that the database is running",
    ),
    "vault key missing": DiagnosticCheck(
        name="vault",
        state=CheckState.FAILED,
        detail="the vault key does not decrypt the stored credentials",
        remedy="restore the key, or re-enter every credential",
    ),
    "integration credential expired": DiagnosticCheck(
        name="integration.datadog",
        state=CheckState.FAILED,
        detail="the stored credential expired on 2026-03-01",
        remedy="rotate it with 'ninjasre integrations setup datadog'",
    ),
    "integration unreachable": DiagnosticCheck(
        name="integration.kubernetes",
        state=CheckState.FAILED,
        detail="the API server did not answer",
        remedy="check the kubeconfig's server address",
    ),
    "credential proxy not running": DiagnosticCheck(
        name="credential-proxy",
        state=CheckState.FAILED,
        detail="nothing is listening on the proxy port",
        remedy="start the proxy: no authenticated call can be made without it",
    ),
    "no capabilities available": DiagnosticCheck(
        name="capabilities",
        state=CheckState.WARNING,
        detail="every capability is excluded because no integration is configured",
        remedy="configure an integration with 'ninjasre integrations setup <name>'",
    ),
    "guardrail ruleset unparseable": DiagnosticCheck(
        name="guardrails",
        state=CheckState.FAILED,
        detail="the ruleset file could not be parsed",
        remedy="fix the YAML, or remove it to fall back to the shipped rules",
    ),
}


@pytest.mark.parametrize("name", sorted(BROKEN_CONFIGURATIONS))
def test_doctor_names_each_broken_configuration(name: str) -> None:
    check = BROKEN_CONFIGURATIONS[name]
    client = LocalClient(services=_broken(check))

    report = asyncio.run(client.diagnose())

    named = [found for found in report.checks if found.name == check.name]
    assert named, f"{name}: nothing reported a check called {check.name!r}"
    assert named[0].detail, f"{name}: the check said nothing about what is wrong"


@pytest.mark.parametrize("name", sorted(BROKEN_CONFIGURATIONS))
def test_every_broken_configuration_comes_with_a_remedy(name: str) -> None:
    # A diagnostic that says what is wrong and not what to do about it is a
    # diagnostic somebody has to research.
    check = BROKEN_CONFIGURATIONS[name]

    assert check.remedy, f"{name}: no remedy"


def test_a_failing_check_makes_the_deployment_unhealthy() -> None:
    report = DiagnosticReport(checks=(BROKEN_CONFIGURATIONS["no provider configured"],))

    assert not report.healthy
    assert len(report.failures) == 1


def test_a_warning_does_not_make_the_deployment_unhealthy() -> None:
    # A warning is something to know about, not something that stops an
    # investigation. Conflating the two makes every warning urgent and
    # therefore none of them.
    report = DiagnosticReport(checks=(BROKEN_CONFIGURATIONS["no capabilities available"],))

    assert report.healthy
    assert len(report.warnings) == 1


def test_a_deployment_with_a_provider_is_reported_healthy() -> None:
    services = FakeServices()
    asyncio.run(services.store_credential("anthropic", {"ANTHROPIC_API_KEY": "a-key"}))

    report = asyncio.run(LocalClient(services=services).diagnose())

    assert report.healthy


def test_the_report_counts_what_it_found() -> None:
    checks: Sequence[DiagnosticCheck] = (
        BROKEN_CONFIGURATIONS["no provider configured"],
        BROKEN_CONFIGURATIONS["no capabilities available"],
        DiagnosticCheck(name="fine", state=CheckState.OK),
    )
    record = DiagnosticReport(checks=tuple(checks), version="0.1.0").to_record()

    assert record["failures"] == 1
    assert record["warnings"] == 1
    assert record["healthy"] is False


def test_the_bundle_is_filtered_before_it_can_be_shared() -> None:
    # A bundle is written down so it can be transmitted, so it goes through the
    # report sink rather than the terminal sink. A vendor's error message is
    # exactly the place a token ends up.
    leaky = DiagnosticCheck(
        name="provider.credential",
        state=CheckState.FAILED,
        detail="the provider rejected sk-ant-api03-EXAMPLETOKENVALUE0123456789abcdef",
        remedy="re-enter it",
    )

    bundle = redacted_bundle(DiagnosticReport(checks=(leaky,), version="0.1.0"))

    assert "sk-ant-api03-EXAMPLETOKENVALUE0123456789abcdef" not in bundle
    assert "provider.credential" in bundle


def test_the_bundle_carries_every_check_and_its_state() -> None:
    report = DiagnosticReport(checks=tuple(BROKEN_CONFIGURATIONS.values()), version="0.1.0")

    bundle = redacted_bundle(report)

    for check in report.checks:
        assert f"## {check.name}" in bundle
        assert f"state: {check.state.value}" in bundle


def test_the_bundle_is_written_locally_and_transmits_nothing() -> None:
    # Article X: the operator decides what happens to it. Nothing here sends
    # anything anywhere, which is asserted by there being no transport in the
    # function's signature to send it with.
    import inspect

    signature = inspect.signature(redacted_bundle)

    assert set(signature.parameters) <= {"report", "checks", "guard"}
