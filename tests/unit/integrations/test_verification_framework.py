"""FR-009 to FR-011. "It works" is not an answer an operator can act on.

A verifier that reports success or failure has answered half the question. The
half it left out is the one that costs an hour: the credential is fine, the
integration reaches the vendor, and one of the four capabilities it advertises
cannot run because the token was issued without a scope nobody mentioned. That
failure surfaces during an incident, as a tool error, with no indication that it
was knowable at setup time.

So verification is two things and reports both: connectivity, and each specific
permission the integration's capabilities need. The tests below are about the
distinctions that make the report worth reading —

* a denied permission is named, with what stops working without it;
* a 404 is *not* a denied permission, because the call was permitted and the
  resource simply is not there. Reading it as a denial sends an operator to
  their vendor's IAM console for a problem that is not there;
* a rejected credential makes every permission *unchecked* rather than denied,
  because nothing was learned about them;
* a vendor with no verification endpoint says which read it used instead.
"""

from __future__ import annotations

import pytest

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._verification.framework import (
    Connectivity,
    VerificationReport,
    VerificationRunner,
)
from integrations._verification.permissions import (
    PermissionProbe,
    ProbeState,
    RequiredPermission,
)
from integrations._verification.reporting import report_message

READ_LOGS = RequiredPermission(
    name="logs:FilterLogEvents",
    grants="read log events from a log group",
    capabilities=("acme_log_statistics", "acme_sample_logs"),
    where="the IAM policy attached to the access key",
)
READ_METRICS = RequiredPermission(
    name="cloudwatch:GetMetricData",
    grants="read metric series",
    capabilities=("acme_metric_series",),
)


def failing(reason: IntegrationErrorReason, *, status: int | None = None):
    """Return a probe call that raises the classified failure ``reason``."""

    async def call(transport: object, context: object) -> object:
        raise IntegrationError("refused", integration="acme", reason=reason, status_code=status)

    return call


async def succeeding(transport: object, context: object) -> object:
    """A probe call the vendor answered."""
    return {"ok": True}


class Verifier:
    """A verifier double whose connectivity and probes are scripted."""

    def __init__(
        self,
        *,
        integration: str = "acme",
        connectivity: Connectivity | None = None,
        probes: tuple[PermissionProbe, ...] = (),
        probe_description: str = "lists one monitor, the cheapest call Acme offers",
    ) -> None:
        self._integration = integration
        self._connectivity = connectivity or Connectivity(reachable=True, status_code=200)
        self._probes = probes
        self._probe_description = probe_description

    @property
    def integration(self) -> str:
        return self._integration

    @property
    def probe_description(self) -> str:
        return self._probe_description

    def probes(self) -> tuple[PermissionProbe, ...]:
        return self._probes

    async def connect(self, transport: object, context: object) -> Connectivity:
        return self._connectivity


async def run(verifier: Verifier) -> VerificationReport:
    """Run ``verifier`` through the framework and return its report."""
    runner = VerificationRunner([verifier])
    return await runner.verify(verifier.integration, transport=object(), context=object())


async def test_a_working_integration_reports_connectivity_and_every_permission() -> None:
    report = await run(
        Verifier(
            probes=(
                PermissionProbe(permission=READ_LOGS, call=succeeding),
                PermissionProbe(permission=READ_METRICS, call=succeeding),
            )
        )
    )

    assert report.ok
    assert report.connectivity.reachable
    assert [outcome.state for outcome in report.permissions] == [
        ProbeState.GRANTED,
        ProbeState.GRANTED,
    ]


async def test_a_missing_permission_is_named_rather_than_reported_as_a_failure() -> None:
    """FR-010, and the whole reason this framework exists."""
    report = await run(
        Verifier(
            probes=(
                PermissionProbe(
                    permission=READ_LOGS, call=failing(IntegrationErrorReason.FORBIDDEN)
                ),
                PermissionProbe(permission=READ_METRICS, call=succeeding),
            )
        )
    )

    assert not report.ok
    assert report.missing_permissions == ("logs:FilterLogEvents",)
    message = report_message(report)
    assert "logs:FilterLogEvents" in message
    assert "acme_log_statistics" in message, "an operator has to know what stops working"
    assert "IAM policy" in message, "and where to go and fix it"


async def test_a_resource_that_is_not_there_is_not_a_missing_permission() -> None:
    """A 404 means the call was permitted. Reading it as a denial sends an
    operator to an IAM console for a problem that is not in one."""
    report = await run(
        Verifier(
            probes=(
                PermissionProbe(
                    permission=READ_LOGS, call=failing(IntegrationErrorReason.NOT_FOUND)
                ),
            )
        )
    )

    assert report.permissions[0].state is ProbeState.GRANTED
    assert report.ok


async def test_a_rejected_credential_leaves_permissions_unchecked_rather_than_denied() -> None:
    """Nothing was learned about them, and saying otherwise sends the operator
    to re-issue scopes on a key that is simply wrong."""
    report = await run(
        Verifier(
            connectivity=Connectivity(
                reachable=False, detail="Acme rejected the key", status_code=401
            ),
            probes=(PermissionProbe(permission=READ_LOGS, call=succeeding),),
        )
    )

    assert not report.ok
    assert report.permissions[0].state is ProbeState.UNCHECKED
    assert report.missing_permissions == ()
    assert "rejected the key" in report_message(report)


async def test_a_permission_the_vendor_cannot_introspect_is_inconclusive_not_granted() -> None:
    """SC-005 is only claimed for vendors that support introspection, and this
    is how the ones that do not say so instead of quietly passing."""
    report = await run(
        Verifier(
            probes=(
                PermissionProbe(
                    permission=READ_LOGS, call=failing(IntegrationErrorReason.UPSTREAM_ERROR)
                ),
            )
        )
    )

    assert report.permissions[0].state is ProbeState.INCONCLUSIVE
    assert "could not be checked" in report_message(report)


async def test_a_vendor_with_no_verification_endpoint_says_which_read_it_used() -> None:
    """FR-011. The fallback is documented rather than implied."""
    probe = PermissionProbe(
        permission=READ_LOGS,
        call=succeeding,
        fallback_note="Acme has no permissions endpoint; this reads one log group, the "
        "cheapest call the capability itself makes",
    )
    report = await run(Verifier(probes=(probe,)))

    assert probe.is_fallback
    assert "no permissions endpoint" in report_message(report)


async def test_the_report_carries_no_credential_and_serialises_for_a_console() -> None:
    report = await run(Verifier(probes=(PermissionProbe(permission=READ_LOGS, call=succeeding),)))
    record = report.to_record()

    assert record["integration"] == "acme"
    assert record["ok"] is True
    assert record["permissions"][0]["permission"] == "logs:FilterLogEvents"


async def test_every_declared_verifier_is_run_by_one_command() -> None:
    """The command an operator runs after onboarding, and the one CI runs."""
    runner = VerificationRunner([Verifier(integration="acme"), Verifier(integration="zenith")])

    reports = await runner.verify_all(transport=object(), context=object())

    assert tuple(report.integration for report in reports) == ("acme", "zenith")


async def test_an_integration_nobody_installed_is_named_rather_than_guessed() -> None:
    runner = VerificationRunner([Verifier(integration="acme")])

    with pytest.raises(LookupError) as raised:
        await runner.verify("typo", transport=object(), context=object())

    assert "acme" in str(raised.value)


def test_a_verifier_that_will_not_say_what_it_probes_is_refused() -> None:
    """FR-011 says the probe is documented; an empty string is not documentation."""
    with pytest.raises(ValueError, match="what call proves"):
        VerificationRunner([Verifier(probe_description="  ")])
