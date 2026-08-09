"""Reading a bounded slice of somebody's logs, and linking to a panel that exists.

Both halves are about the same failure: an answer that looks complete and is
not. A log query that silently returned the first five hundred lines of a
thousand, or a report that linked to a default dashboard because the right one
was not mapped, would both hand a responder a confident-looking wrong thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observability_bridge import (
    DASHBOARD_LINK_PADDING_SECONDS,
    MAX_LOG_LINES,
    MAX_LOG_WINDOW_SECONDS,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.observation.bridge.dashboards import (
    DashboardMapping,
    dashboard_link,
    link_for,
)
from platform.observation.bridge.errors import (
    BridgeBoundExceeded,
    DashboardsUnreachable,
    LogSourceUnreachable,
)
from platform.observation.bridge.logs import LogReader, verify_log_source
from platform.observation.bridge.ports import LogLine, LogSource

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 6, 0, tzinfo=UTC)
SELECTOR = '{job="systemd-journal", host="pve01"}'


@dataclass
class StubLogs:
    """A log system with a fixed retention and a fixed pile of lines."""

    retention: int = 86_400
    available: int = 40
    fails: Exception | None = None
    asked: list[tuple[str, datetime, datetime, int]] = field(default_factory=list)

    async def retention_seconds(self) -> int:
        """Return the declared retention."""
        if self.fails is not None:
            raise self.fails
        return self.retention

    async def lines(
        self, *, selector: str, start: datetime, end: datetime, limit: int
    ) -> tuple[LogLine, ...]:
        """Return ``available`` lines, capped by ``limit``, recording what was asked."""
        if self.fails is not None:
            raise self.fails
        self.asked.append((selector, start, end, limit))
        return tuple(
            LogLine(observed_at=end - timedelta(seconds=index), line=f"line {index}")
            for index in range(min(self.available, limit))
        )


@dataclass
class StubDashboards:
    """A dashboard system that is reachable, or is not."""

    fails: Exception | None = None
    checks: int = 0

    async def check(self) -> None:
        """Raise whatever the test configured."""
        self.checks += 1
        if self.fails is not None:
            raise self.fails


def test_a_stub_log_source_satisfies_the_port() -> None:
    """The protocol is structural, so a double proves the shape is reachable."""
    assert isinstance(StubLogs(), LogSource)


@pytest.mark.asyncio
async def test_a_log_source_is_verified_before_anything_depends_on_it() -> None:
    """FR-012: configured and verified, like the metrics source."""
    verification = await verify_log_source(StubLogs(retention=3_600), name="loki")

    assert verification.reachable
    assert verification.retention_seconds == 3_600
    assert "loki" in verification.summary


@pytest.mark.asyncio
async def test_an_unreachable_log_source_says_so_rather_than_reporting_no_retention() -> None:
    """Zero retention and an unreachable source are different facts."""
    verification = await verify_log_source(
        StubLogs(fails=LogSourceUnreachable("loki", reason="no route to host")), name="loki"
    )

    assert not verification.reachable
    assert "no route to host" in verification.failure
    assert verification.retention_seconds == 0


@pytest.mark.asyncio
async def test_a_log_query_is_bounded_and_states_its_bound() -> None:
    """FR-014: the bound is in the result, not only in the configuration."""
    source = StubLogs(available=1_000)

    answer = await LogReader(source=source, window_seconds=900, limit=50).read(SELECTOR, at=EPOCH)

    assert len(answer.lines) == 50
    assert answer.bound.limit == 50
    assert answer.bound.window_seconds == 900
    assert answer.truncated
    assert "50" in answer.summary


@pytest.mark.asyncio
async def test_a_query_inside_its_bounds_reports_itself_complete() -> None:
    """The same statement, the other way round: this is all there was."""
    answer = await LogReader(source=StubLogs(available=12)).read(SELECTOR, at=EPOCH)

    assert not answer.truncated
    assert answer.complete


@pytest.mark.asyncio
async def test_a_retention_shorter_than_the_window_is_stated_not_glossed_over() -> None:
    """SC-006's honesty half: a partial answer must not read as a complete one."""
    reader = LogReader(source=StubLogs(retention=600), window_seconds=3_600)

    answer = await reader.read(SELECTOR, at=EPOCH)

    assert not answer.complete
    assert answer.retention_shortfall_seconds == 3_000
    assert "retention" in answer.summary
    assert answer.start == EPOCH - timedelta(seconds=600)


@pytest.mark.asyncio
async def test_a_source_with_no_declared_retention_is_not_treated_as_keeping_nothing() -> None:
    """Zero is "it has no opinion". Refusing every query on it would be wrong."""
    answer = await LogReader(source=StubLogs(retention=0), window_seconds=3_600).read(
        SELECTOR, at=EPOCH
    )

    assert answer.retention_shortfall_seconds == 0
    assert answer.start == EPOCH - timedelta(seconds=3_600)


def test_a_window_past_the_ceiling_is_refused_where_it_is_declared() -> None:
    """A query that can take the operator's own logging down is not configurable."""
    with pytest.raises(BridgeBoundExceeded):
        LogReader(source=StubLogs(), window_seconds=MAX_LOG_WINDOW_SECONDS + 1)
    with pytest.raises(BridgeBoundExceeded):
        LogReader(source=StubLogs(), limit=MAX_LOG_LINES + 1)


@pytest.mark.asyncio
async def test_an_unreachable_log_source_raises_rather_than_returning_no_lines() -> None:
    """An empty stream and a dead Loki lead to opposite conclusions."""
    reader = LogReader(source=StubLogs(fails=LogSourceUnreachable("loki", reason="refused")))

    with pytest.raises(LogSourceUnreachable):
        await reader.read(SELECTOR, at=EPOCH)


# --- Dashboards -------------------------------------------------------------------

MAPPING = DashboardMapping(
    dashboard_uid="pve-nodes",
    title="Proxmox nodes",
    base_url="https://grafana.lan",
    resource_kinds=(KIND_NODE,),
    panel_id="4",
    description="the node overview the operator already had open during the last outage",
)


def test_a_link_carries_the_incidents_own_window() -> None:
    """FR-017: a panel showing the wrong hour is worse than no panel."""
    link = link_for(
        (MAPPING,),
        resource_kind=KIND_NODE,
        detector_id="",
        opened_at=EPOCH,
        closed_at=EPOCH + timedelta(minutes=20),
    )

    assert link is not None
    padding = DASHBOARD_LINK_PADDING_SECONDS * 1_000
    assert f"from={int(EPOCH.timestamp() * 1_000) - padding}" in link.url
    assert link.url.startswith("https://grafana.lan/d/pve-nodes")
    assert "viewPanel=4" in link.url


def test_a_dashboard_maps_to_a_detector_as_well_as_to_a_kind() -> None:
    """FR-016: a detector's own panel is the more useful mapping when it exists."""
    by_detector = DashboardMapping(
        dashboard_uid="thin-pools",
        title="Thin pools",
        base_url="https://grafana.lan",
        detector_ids=("thin-pool-metadata-full",),
        description="the metadata percentage that stops writes while data still looks fine",
    )

    link = link_for(
        (MAPPING, by_detector),
        resource_kind=KIND_NODE,
        detector_id="thin-pool-metadata-full",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert link is not None
    assert link.dashboard_uid == "thin-pools"


def test_no_mapped_dashboard_means_no_link_and_never_a_default() -> None:
    """SC-007: a link to a default dashboard is a dead end wearing an answer's clothes."""
    link = link_for(
        (MAPPING,),
        resource_kind=KIND_CONTAINER,
        detector_id="guest-cpu-saturated",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert link is None


@pytest.mark.asyncio
async def test_a_reachable_grafana_produces_the_link() -> None:
    """The ordinary case, and the one the check exists to distinguish from the next."""
    source = StubDashboards()

    outcome = await dashboard_link(
        source,
        mappings=(MAPPING,),
        resource_kind=KIND_NODE,
        detector_id="",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert outcome.link is not None
    assert outcome.omitted_because == ""
    assert source.checks == 1


@pytest.mark.asyncio
async def test_grafana_behind_authentication_we_do_not_hold_degrades_to_no_link() -> None:
    """T-027: the reason is recorded; the report does not link somewhere that 401s."""
    source = StubDashboards(fails=DashboardsUnreachable("grafana", reason="401 unauthorized"))

    outcome = await dashboard_link(
        source,
        mappings=(MAPPING,),
        resource_kind=KIND_NODE,
        detector_id="",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert outcome.link is None
    assert "401 unauthorized" in outcome.omitted_because


@pytest.mark.asyncio
async def test_an_unmapped_kind_does_not_even_ask_grafana() -> None:
    """Checking reachability for a link nobody would build is a round trip for nothing."""
    source = StubDashboards()

    outcome = await dashboard_link(
        source,
        mappings=(MAPPING,),
        resource_kind=KIND_CONTAINER,
        detector_id="",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert outcome.link is None
    assert source.checks == 0
    assert "no dashboard" in outcome.omitted_because
