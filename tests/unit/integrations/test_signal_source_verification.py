"""Verifying an observability source by investigating it, not by pinging it.

A credential check that reports "reachable" about a Prometheus holding nothing
has answered a question nobody asked. Three failures look identical from a
status code and are fixed in three different places:

**The store is empty for the window that matters.** 200, a well-formed body, an
empty result set. Every scrape target is down, or the retention was cut, or the
query is pointed at a tenant with no data — and an investigation that reaches
this source during an incident concludes that nothing happened.

**The store's clock disagrees with the platform's.** Correlating "the alert
fired at 03:14" against a source thirty seconds ahead puts cause after effect.
The Proxmox integration already measures this between cluster members for the
same reason; a signal source is the same failure with a wider blast radius.

**An empty answer is the correct answer.** An alert router holding no alerts is
an alert router doing its job, and reporting that as a broken source would train
an operator to ignore the check. So a probe declares what an empty window
*means* for its vendor, and the report distinguishes the two.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.signals import (
    SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
    VERIFY_WINDOW_MINUTES,
)
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._verification.diagnostics import (
    ClockSkewProbe,
    DataWindow,
    DataWindowProbe,
    EmptyWindow,
    SkewState,
    WindowState,
    http_date,
)
from integrations._verification.framework import (
    Connectivity,
    VerificationRunner,
)
from integrations._verification.permissions import PermissionProbe, RequiredPermission
from integrations._verification.reporting import report_message

#: The instant every test in this module measures against. Pinned: a probe that
#: read the wall clock would make the skew assertions depend on how long the
#: suite took to get here, and a suite whose two runs disagree is a failing one.
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

READ_SERIES = RequiredPermission(
    name="query",
    grants="evaluate a query over the stored series",
    capabilities=("acme_metric_statistics",),
    where="the reverse proxy in front of it",
)


def returning(rows: int):
    """Return a window read that answers with ``rows`` series."""

    async def read(transport: object, context: object, window: DataWindow) -> int:
        assert window.minutes == VERIFY_WINDOW_MINUTES
        return rows

    return read


def refusing(reason: IntegrationErrorReason):
    """Return a window read the vendor turned down."""

    async def read(transport: object, context: object, window: DataWindow) -> int:
        raise IntegrationError("refused", integration="acme", reason=reason)

    return read


def reporting(when: datetime | None):
    """Return a clock read that says the source believes it is ``when``."""

    async def read(transport: object, context: object) -> datetime | None:
        return when

    return read


def window_probe(
    read,
    *,
    empty_means: EmptyWindow = EmptyWindow.BROKEN,
) -> DataWindowProbe:
    return DataWindowProbe(
        description="evaluates up{} over the last window, the cheapest read that returns series",
        read=read,
        empty_means=empty_means,
        advice="Acme answered and holds nothing for this window; check its scrape targets.",
    )


def clock_probe(read) -> ClockSkewProbe:
    return ClockSkewProbe(
        description="reads the Date header Acme returns on its status endpoint",
        read=read,
    )


class Source:
    """A verifier double for a vendor that is also a signal source."""

    def __init__(
        self,
        *,
        integration: str = "acme",
        connectivity: Connectivity | None = None,
        probes: tuple[PermissionProbe, ...] = (),
        window: DataWindowProbe | None = None,
        clock: ClockSkewProbe | None = None,
    ) -> None:
        self._integration = integration
        self._connectivity = connectivity or Connectivity(reachable=True, status_code=200)
        self._probes = probes
        self._window = window
        self._clock = clock

    @property
    def integration(self) -> str:
        return self._integration

    @property
    def probe_description(self) -> str:
        return "reads one series, the cheapest call Acme offers"

    def probes(self) -> tuple[PermissionProbe, ...]:
        return self._probes

    async def connect(self, transport: object, context: object) -> Connectivity:
        return self._connectivity

    def data_window_probe(self) -> DataWindowProbe | None:
        return self._window

    def clock_probe(self) -> ClockSkewProbe | None:
        return self._clock


async def run(source: Source):
    """Run ``source`` through the framework against the pinned clock."""
    runner = VerificationRunner([source], clock=lambda: NOW)
    return await runner.verify(source.integration, transport=object(), context=object())


# --- the window ---------------------------------------------------------------


class TestAWindowThatReturnedData:
    async def test_a_source_holding_series_verifies_with_the_count(self) -> None:
        report = await run(Source(window=window_probe(returning(12))))

        assert report.data_window is not None
        assert report.data_window.state is WindowState.RETURNED
        assert report.data_window.rows == 12
        assert report.data_window.usable
        assert report.ok
        assert not report.degraded

    async def test_the_window_is_the_named_constant_and_ends_at_the_platforms_now(self) -> None:
        report = await run(Source(window=window_probe(returning(1))))

        assert report.data_window is not None
        assert report.data_window.window_minutes == VERIFY_WINDOW_MINUTES
        assert report.data_window.window == DataWindow(
            start=NOW - timedelta(minutes=VERIFY_WINDOW_MINUTES), end=NOW
        )

    async def test_the_report_says_what_was_asked_and_what_came_back(self) -> None:
        report = await run(Source(window=window_probe(returning(12))))

        printed = report_message(report)
        assert "evaluates up{} over the last window" in printed
        assert "12" in printed


class TestAnEmptyWindowThatMeansTheSourceIsBroken:
    """The failure this whole probe family exists for: 200 with nothing in it."""

    async def test_an_empty_window_is_its_own_state_not_a_denial(self) -> None:
        report = await run(Source(window=window_probe(returning(0))))

        assert report.data_window is not None
        assert report.data_window.state is WindowState.EMPTY_WINDOW
        assert report.data_window.state is not WindowState.DENIED

    async def test_an_empty_window_fails_the_report_rather_than_passing_as_healthy(self) -> None:
        report = await run(Source(window=window_probe(returning(0))))

        assert not report.data_window.usable  # type: ignore[union-attr]
        assert not report.ok
        assert report.degraded
        assert any("holds nothing" in reason for reason in report.degradations)

    async def test_the_advice_names_what_to_check_rather_than_that_it_failed(self) -> None:
        report = await run(Source(window=window_probe(returning(0))))

        printed = report_message(report)
        assert "check its scrape targets" in printed
        assert f"{VERIFY_WINDOW_MINUTES}" in printed


class TestAnEmptyWindowThatIsTheCorrectAnswer:
    """An alert router holding no alerts is an alert router working."""

    async def test_an_expected_empty_window_is_recorded_and_does_not_fail_the_report(self) -> None:
        report = await run(
            Source(window=window_probe(returning(0), empty_means=EmptyWindow.EXPECTED))
        )

        assert report.data_window is not None
        assert report.data_window.state is WindowState.EMPTY_WINDOW
        assert report.data_window.rows == 0
        assert report.data_window.usable
        assert report.ok
        assert not report.degraded

    async def test_the_report_says_why_empty_is_not_a_finding_here(self) -> None:
        report = await run(
            Source(window=window_probe(returning(0), empty_means=EmptyWindow.EXPECTED))
        )

        printed = report_message(report)
        assert "empty answer is a real answer" in printed


class TestAWindowTheVendorWouldNotServe:
    async def test_a_denied_read_keeps_its_own_state(self) -> None:
        report = await run(Source(window=window_probe(refusing(IntegrationErrorReason.FORBIDDEN))))

        assert report.data_window is not None
        assert report.data_window.state is WindowState.DENIED
        assert not report.ok

    async def test_an_unreachable_source_never_runs_the_window_read(self) -> None:
        """The credential was rejected, so nothing was learned about the data."""
        report = await run(
            Source(
                connectivity=Connectivity(reachable=False, detail="401", status_code=401),
                window=window_probe(returning(99)),
            )
        )

        assert report.data_window is not None
        assert report.data_window.state is WindowState.UNCHECKED
        assert report.data_window.rows == 0

    async def test_a_read_that_failed_for_an_unrelated_reason_is_inconclusive(self) -> None:
        report = await run(
            Source(window=window_probe(refusing(IntegrationErrorReason.PROXY_UNAVAILABLE)))
        )

        assert report.data_window is not None
        assert report.data_window.state is WindowState.INCONCLUSIVE
        assert not report.degraded, "nothing was established, so nothing is degraded"


class TestAProbeThatWillNotSayWhatItReads:
    def test_a_window_probe_with_no_description_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="what it read"):
            DataWindowProbe(description="  ", read=returning(1), advice="check the targets")

    def test_a_window_probe_with_no_advice_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="advice"):
            DataWindowProbe(description="reads one series", read=returning(1), advice=" ")


# --- the clock ----------------------------------------------------------------


class TestAClockInsideTheTolerance:
    async def test_a_source_that_agrees_verifies_with_the_measured_offset(self) -> None:
        report = await run(Source(clock=clock_probe(reporting(NOW + timedelta(seconds=2)))))

        assert report.clock is not None
        assert report.clock.state is SkewState.IN_TOLERANCE
        assert report.clock.offset_seconds == pytest.approx(2.0)
        assert report.clock.tolerance_seconds == SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS
        assert not report.degraded

    async def test_a_source_behind_the_platform_measures_a_negative_offset(self) -> None:
        report = await run(Source(clock=clock_probe(reporting(NOW - timedelta(seconds=3)))))

        assert report.clock is not None
        assert report.clock.offset_seconds == pytest.approx(-3.0)
        assert report.clock.state is SkewState.IN_TOLERANCE


class TestAClockOutsideTheTolerance:
    async def test_a_skewed_source_is_degraded_rather_than_unusable(self) -> None:
        drift = SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS + 10
        report = await run(Source(clock=clock_probe(reporting(NOW + timedelta(seconds=drift)))))

        assert report.clock is not None
        assert report.clock.state is SkewState.OUT_OF_TOLERANCE
        assert report.degraded
        assert report.ok, "the source answers; what it says about time is what cannot be trusted"

    async def test_the_report_names_the_measured_offset_and_the_tolerance(self) -> None:
        drift = SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS + 10
        report = await run(Source(clock=clock_probe(reporting(NOW + timedelta(seconds=drift)))))

        printed = report_message(report)
        assert f"{drift:.1f}s" in printed
        assert f"{SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS:.1f}s" in printed
        assert any(f"{drift:.1f}s" in reason for reason in report.degradations)


class TestASourceThatReportsNoTime:
    async def test_a_source_with_no_clock_is_inconclusive_and_says_so(self) -> None:
        report = await run(Source(clock=clock_probe(reporting(None))))

        assert report.clock is not None
        assert report.clock.state is SkewState.UNREPORTED
        assert report.clock.offset_seconds is None
        assert not report.degraded, "an unmeasured clock is not a skewed one"

    async def test_the_report_says_it_could_not_be_measured_not_that_it_agreed(self) -> None:
        report = await run(Source(clock=clock_probe(reporting(None))))

        printed = report_message(report)
        assert "does not report its own time" in printed

    async def test_an_unreachable_source_leaves_the_clock_unchecked(self) -> None:
        report = await run(
            Source(
                connectivity=Connectivity(reachable=False, detail="401", status_code=401),
                clock=clock_probe(reporting(NOW)),
            )
        )

        assert report.clock is not None
        assert report.clock.state is SkewState.UNCHECKED


class TestReadingAVendorsDateHeader:
    """Every one of the six answers HTTP, and HTTP carries the server's clock."""

    def test_an_rfc_1123_date_is_read_as_an_aware_instant(self) -> None:
        assert http_date("Mon, 10 Aug 2026 12:00:00 GMT") == NOW

    def test_a_header_that_is_absent_or_unparseable_yields_no_time(self) -> None:
        assert http_date("") is None
        assert http_date("whenever") is None


# --- the rest of the report is untouched --------------------------------------


class TestAVendorThatIsNotASignalSource:
    async def test_a_verifier_without_the_probes_reports_neither(self) -> None:
        """Eighty-odd integrations declare no window and no clock, and must not
        acquire an empty one that reads as a finding."""
        report = await run(Source())

        assert report.data_window is None
        assert report.clock is None
        assert report.ok
        assert not report.degraded
        assert "window" not in report_message(report)

    async def test_the_record_carries_the_new_probes_only_when_they_ran(self) -> None:
        bare = (await run(Source())).to_record()
        assert "data_window" not in bare
        assert "clock" not in bare

        probed = (
            await run(Source(window=window_probe(returning(4)), clock=clock_probe(reporting(NOW))))
        ).to_record()
        assert probed["data_window"]["rows"] == 4  # type: ignore[index]
        assert probed["clock"]["offset_seconds"] == 0.0  # type: ignore[index]

    async def test_a_permission_denial_still_fails_the_report_alongside_a_good_window(self) -> None:
        async def denied(transport: object, context: object) -> object:
            raise IntegrationError(
                "no", integration="acme", reason=IntegrationErrorReason.FORBIDDEN
            )

        report = await run(
            Source(
                probes=(PermissionProbe(permission=READ_SERIES, call=denied),),
                window=window_probe(returning(7)),
            )
        )

        assert report.missing_permissions == ("query",)
        assert not report.ok
