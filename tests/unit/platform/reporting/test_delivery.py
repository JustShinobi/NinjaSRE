"""Delivering one report to many destinations, with each one's failure its own."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.notifications import (
    DESTINATION_UNHEALTHY_AFTER_FAILURES,
    DESTINATION_UNHEALTHY_COOLDOWN_SECONDS,
    REPORT_MAX_DELIVERY_ATTEMPTS,
)
from platform.reporting.delivery.dispatcher import (
    DeliveryDispatcher,
    DeliveryLedger,
    DeliveryStatus,
    PermanentDeliveryFailure,
    TransientDeliveryFailure,
    UnknownTeam,
)
from platform.reporting.delivery.health import DestinationHealth
from platform.reporting.delivery.verification import DestinationVerifier
from platform.reporting.models import (
    Destination,
    FormattedReport,
    Report,
    ReportMetadata,
)

NOW = datetime(2026, 3, 1, 3, 14, tzinfo=UTC)


class FrozenClock:
    """A clock the test moves by hand."""

    def __init__(self, at: datetime = NOW) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.at = self.at + timedelta(seconds=seconds)


async def no_sleep(seconds: float) -> None:
    """Absorb a backoff wait so the suite does not sit through one."""


def report() -> Report:
    """Return a small report to deliver."""
    return Report(
        run_id="run-1",
        title="checkout latency",
        summary="Latency rose after a deploy.",
        root_cause="The deploy narrowed the pool.",
        confidence_score=0.8,
        metadata=ReportMetadata(run_id="run-1", run_link="https://ninjasre.invalid/runs/run-1"),
    )


def destination(kind: str = "slack", target: str = "#incidents") -> Destination:
    """Return a verified destination."""
    return Destination(kind=kind, target=target, verified=True)


class RecordingTransport:
    """Takes every delivery and remembers what it was given."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def deliver(
        self, formatted: FormattedReport, target: Destination, *, delivery_key: str
    ) -> str:
        """Accept the delivery and return a reference to it."""
        self.calls.append((target.name, delivery_key, formatted.body))
        return f"ref-{len(self.calls)}"

    @property
    def deliveries(self) -> int:
        """Return how many bodies this transport actually accepted."""
        return len(self.calls)


class FlakyTransport(RecordingTransport):
    """Fails transiently a fixed number of times, then works."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.remaining = failures
        self.attempts = 0

    async def deliver(
        self, formatted: FormattedReport, target: Destination, *, delivery_key: str
    ) -> str:
        """Fail while there are failures left, then accept."""
        self.attempts += 1
        if self.remaining:
            self.remaining -= 1
            raise TransientDeliveryFailure("the vendor answered 503")
        return await super().deliver(formatted, target, delivery_key=delivery_key)


class BrokenTransport:
    """Raises something the dispatcher was never told about."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.attempts = 0

    async def deliver(
        self, formatted: FormattedReport, target: Destination, *, delivery_key: str
    ) -> str:
        """Raise whatever this transport was built with."""
        self.attempts += 1
        raise self.error


def dispatcher(
    transports: dict[str, object],
    *,
    clock: Callable[[], datetime] | None = None,
    health: DestinationHealth | None = None,
    ledger: DeliveryLedger | None = None,
) -> DeliveryDispatcher:
    """Return a dispatcher over ``transports``, keyed by destination kind."""
    tick = clock or FrozenClock()
    return DeliveryDispatcher(
        transports=transports,  # type: ignore[arg-type]
        health=health if health is not None else DestinationHealth(clock=tick),
        ledger=ledger if ledger is not None else DeliveryLedger(),
        clock=tick,
        sleep=no_sleep,
    )


# -- T020/SC-002: per-destination isolation -------------------------------------


async def test_a_report_reaches_every_configured_destination() -> None:
    transports = {"slack": RecordingTransport(), "jira": RecordingTransport()}
    records = await dispatcher(transports).deliver(
        report(), (destination(), destination("jira", "OPS"))
    )

    assert [record.status for record in records] == [
        DeliveryStatus.DELIVERED,
        DeliveryStatus.DELIVERED,
    ]
    assert transports["slack"].deliveries == 1  # type: ignore[union-attr]
    assert transports["jira"].deliveries == 1  # type: ignore[union-attr]


async def test_one_destination_failing_does_not_stop_the_others() -> None:
    working = RecordingTransport()
    transports = {
        "slack": working,
        "jira": BrokenTransport(PermanentDeliveryFailure("project archived")),
        "email": RecordingTransport(),
    }

    records = await dispatcher(transports).deliver(
        report(),
        (destination(), destination("jira", "OPS"), destination("email", "a@example.invalid")),
    )

    by_destination = {record.destination: record for record in records}
    assert by_destination["slack:#incidents"].status is DeliveryStatus.DELIVERED
    assert by_destination["jira:OPS"].status is DeliveryStatus.REFUSED
    assert by_destination["jira:OPS"].reason == "project archived"
    assert by_destination["email:a@example.invalid"].status is DeliveryStatus.DELIVERED


async def test_an_unexpected_exception_from_a_transport_is_isolated_too() -> None:
    transports = {
        "slack": BrokenTransport(RuntimeError("the client library exploded")),
        "email": RecordingTransport(),
    }

    records = await dispatcher(transports).deliver(
        report(), (destination(), destination("email", "a@example.invalid"))
    )

    by_destination = {record.destination: record for record in records}
    assert by_destination["slack:#incidents"].status is DeliveryStatus.FAILED
    assert by_destination["email:a@example.invalid"].status is DeliveryStatus.DELIVERED


async def test_a_destination_with_no_transport_is_recorded_rather_than_raising() -> None:
    records = await dispatcher({"email": RecordingTransport()}).deliver(
        report(), (destination(), destination("email", "a@example.invalid"))
    )

    by_destination = {record.destination: record for record in records}
    assert by_destination["slack:#incidents"].status is DeliveryStatus.SKIPPED
    assert "no transport" in by_destination["slack:#incidents"].reason
    assert by_destination["email:a@example.invalid"].status is DeliveryStatus.DELIVERED


# -- T021/SC-005: retry produces exactly one delivery ---------------------------


async def test_a_transient_failure_is_retried_and_delivers_exactly_once() -> None:
    flaky = FlakyTransport(failures=2)

    records = await dispatcher({"slack": flaky}).deliver(report(), (destination(),))

    assert records[0].status is DeliveryStatus.DELIVERED
    assert records[0].attempts == 3
    assert flaky.attempts == 3
    assert flaky.deliveries == 1


async def test_every_attempt_carries_the_same_idempotency_key() -> None:
    flaky = FlakyTransport(failures=1)

    await dispatcher({"slack": flaky}).deliver(report(), (destination(),))

    assert flaky.calls[0][1] == destination().delivery_key("run-1")


async def test_delivering_the_same_report_again_does_not_produce_a_second_copy() -> None:
    transport = RecordingTransport()
    ledger = DeliveryLedger()
    first = await dispatcher({"slack": transport}, ledger=ledger).deliver(
        report(), (destination(),)
    )
    second = await dispatcher({"slack": transport}, ledger=ledger).deliver(
        report(), (destination(),)
    )

    assert first[0].status is DeliveryStatus.DELIVERED
    assert second[0].status is DeliveryStatus.DUPLICATE
    assert second[0].reference == first[0].reference
    assert transport.deliveries == 1


async def test_retries_stop_at_the_ceiling_and_the_failure_is_recorded() -> None:
    always_failing = FlakyTransport(failures=REPORT_MAX_DELIVERY_ATTEMPTS + 5)

    records = await dispatcher({"slack": always_failing}).deliver(report(), (destination(),))

    assert records[0].status is DeliveryStatus.FAILED
    assert records[0].attempts == REPORT_MAX_DELIVERY_ATTEMPTS
    assert always_failing.attempts == REPORT_MAX_DELIVERY_ATTEMPTS
    assert always_failing.deliveries == 0


async def test_a_permanent_failure_is_not_retried() -> None:
    broken = BrokenTransport(PermanentDeliveryFailure("the channel was deleted"))

    records = await dispatcher({"slack": broken}).deliver(report(), (destination(),))

    assert records[0].status is DeliveryStatus.REFUSED
    assert broken.attempts == 1


# -- T025: a delivery whose team was deleted -----------------------------------


async def test_a_delivery_for_a_deleted_team_is_recorded_and_not_retried() -> None:
    gone = BrokenTransport(UnknownTeam("team-payments"))

    records = await dispatcher({"slack": gone}).deliver(report(), (destination(),))

    assert records[0].status is DeliveryStatus.REFUSED
    assert "team-payments" in records[0].reason
    assert gone.attempts == 1


# -- T022/FR-011: health -------------------------------------------------------


async def test_a_destination_that_keeps_failing_is_marked_unhealthy() -> None:
    clock = FrozenClock()
    health = DestinationHealth(clock=clock)
    transports = {"slack": BrokenTransport(PermanentDeliveryFailure("gone"))}

    for _ in range(DESTINATION_UNHEALTHY_AFTER_FAILURES):
        await dispatcher(transports, clock=clock, health=health).deliver(report(), (destination(),))

    assert not health.is_available("slack:#incidents")
    assert [entry.destination for entry in health.unhealthy()] == ["slack:#incidents"]
    assert health.report()["unhealthy"] == ["slack:#incidents"]


async def test_an_unhealthy_destination_is_skipped_rather_than_hammered() -> None:
    clock = FrozenClock()
    health = DestinationHealth(clock=clock)
    broken = BrokenTransport(PermanentDeliveryFailure("gone"))
    for _ in range(DESTINATION_UNHEALTHY_AFTER_FAILURES):
        await dispatcher({"slack": broken}, clock=clock, health=health).deliver(
            report(), (destination(),)
        )
    attempts_before = broken.attempts

    records = await dispatcher({"slack": broken}, clock=clock, health=health).deliver(
        report(), (destination(),)
    )

    assert records[0].status is DeliveryStatus.SKIPPED
    assert "unhealthy" in records[0].reason
    assert broken.attempts == attempts_before


async def test_an_unhealthy_destination_is_tried_again_after_the_cooldown() -> None:
    clock = FrozenClock()
    health = DestinationHealth(clock=clock)
    flaky = FlakyTransport(
        failures=DESTINATION_UNHEALTHY_AFTER_FAILURES * REPORT_MAX_DELIVERY_ATTEMPTS
    )
    for _ in range(DESTINATION_UNHEALTHY_AFTER_FAILURES):
        await dispatcher({"slack": flaky}, clock=clock, health=health).deliver(
            report(), (destination(),)
        )
    assert not health.is_available("slack:#incidents")

    clock.advance(DESTINATION_UNHEALTHY_COOLDOWN_SECONDS + 1)

    records = await dispatcher({"slack": flaky}, clock=clock, health=health).deliver(
        report(), (destination(),)
    )

    assert records[0].status is DeliveryStatus.DELIVERED
    assert health.is_available("slack:#incidents")


async def test_a_success_clears_the_failure_streak() -> None:
    clock = FrozenClock()
    health = DestinationHealth(clock=clock)
    health.record_failure("slack:#incidents", reason="503")
    health.record_failure("slack:#incidents", reason="503")

    health.record_success("slack:#incidents")

    assert health.is_available("slack:#incidents")
    assert health.unhealthy() == ()


# -- T023/FR-022: verification --------------------------------------------------


class WorkingProbe:
    """A destination that answers when asked."""

    async def check(self, target: Destination) -> None:
        """Return without raising."""


class RefusingProbe:
    """A destination that names its own failure."""

    async def check(self, target: Destination) -> None:
        """Refuse with a specific reason."""
        raise PermanentDeliveryFailure("the API token is not valid for this workspace")


async def test_a_working_destination_verifies() -> None:
    verifier = DestinationVerifier(probes={"slack": WorkingProbe()}, clock=FrozenClock())

    result = await verifier.verify(destination())

    assert result.ok
    assert result.destination == "slack:#incidents"
    assert result.checked_at == NOW


async def test_a_failing_destination_reports_the_specific_failure() -> None:
    verifier = DestinationVerifier(probes={"slack": RefusingProbe()}, clock=FrozenClock())

    result = await verifier.verify(destination())

    assert not result.ok
    assert result.reason == "the API token is not valid for this workspace"


async def test_a_destination_with_no_probe_is_reported_rather_than_assumed_working() -> None:
    verifier = DestinationVerifier(probes={}, clock=FrozenClock())

    result = await verifier.verify(destination())

    assert not result.ok
    assert "no verifier" in result.reason


async def test_verifying_several_destinations_reports_each_one() -> None:
    verifier = DestinationVerifier(
        probes={"slack": WorkingProbe(), "jira": RefusingProbe()}, clock=FrozenClock()
    )

    results = await verifier.verify_all((destination(), destination("jira", "OPS")))

    assert [result.ok for result in results] == [True, False]


async def test_a_never_verified_destination_is_not_delivered_to() -> None:
    transport = RecordingTransport()

    records = await dispatcher({"slack": transport}).deliver(
        report(), (Destination(kind="slack", target="#incidents"),)
    )

    assert records[0].status is DeliveryStatus.SKIPPED
    assert "verified" in records[0].reason
    assert transport.deliveries == 0


# -- T024/FR-012: the trace ------------------------------------------------------


class CollectingTrace:
    """Keeps the delivery records the dispatcher hands over."""

    def __init__(self) -> None:
        self.records: list[object] = []

    async def record_delivery(self, record: object) -> None:
        """Keep ``record``."""
        self.records.append(record)


async def test_every_delivery_outcome_reaches_the_trace() -> None:
    trace = CollectingTrace()
    dispatch = dispatcher({"slack": RecordingTransport()})
    dispatch.trace = trace

    await dispatch.deliver(report(), (destination(), destination("jira", "OPS")))

    assert [record.status for record in trace.records] == [  # type: ignore[attr-defined]
        DeliveryStatus.DELIVERED,
        DeliveryStatus.SKIPPED,
    ]


async def test_a_trace_that_fails_does_not_lose_the_delivery() -> None:
    class BrokenTrace:
        async def record_delivery(self, record: object) -> None:
            raise RuntimeError("the store is down")

    transport = RecordingTransport()
    dispatch = dispatcher({"slack": transport})
    dispatch.trace = BrokenTrace()

    records = await dispatch.deliver(report(), (destination(),))

    assert records[0].status is DeliveryStatus.DELIVERED
    assert transport.deliveries == 1


def test_a_delivery_record_renders_the_payload_a_trace_stores() -> None:
    from platform.reporting.delivery.dispatcher import DeliveryRecord

    payload = DeliveryRecord(
        destination="slack:#incidents",
        run_id="run-1",
        delivery_key="run-1/slack:#incidents",
        status=DeliveryStatus.DELIVERED,
        attempts=2,
        reference="ref-1",
        summarised=True,
    ).to_payload()

    assert payload["destination"] == "slack:#incidents"
    assert payload["status"] == "delivered"
    assert payload["attempts"] == 2
    assert payload["reference"] == "ref-1"
    assert payload["summarised"] is True


# -- backoff --------------------------------------------------------------------


async def test_the_wait_between_attempts_grows_and_is_capped() -> None:
    waits: list[float] = []

    async def record_sleep(seconds: float) -> None:
        waits.append(seconds)

    dispatch = DeliveryDispatcher(
        transports={"slack": FlakyTransport(failures=REPORT_MAX_DELIVERY_ATTEMPTS + 5)},
        health=DestinationHealth(clock=FrozenClock()),
        ledger=DeliveryLedger(),
        clock=FrozenClock(),
        sleep=record_sleep,
    )

    await dispatch.deliver(report(), (destination(),))

    assert waits == sorted(waits)
    assert len(waits) == REPORT_MAX_DELIVERY_ATTEMPTS - 1


@pytest.mark.parametrize("kind", ["local_markdown", "notion", "pagerduty"])
async def test_the_dispatcher_renders_through_the_registry_for_every_class(kind: str) -> None:
    transport = RecordingTransport()

    await dispatcher({kind: transport}).deliver(
        report(), (Destination(kind=kind, target="somewhere", verified=True),)
    )

    assert "The deploy narrowed the pool." in transport.calls[0][2]
