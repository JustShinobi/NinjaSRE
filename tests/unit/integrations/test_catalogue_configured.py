"""Whether a credential is stored is a different question from whether a live
check has ever run against it, and the catalogue's ``health`` field used to
answer only the second one.

An integration nobody has connected and an integration that is connected but
has never been checked both read ``unknown`` before this file's own fix,
which is exactly the "todas dizem UNKNOWN" defect an operator with three real
integrations among eighty-five sees: nothing on the card says which three.
``configured`` is the missing half, threaded through from the same vault
listing ``gateway/http/configured.py`` already uses for the estate's own
catalogue read.
"""

from __future__ import annotations

import pytest

from integrations._catalogue.discovery import catalogue, entry, vendor_packages
from integrations._catalogue.entry import HealthStatus
from integrations._catalogue.health import HealthLedger

pytestmark = pytest.mark.unit


def test_an_integration_with_no_credential_is_unconfigured() -> None:
    name = vendor_packages()[0]

    entries = {entry.name: entry for entry in catalogue(configured=frozenset())}

    assert entries[name].health is HealthStatus.UNCONFIGURED


def test_unconfigured_carries_a_detail_an_operator_can_read_without_expanding_anything() -> None:
    name = vendor_packages()[0]

    entries = {entry.name: entry for entry in catalogue(configured=frozenset())}

    assert entries[name].health_detail.strip() != ""


def test_a_configured_integration_the_ledger_has_not_run_reads_unknown_not_unconfigured() -> None:
    name = vendor_packages()[0]

    entries = {entry.name: entry for entry in catalogue(configured=frozenset({name}))}

    assert entries[name].health is HealthStatus.UNKNOWN


def test_a_configured_integration_the_ledger_marks_healthy_stays_healthy() -> None:
    name = vendor_packages()[0]
    ledger = HealthLedger()
    ledger.record_success(name)

    entries = {
        entry.name: entry for entry in catalogue(health=ledger, configured=frozenset({name}))
    }

    assert entries[name].health is HealthStatus.HEALTHY


def test_a_configured_integration_the_ledger_marks_degraded_stays_degraded_even_though_it_is_configured() -> (
    None
):
    """Being connected does not excuse a failing live check — the two facts
    are independent and both have to survive the join."""
    name = vendor_packages()[0]
    ledger = HealthLedger()
    ledger.record_failure(name, detail="the vendor answered 500")

    entries = {
        entry.name: entry for entry in catalogue(health=ledger, configured=frozenset({name}))
    }

    assert entries[name].health is HealthStatus.DEGRADED


def test_leaving_configured_unset_keeps_every_existing_caller_seeing_what_it_always_saw() -> None:
    """Every caller that predates this parameter never passes it, and none of
    them may start seeing ``unconfigured`` because of a default that changed
    out from under them."""
    name = vendor_packages()[0]

    entries = {found.name: found for found in catalogue()}

    assert entries[name].health is HealthStatus.UNKNOWN


def test_the_single_entry_lookup_carries_the_same_parameter_through() -> None:
    """``entry`` is a thin wrapper over ``catalogue`` and must not drop it."""
    name = vendor_packages()[0]

    assert entry(name, configured=frozenset()).health is HealthStatus.UNCONFIGURED
    assert entry(name, configured=frozenset({name})).health is HealthStatus.UNKNOWN
