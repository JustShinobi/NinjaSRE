"""Writing down what a check found, and reading it back on the screens that ask.

Four routes write here and three read, and the reason this is a module rather
than seven inline blocks is that the writes and the reads have to agree about
one thing: an entry that is absent means nobody has checked, and it must never
be rendered as a failure. Spread over seven call sites, that agreement lasts
until somebody adds an eighth.

The read helpers hand back a ``HealthLedger`` — the shape the integration
catalogue already takes — rather than a list of names. That is deliberate: the
catalogue's health field, the checklist's readiness field, and the console's
"what is set up so far" panel are then three renderings of one record instead of
three sources that can disagree about the same vendor.
"""

from __future__ import annotations

from datetime import UTC, datetime

from integrations._catalogue.health import HealthLedger
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.verification_ledger import (
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
)

logger = get_logger(__name__)


async def record_check(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    kind: VerificationSubject,
    subject: str,
    passed: bool,
    detail: str,
    checked_by: str = "",
    team_node_id: str = "",
    model_id: str = "",
) -> None:
    """Write down what a check of ``subject`` found.

    Swallows its own failure, and this is the one place in the feature where
    that is right: the check itself already happened and its answer is already
    on the way to the caller. A store that could not be written is worth a log
    line and is not worth turning a successful verification into a 500 — the
    operator would retry, the same call would go out to the same vendor, and
    they would be charged twice for one answer.

    ``detail`` is required for a failure by the record itself, so a caller that
    has nothing to say about one gets a sentence here rather than an exception
    escaping into a route that had already succeeded.
    """
    said = detail.strip() or (
        "it answered"
        if passed
        else "the check did not pass, and nothing said why — look at the deployment's logs"
    )
    try:
        async with gateway.begin(scope) as uow:
            await uow.verifications.record(
                VerificationRecord(
                    subject=subject,
                    kind=kind,
                    outcome=(VerificationOutcome.PASSED if passed else VerificationOutcome.FAILED),
                    checked_at=datetime.now(UTC),
                    detail=said,
                    checked_by=checked_by,
                    team_node_id=team_node_id,
                    model_id=model_id,
                )
            )
    except Exception:  # noqa: BLE001 — a check that ran is not undone by a store that did not
        logger.warning(
            "verification.not_recorded",
            extra={"subject": subject, "kind": kind.value},
            exc_info=True,
        )


async def forget_check(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    kind: VerificationSubject,
    subject: str,
) -> None:
    """Drop what was recorded about ``subject``, because its credential changed.

    A verdict is about the key it was reached with. Keeping it across a rotation
    would leave a green tick on a credential nothing has tested, which is worse
    than never having checked: it is a wrong answer wearing the authority of a
    measurement.
    """
    try:
        async with gateway.begin(scope) as uow:
            await uow.verifications.forget(kind=kind, subject=subject)
    except Exception:  # noqa: BLE001 — the credential write is the thing that must not fail
        logger.warning(
            "verification.not_forgotten",
            extra={"subject": subject, "kind": kind.value},
            exc_info=True,
        )


async def recorded_checks(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    kind: VerificationSubject,
) -> dict[str, VerificationRecord]:
    """Return what has been checked of one kind, by subject.

    Empty for a deployment that has checked nothing, and empty is also what a
    store that could not be read returns: a checklist that refused to render
    because a side table was unavailable would take away the screen an operator
    reaches for when things are unavailable.
    """
    try:
        async with gateway.begin(scope) as uow:
            rows = await uow.verifications.records(kind=kind)
    except Exception:  # noqa: BLE001 — an unreadable ledger is "nobody has checked"
        logger.warning("verification.not_read", extra={"kind": kind.value}, exc_info=True)
        return {}
    return {row.subject: row for row in rows}


async def recorded_checks_by_kind(
    gateway: PersistenceGateway, scope: TenantScope
) -> dict[VerificationSubject, dict[str, VerificationRecord]]:
    """Return what has been checked, of every kind, in one read of the ledger.

    For the screen that wants two kinds at once — the checklist reads the
    provider's verdict and the integrations' — so it opens one transaction
    rather than one per kind. Absent kinds are empty, as ``recorded_checks``
    would answer for them.
    """
    try:
        async with gateway.begin(scope) as uow:
            rows = await uow.verifications.records()
    except Exception:  # noqa: BLE001 — an unreadable ledger is "nobody has checked"
        logger.warning("verification.not_read", extra={"kind": "all"}, exc_info=True)
        return {kind: {} for kind in VerificationSubject}
    held: dict[VerificationSubject, dict[str, VerificationRecord]] = {
        kind: {} for kind in VerificationSubject
    }
    for row in rows:
        held[row.kind][row.subject] = row
    return held


async def integration_health(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    held: dict[str, VerificationRecord] | None = None,
) -> HealthLedger | None:
    """Return the catalogue's health ledger, populated from what has been checked.

    ``None`` when nothing has been checked, because that is what ``catalogue``
    reads as "every entry is ``unknown``" — and an empty ledger and a missing one
    would otherwise be two ways of saying the same thing with one of them
    requiring an argument to be built.

    ``held`` lets a caller that already read the ledger for another reason —
    the checklist route reads it again for the provider's own record — hand
    the integration rows over rather than paying for the same read twice.
    Read fresh when omitted, which is every caller but that one.
    """
    if held is None:
        held = await recorded_checks(gateway, scope, kind=VerificationSubject.INTEGRATION)
    if not held:
        return None

    # The ledger stamps each observation from its clock, so the clock is moved to
    # the instant each check actually ran. Rebuilding the record with "now" would
    # tell an operator that a check from Tuesday happened when they opened the
    # page, which is the one thing a timestamp is read for.
    stamp = datetime.now(UTC)
    ledger = HealthLedger(clock=lambda: stamp)
    for subject, record in held.items():
        stamp = record.checked_at
        if record.verified:
            ledger.record_success(subject)
        else:
            ledger.record_failure(subject, detail=record.detail)
    return ledger


__all__ = [
    "forget_check",
    "integration_health",
    "record_check",
    "recorded_checks",
    "recorded_checks_by_kind",
]
