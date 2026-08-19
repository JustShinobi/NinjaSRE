"""``GET /v1/integrations`` says whether a credential is stored, not only
whether it has ever been verified — the fact the catalogue's slide-over needs
in order to tell "nothing is connected here" apart from "something is
connected and simply has not been checked yet".

The behaviour is already proven end to end, with real HTTP calls, in
``tests/unit/gateway/http/test_integrations_credential_state.py``. What this
file adds is the contract two other tiers rely on: that the distinction
survives into the catalogue the mock plane actually serves, for the two named
vendors this feature depends on, and that every value either one carries is a
spelling the real health enum actually declares rather than one that merely
agrees with itself.
"""

from __future__ import annotations

from collections.abc import Iterable

from integrations._catalogue.discovery import catalogue
from integrations._catalogue.entry import CatalogueEntry, HealthStatus
from integrations._catalogue.health import HealthLedger
from tools.mockplane import scenarios

#: A real, installed vendor package this deployment does not otherwise depend
#: on for anything measured elsewhere in this feature — see the note in this
#: feature's own control log about why ``prometheus`` is left untouched by the
#: fixtures.
_NAME = "prometheus"


def _health_of(entries: Iterable[CatalogueEntry], name: str) -> str:
    return next(entry.health.value for entry in entries if entry.name == name)


def test_an_absent_credential_and_a_stored_unverified_one_are_different_payload_values() -> None:
    """The same vendor, three states, three different strings — not an absence.

    A caller reading ``health`` alone can tell all three apart: the payload
    states the distinction outright rather than requiring the console to infer
    "stored, never checked" from some other field being missing.
    """
    absent = catalogue(configured=frozenset())
    stored_unverified = catalogue(health=HealthLedger(), configured=frozenset({_NAME}))
    verified_ledger = HealthLedger()
    verified_ledger.record_success(_NAME)
    verified = catalogue(health=verified_ledger, configured=frozenset({_NAME}))

    values = {
        _health_of(absent, _NAME),
        _health_of(stored_unverified, _NAME),
        _health_of(verified, _NAME),
    }

    assert values == {
        HealthStatus.UNCONFIGURED.value,
        HealthStatus.UNKNOWN.value,
        HealthStatus.HEALTHY.value,
    }, f"three different credential states collapsed onto fewer than three payload values: {values}"


def test_a_stored_unverified_credential_is_never_the_same_value_as_an_absent_one() -> None:
    """FR-034/FR-042's precondition, isolated: ``unknown`` is not ``unconfigured``.

    A console that only checked ``health !== 'unconfigured'`` to mean
    "connected" would already work today, but only because this holds — if a
    future change ever let a stored-but-unverified credential fall back to
    ``unconfigured``, the panel this feature builds would render an empty
    credential field beside a disabled button for an integration that is
    actually connected.
    """
    stored_unverified = catalogue(health=HealthLedger(), configured=frozenset({_NAME}))
    assert _health_of(stored_unverified, _NAME) != HealthStatus.UNCONFIGURED.value


def test_the_served_catalogue_carries_a_verified_integration_and_a_stored_but_unverified_one() -> (
    None
):
    """The mock plane the console actually runs against states the same fact.

    ``alertmanager`` and ``loki`` are this feature's own fixtures for
    "verified" and "stored, never verified" respectively. Both are checked
    against the real ``HealthStatus`` enum rather than against each other, so a
    fixture that agreed with itself and disagreed with the backend would be
    caught here rather than only read as a comment.
    """
    allowed = {member.value for member in HealthStatus}
    record = next(
        record
        for record in scenarios.load("populated").all_records()
        if record.slug == "integrations"
    )
    entries = {entry["name"]: entry for entry in record.body["integrations"]}

    assert entries["alertmanager"]["health"] in allowed
    assert entries["loki"]["health"] in allowed
    assert entries["alertmanager"]["health"] == HealthStatus.HEALTHY.value
    assert entries["loki"]["health"] == HealthStatus.UNKNOWN.value
    assert entries["alertmanager"]["health"] != entries["loki"]["health"]
