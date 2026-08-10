"""What a token has to be allowed to do, and what an operator is told is missing.

The privilege listing is the substance behind "a token with insufficient
privileges is refused with the list of what is missing, by name". These
assertions are about the *list*, not about the screen that renders it: a
refusal that names ``Sys.Syslog`` and says what stops working without it is
worth having whether it arrives over HTTP, in the console, or from the CLI.

Three tiers, and the middle one is the one worth reading twice. ``READ`` is what
this integration cannot work without, so a gap in it is a refusal. ``ADVISORY``
is granted by the role the operator is asked to create and is used by nothing
shipped today, so a gap in it is *reported and never refused* — refusing on it
would tell an operator their working token is broken. ``WRITE`` is the same
shape for the other direction: declared so it can be reported, never required,
because a verification that went red without it would push every operator
towards a token that can destroy a guest.
"""

from __future__ import annotations

import pytest

from integrations._catalogue.discovery import capabilities_of
from integrations.proxmox.privileges import (
    ADVISORY_PRIVILEGES,
    READ_PRIVILEGES,
    WRITE_PRIVILEGES,
    privilege_report,
)
from integrations.proxmox.schema import INTEGRATION
from integrations.proxmox.verifier import ProxmoxVerifier
from tests.support.proxmox import client_for

pytestmark = pytest.mark.unit

#: What a correctly-issued token holds, as the reference cluster reports it.
GRANTED = {
    "/": {"Sys.Audit": 1, "Datastore.Audit": 1, "Sys.Syslog": 1, "SDN.Audit": 1},
    "/vms": {"VM.Audit": 1},
    "/storage": {"Datastore.Audit": 1},
}


def _without(privilege: str) -> dict[str, dict[str, int]]:
    """Return ``GRANTED`` with ``privilege`` revoked wherever it was held."""
    return {
        path: {name: value for name, value in held.items() if name != privilege}
        for path, held in GRANTED.items()
    }


# --- what the list declares ---------------------------------------------------


def test_the_read_privileges_name_the_cluster_log_and_the_two_the_estate_reads() -> None:
    """``Sys.Syslog`` on ``/`` is required: ``/cluster/log`` is behind it."""
    required = {(privilege.privilege, privilege.path) for privilege in READ_PRIVILEGES}

    assert ("Sys.Audit", "/") in required
    assert ("VM.Audit", "/vms") in required
    assert ("Datastore.Audit", "/storage") in required
    assert ("Sys.Syslog", "/") in required


def test_the_advisory_privileges_name_sdn_audit_and_refuse_nothing() -> None:
    """The role an operator is asked to create carries it; nothing shipped reads it."""
    advisory = {(privilege.privilege, privilege.path) for privilege in ADVISORY_PRIVILEGES}

    assert ("SDN.Audit", "/") in advisory
    assert privilege_report(_without("SDN.Audit")).read_sufficient


def test_every_required_privilege_names_a_capability_this_integration_declares() -> None:
    """The declaration consistency check: a privilege that unlocks nothing named
    is a privilege nobody can decide whether they care about."""
    declared = set(capabilities_of(INTEGRATION))

    assert declared, "the catalogue reports no capabilities for this integration"
    for privilege in READ_PRIVILEGES:
        assert privilege.capabilities, f"{privilege.describe()} names no capability"
        assert set(privilege.capabilities) <= declared, (
            f"{privilege.describe()} names {sorted(set(privilege.capabilities) - declared)}, "
            f"which this integration does not declare"
        )


def test_an_advisory_privilege_names_no_capability_and_says_why() -> None:
    """The one exemption from the check above, asserted rather than assumed.

    An advisory privilege exists precisely because nothing shipped needs it. If
    a capability ever does, it belongs in ``READ_PRIVILEGES`` and this test is
    what makes moving it a decision rather than an oversight.
    """
    for privilege in ADVISORY_PRIVILEGES:
        assert privilege.capabilities == ()
        assert privilege.grants.strip()


def test_every_declared_privilege_says_what_stops_working_without_it() -> None:
    for privilege in (*READ_PRIVILEGES, *ADVISORY_PRIVILEGES, *WRITE_PRIVILEGES):
        assert privilege.grants.strip()
        assert privilege.path.startswith("/")


# --- what a report says -------------------------------------------------------


def test_a_token_that_cannot_read_the_cluster_log_is_named_not_summarised() -> None:
    """Acceptance 1. ``Sys.Syslog`` missing is the case the specification names:
    an investigation that cannot read the log does not find the cause."""
    report = privilege_report(_without("Sys.Syslog"))

    assert not report.read_sufficient
    gaps = {(gap.privilege, gap.path) for gap in report.missing_read}
    assert gaps == {("Sys.Syslog", "/")}

    explanation = report.explain()
    assert "Sys.Syslog on /" in explanation
    assert "cluster log" in explanation
    assert "Datacenter" in explanation


def test_the_record_a_console_renders_carries_every_tier_separately() -> None:
    record = privilege_report(_without("SDN.Audit")).to_record()

    assert record["read_sufficient"] is True
    assert record["advisory_sufficient"] is False
    assert record["write_sufficient"] is False
    assert record["missing_read"] == []
    assert any("SDN.Audit on /" in line for line in record["missing_advisory"])
    assert record["granted_at"]


def test_a_missing_advisory_privilege_is_offered_as_information_not_as_a_failure() -> None:
    explanation = privilege_report(_without("SDN.Audit")).explain()

    assert "SDN.Audit on /" in explanation
    assert "Missing for reading:" not in explanation


# --- through the verifier, which is what a deep verify runs -------------------


async def test_the_verifier_reports_the_gap_by_name_rather_than_failing_generically() -> None:
    """Acceptance 1, end to end through the object the deep-verify route runs.

    Driven with a staged ``/access/permissions`` rather than a hand-built
    report, because the thing that could break is the verifier asking Proxmox
    the wrong question — and a unit test over ``privilege_report`` alone would
    still pass if it did.
    """
    client, _ = client_for(responses={"/access/permissions": _without("Sys.Syslog")})

    described = await ProxmoxVerifier().describe(client)
    record = described.to_record()
    privileges = record["privileges"]

    assert privileges["read_sufficient"] is False
    assert privileges["missing_read"] == [
        "Sys.Syslog on / — without it, nothing can read the cluster log, which is where "
        "corosync says why a link flapped and why a node left"
    ]
    assert "cannot read everything" in str(record["summary"])


async def test_a_sufficient_token_is_described_as_read_only_and_supported() -> None:
    client, _ = client_for()

    described = await ProxmoxVerifier().describe(client)

    assert described.privileges.read_sufficient
    assert described.privileges.advisory_sufficient
    assert not described.privileges.write_sufficient
    assert "read-only" in described.summary()
