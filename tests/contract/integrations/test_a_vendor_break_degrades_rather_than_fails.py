"""SC-006 and FR-016. A vendor shipped a breaking change. Now what?

There are only two answers and one of them is wrong.

**Failing the build** is wrong. It is not the operator's change, they cannot fix
it, and a red build across the whole catalogue tells them nothing about
which vendor broke. The pressure that produces is to disable the scheduled live
run — and then the drift is undetected rather than merely unfixed, which is
strictly worse than where they started.

**Marking the integration degraded** is right. Everything else keeps working,
the catalogue says exactly which vendor broke and how, and the investigation
that would have called it knows in advance instead of discovering it mid-incident.

So this suite runs the whole loop rather than asserting the ledger's API. A real
capability, a real client, the real proxy, and a vendor answering the way a
broken one does; the failure is recorded; and the catalogue that the console and
the documentation generator read reports one integration degraded and the rest
untouched.
"""

from __future__ import annotations

import pytest

from integrations._base.access import IntegrationAccess, bind, restore
from integrations._catalogue.discovery import catalogue
from integrations._catalogue.entry import HealthStatus
from integrations._catalogue.health import HealthLedger
from platform.credentials.proxy.model import OutboundResponse
from tests.contract.integrations.conftest import (
    CATALOGUE,
    CONTEXT,
    ORG_ID,
    TEAM_ID,
    integration_ids,
    stand_up,
)

pytestmark = pytest.mark.contract

IDS = integration_ids()
DESCRIPTORS = [entry.descriptor for entry in CATALOGUE]

#: What a vendor's breaking change looks like from here: the call is permitted
#: and the request is now the wrong shape. Not a 500 — that is an outage, which
#: is transient and retried — and not a 403, which is a permission the operator
#: can actually fix.
BROKEN_REQUEST = OutboundResponse(422, {}, b'{"errors":["unknown field: filter.query"]}')


async def run_live(name: str, *, broken: bool) -> tuple[bool, str]:
    """Run one integration's cheapest live call and return whether it worked."""
    from integrations._base.errors import IntegrationError

    transport, vendor = await stand_up(DESCRIPTORS, seeded=(name,))
    if broken:
        vendor.responses.append(BROKEN_REQUEST)

    previous = bind(IntegrationAccess(transport=transport, org_id=ORG_ID, team_id=TEAM_ID))
    try:
        client = next(entry for entry in CATALOGUE if entry.name == name).descriptor.client_class(
            transport=transport, context=CONTEXT
        )
        try:
            await client.ping()
        except IntegrationError as error:
            return False, str(error)
        return True, ""
    finally:
        restore(previous)


async def test_a_vendor_api_break_marks_that_integration_degraded_and_says_what_broke() -> None:
    ledger = HealthLedger()
    broken = IDS[0]

    for name in IDS:
        worked, detail = await run_live(name, broken=name == broken)
        if worked:
            ledger.record_success(name)
        else:
            ledger.record_failure(name, detail=detail)

    degraded = ledger.degraded()
    assert [record.integration for record in degraded] == [broken]
    assert "422" in degraded[0].detail, "a degraded mark with no detail leaves no next step"


async def test_the_break_surfaces_in_the_catalogue_the_console_reads() -> None:
    """FR-016's second half. Recording it is not the same as surfacing it."""
    ledger = HealthLedger()
    broken = IDS[0]
    _, detail = await run_live(broken, broken=True)
    ledger.record_failure(broken, detail=detail)
    for name in IDS[1:]:
        ledger.record_success(name)

    entries = {entry.name: entry for entry in catalogue(health=ledger)}

    assert entries[broken].health is HealthStatus.DEGRADED
    assert entries[broken].to_record()["health_detail"]
    assert not entries[broken].usable
    for name in IDS[1:]:
        assert entries[name].health is HealthStatus.HEALTHY
        assert entries[name].usable


async def test_everything_the_break_did_not_touch_keeps_working() -> None:
    """The whole reason for degrading rather than failing."""
    ledger = HealthLedger()
    ledger.record_failure(IDS[0], detail="the vendor changed the response shape")

    for name in IDS[1:]:
        worked, _ = await run_live(name, broken=False)
        assert worked, f"{name} should be unaffected by another vendor's change"
        ledger.record_success(name)

    assert len(ledger.degraded()) == 1


def test_an_integration_no_live_run_has_touched_is_unknown_rather_than_healthy() -> None:
    """Claiming health for something never checked is the same failure as
    reporting a truncated answer as a complete one."""
    entries = catalogue(health=HealthLedger())

    assert all(entry.health is HealthStatus.UNKNOWN for entry in entries)


def test_the_catalogue_still_builds_with_an_integration_degraded() -> None:
    """A degraded vendor must not stop the deployment from starting."""
    ledger = HealthLedger()
    ledger.record_failure(IDS[0], detail="a vendor API break")

    entries = catalogue(health=ledger)

    assert len(entries) == len(IDS)
    assert all(not entry.parity.missing for entry in entries)
