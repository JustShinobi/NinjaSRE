"""Contract: a check that passed is still passed after the process that ran it died.

Five things a backend must not get wrong. Checking the same thing twice is one
row and the second one wins; a passed check and a failed one are both recorded,
because "nobody has checked" and "somebody checked and it failed" are different
screens; replacing the credential forgets the verdict, because a verdict about a
key that is no longer there is a green tick on something nobody tested; the page
bound raises rather than clamps; and one tenant's checks are invisible from
another.

The third is the load-bearing one. Everything else here is bookkeeping — that
one is the difference between a checklist an operator can trust and a checklist
that goes green once and stays green through the key rotation that broke it.
"""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import (
    PersistenceGateway,
    TenantScope,
    VerificationLedger,
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
)

pytestmark = pytest.mark.contract


def check(
    *,
    subject: str = "prometheus",
    kind: VerificationSubject = VerificationSubject.INTEGRATION,
    outcome: VerificationOutcome = VerificationOutcome.PASSED,
    minutes: float = 0.0,
    detail: str = "It answered.",
    checked_by: str = "ada",
    model_id: str = "",
) -> VerificationRecord:
    """Return one recorded check, at a fixed instant."""
    return VerificationRecord(
        subject=subject,
        kind=kind,
        outcome=outcome,
        checked_at=at(minutes),
        detail=detail,
        checked_by=checked_by,
        team_node_id="payments",
        model_id=model_id,
    )


# --- Recording ---------------------------------------------------------------------


async def test_a_check_survives_the_transaction_that_recorded_it(
    gateway: PersistenceGateway,
) -> None:
    """The whole point: reload the page and the green tick is still there."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check())

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        ledger: VerificationLedger = uow.verifications
        found = await ledger.latest(kind=VerificationSubject.INTEGRATION, subject="prometheus")

    assert found is not None
    assert found.verified
    assert found.detail == "It answered."
    assert found.checked_by == "ada"
    assert found.checked_at == at(0)


async def test_checking_the_same_thing_twice_keeps_the_second_answer(
    gateway: PersistenceGateway,
) -> None:
    """A check is current state, not history. The one that ran last is the one that counts."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check())
        await uow.verifications.record(
            check(outcome=VerificationOutcome.FAILED, minutes=5, detail="401 from the endpoint.")
        )

        rows = await uow.verifications.records()
        found = await uow.verifications.latest(
            kind=VerificationSubject.INTEGRATION, subject="prometheus"
        )

    assert len(rows) == 1
    assert found is not None
    assert not found.verified
    assert found.detail == "401 from the endpoint."


async def test_a_failed_check_is_recorded_rather_than_dropped(
    gateway: PersistenceGateway,
) -> None:
    """ "Nobody checked" and "somebody checked and it failed" are different next actions."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(
            check(outcome=VerificationOutcome.FAILED, detail="the host did not resolve")
        )
        found = await uow.verifications.latest(
            kind=VerificationSubject.INTEGRATION, subject="prometheus"
        )

    assert found is not None
    assert found.outcome is VerificationOutcome.FAILED
    assert not found.verified


async def test_a_provider_check_records_the_model_it_actually_exercised(
    gateway: PersistenceGateway,
) -> None:
    """Verifying the registry default and verifying the configured model are different claims."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(
            check(
                subject="google_gemini",
                kind=VerificationSubject.MODEL_PROVIDER,
                model_id="gemini-2.5-flash",
            )
        )
        found = await uow.verifications.latest(
            kind=VerificationSubject.MODEL_PROVIDER, subject="google_gemini"
        )

    assert found is not None
    assert found.model_id == "gemini-2.5-flash"


async def test_the_same_name_under_two_kinds_is_two_records(
    gateway: PersistenceGateway,
) -> None:
    """A vendor and a provider can share a name; a shared row would leak one verdict onto both."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check(subject="grafana"))
        await uow.verifications.record(
            check(
                subject="grafana",
                kind=VerificationSubject.MODEL_PROVIDER,
                outcome=VerificationOutcome.FAILED,
            )
        )

        integration = await uow.verifications.latest(
            kind=VerificationSubject.INTEGRATION, subject="grafana"
        )
        provider = await uow.verifications.latest(
            kind=VerificationSubject.MODEL_PROVIDER, subject="grafana"
        )

    assert integration is not None and integration.verified
    assert provider is not None and not provider.verified


# --- Forgetting --------------------------------------------------------------------


async def test_forgetting_a_check_removes_the_verdict(gateway: PersistenceGateway) -> None:
    """A key that was replaced has not been verified. The tick goes with the credential."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check())

        forgotten = await uow.verifications.forget(
            kind=VerificationSubject.INTEGRATION, subject="prometheus"
        )
        found = await uow.verifications.latest(
            kind=VerificationSubject.INTEGRATION, subject="prometheus"
        )

    assert forgotten is True
    assert found is None


async def test_forgetting_something_nobody_checked_says_so(
    gateway: PersistenceGateway,
) -> None:
    """False rather than an error: the caller wanted the row gone and it is gone."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        forgotten = await uow.verifications.forget(
            kind=VerificationSubject.INTEGRATION, subject="never-configured"
        )

    assert forgotten is False


# --- Reading -----------------------------------------------------------------------


async def test_records_come_back_in_a_stable_order(gateway: PersistenceGateway) -> None:
    """Kind then subject, so two backends render one console the same way."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check(subject="proxmox"))
        await uow.verifications.record(check(subject="loki"))
        await uow.verifications.record(
            check(subject="google_gemini", kind=VerificationSubject.MODEL_PROVIDER)
        )

        rows = await uow.verifications.records()

    assert [(row.kind.value, row.subject) for row in rows] == [
        ("integration", "loki"),
        ("integration", "proxmox"),
        ("model-provider", "google_gemini"),
    ]


async def test_reading_one_kind_leaves_the_other_out(gateway: PersistenceGateway) -> None:
    """The checklist asks about integrations; the provider step asks its own question."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check(subject="proxmox"))
        await uow.verifications.record(
            check(subject="google_gemini", kind=VerificationSubject.MODEL_PROVIDER)
        )

        rows = await uow.verifications.records(kind=VerificationSubject.INTEGRATION)

    assert [row.subject for row in rows] == ["proxmox"]


async def test_the_page_bound_raises_rather_than_clamps(gateway: PersistenceGateway) -> None:
    """A caller who asked for a thousand and got five hundred cannot tell that from five hundred."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        with pytest.raises(BoundExceeded):
            await uow.verifications.records(limit=100_000)


# --- Tenancy -----------------------------------------------------------------------


async def test_one_tenants_checks_are_invisible_from_another(
    gateway: PersistenceGateway,
) -> None:
    """The boundary is the organisation, and it does not move for a checklist."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.verifications.record(check())

    async with gateway.begin(TenantScope(org_id="globex")) as uow:
        found = await uow.verifications.latest(
            kind=VerificationSubject.INTEGRATION, subject="prometheus"
        )
        rows = await uow.verifications.records()

    assert found is None
    assert rows == ()


# --- The record itself -------------------------------------------------------------


def test_a_record_needs_something_to_be_about() -> None:
    """A verdict with no subject is a green tick nothing can be joined to."""
    with pytest.raises(ValueError, match="subject"):
        VerificationRecord(
            subject="",
            kind=VerificationSubject.INTEGRATION,
            outcome=VerificationOutcome.PASSED,
            checked_at=at(0),
        )


def test_a_failed_check_must_say_what_failed() -> None:
    """A red mark with no sentence leaves an operator with a colour and no next step."""
    with pytest.raises(ValueError, match="detail"):
        VerificationRecord(
            subject="prometheus",
            kind=VerificationSubject.INTEGRATION,
            outcome=VerificationOutcome.FAILED,
            checked_at=at(0),
            detail="   ",
        )
