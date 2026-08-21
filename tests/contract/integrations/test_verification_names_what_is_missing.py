"""SC-005, per integration: a denied permission is named, not summarised.

The requirement is easy to satisfy in a framework and easy to lose in a vendor.
The framework's own tests prove that a denied probe becomes a named permission
in a report; what they cannot prove is that *this* vendor declared its
permissions, wrote a probe for each, and named the capabilities that stop
working. A verifier that declares nothing passes every framework test and tells
an operator "the credential works" about a credential that cannot do the job.

So these run each installed verifier against a vendor that refuses everything,
through the real proxy, and read the message the operator would read.

The second half is the one worth reading twice:
``test_a_resource_that_is_not_there_is_not_reported_as_a_missing_permission``.
Probes commonly name an object that does not exist — that is what makes them
cheap — and a vendor answering 404 has *permitted* the call. Reading that as a
denial sends an operator into an IAM console after a policy that is already
correct, which is an hour spent proving nothing was wrong.
"""

from __future__ import annotations

import pytest

from integrations._verification.framework import VerificationRunner, runner_for
from integrations._verification.permissions import ProbeState
from integrations._verification.reporting import report_message, summary_line
from platform.credentials.proxy.model import OutboundResponse
from tests.contract.integrations.conftest import (
    CATALOGUE,
    CONTEXT,
    CREDENTIALS,
    ENTRIES,
    integration_ids,
    stand_up,
)

pytestmark = pytest.mark.contract

IDS = integration_ids()
DESCRIPTORS = [entry.descriptor for entry in CATALOGUE]


def runner() -> VerificationRunner:
    """Return a runner over every installed integration's verifier."""
    return runner_for(DESCRIPTORS)


@pytest.mark.parametrize("name", IDS)
def test_the_verifier_probes_every_permission_it_declares(name: str) -> None:
    """A declared permission with no probe is a permission nobody checks."""
    entry = ENTRIES[name]
    probed = {probe.permission.name for probe in entry.descriptor.verifier.probes()}
    declared = {permission.name for permission in entry.profile.permissions}

    assert declared, f"{name}: declares no permission, so verification proves only connectivity"
    assert declared <= probed, f"{name}: declares {sorted(declared - probed)} and probes nothing"


@pytest.mark.parametrize("name", IDS)
def test_every_permission_says_what_stops_working_without_it(name: str) -> None:
    """FR-010's actionable half: an operator who does not know a permission name
    still knows whether they care about the capability."""
    entry = ENTRIES[name]
    declared = set(entry.capabilities)

    for permission in entry.profile.permissions:
        assert permission.capabilities, f"{name}: {permission.name} names no capability"
        assert set(permission.capabilities) <= declared, (
            f"{name}: {permission.name} names a capability this integration does not declare"
        )
        assert permission.where.strip(), (
            f"{name}: {permission.name} does not say where it is granted, so the operator's "
            f"next step is a search"
        )


@pytest.mark.parametrize("name", IDS)
async def test_a_working_credential_verifies_with_every_permission_granted(name: str) -> None:
    transport, _ = await stand_up(DESCRIPTORS, seeded=(name,))

    report = await runner().verify(name, transport=transport, context=CONTEXT)

    assert report.ok, report_message(report)
    assert all(outcome.granted for outcome in report.permissions)
    assert report.missing_permissions == ()


@pytest.mark.parametrize("name", IDS)
async def test_a_refused_permission_is_named_in_the_operators_message(name: str) -> None:
    """SC-005. Every probe is refused, so every declared permission is named."""
    entry = ENTRIES[name]
    transport, vendor = await stand_up(DESCRIPTORS, seeded=(name,))
    # The first response answers connectivity; the rest answer the probes.
    vendor.responses.append(OutboundResponse(200, {"content-type": "application/json"}, b"{}"))
    vendor.responses.extend(
        OutboundResponse(403, {}, b"forbidden") for _ in entry.profile.permissions
    )

    report = await runner().verify(name, transport=transport, context=CONTEXT)
    message = report_message(report)

    assert not report.ok
    assert set(report.missing_permissions) == {
        permission.name for permission in entry.profile.permissions
    }
    for permission in entry.profile.permissions:
        assert permission.name in message
        assert permission.where in message
        for capability in permission.capabilities:
            assert capability in message


@pytest.mark.parametrize("name", IDS)
async def test_a_resource_that_is_not_there_is_not_reported_as_a_missing_permission(
    name: str,
) -> None:
    """A 404 means the call was permitted. The probes deliberately name absent
    objects, so reading it as a denial would fail every integration here."""
    entry = ENTRIES[name]
    transport, vendor = await stand_up(DESCRIPTORS, seeded=(name,))
    vendor.responses.append(OutboundResponse(200, {"content-type": "application/json"}, b"{}"))
    vendor.responses.extend(
        OutboundResponse(404, {}, b"not found") for _ in entry.profile.permissions
    )

    report = await runner().verify(name, transport=transport, context=CONTEXT)

    assert report.missing_permissions == ()
    assert all(outcome.granted for outcome in report.permissions)


@pytest.mark.parametrize("name", IDS)
async def test_a_rejected_credential_leaves_every_permission_unchecked(name: str) -> None:
    """Reporting them denied would send an operator to re-issue scopes on a key
    that simply needs replacing."""
    transport, vendor = await stand_up(DESCRIPTORS, seeded=(name,))
    vendor.responses.append(OutboundResponse(401, {}, b"unauthorized"))

    report = await runner().verify(name, transport=transport, context=CONTEXT)

    assert not report.ok
    assert report.missing_permissions == ()
    assert all(outcome.state is ProbeState.UNCHECKED for outcome in report.permissions)


@pytest.mark.parametrize("name", IDS)
async def test_no_verification_report_carries_the_credential_it_checked(name: str) -> None:
    transport, _ = await stand_up(DESCRIPTORS, seeded=(name,))

    report = await runner().verify(name, transport=transport, context=CONTEXT)
    rendered = f"{report.to_record()}{report_message(report)}"

    for field in ENTRIES[name].descriptor.schema.secret_names:
        value = CREDENTIALS[name].get(field)
        if value:
            assert value not in rendered


@pytest.mark.parametrize("name", IDS)
def test_the_probe_that_proves_connectivity_is_documented(name: str) -> None:
    """FR-011. A vendor with no verification endpoint may use its cheapest read,
    on condition that the substitution is written down."""
    verifier = ENTRIES[name].descriptor.verifier

    assert len(verifier.probe_description.split()) > 5, (
        f"{name}: 'it makes a call' is not a description an operator can interpret"
    )


async def test_one_command_verifies_the_whole_catalogue() -> None:
    """The command an operator runs after onboarding, and the one CI runs."""
    transport, _ = await stand_up(DESCRIPTORS, seeded=tuple(CREDENTIALS))

    reports = await runner().verify_all(transport=transport, context=CONTEXT)

    assert tuple(report.integration for report in reports) == IDS
    assert summary_line(reports) == f"{len(reports)} integration(s) verified"
