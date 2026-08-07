"""``ninjasre cost`` and ``ninjasre integrations health``.

Two commands an operator runs from a shell prompt rather than a dashboard —
FR-023 and FR-024 respectively — driven through the real typer application
against a seeded in-memory deployment, so what is asserted is what the command
emits rather than what a helper returns.

The property both share is that an incomplete answer says so. A spend total that
silently omits an unpriced model is a floor presented as a bill, and a health
line that counted "never configured" as "broken" is one nobody reads twice.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from surfaces.cli.app import app, use_local_services
from surfaces.cli.client import LocalClient
from surfaces.cli.models import CostReport, RunSummary, aggregate_spend
from tests.support.deployment import FakeServices

pytestmark = pytest.mark.unit

runner = CliRunner()


@pytest.fixture(autouse=True)
def _local(services: FakeServices) -> None:
    """Point the application at the seeded deployment for the duration of a test."""
    use_local_services(lambda: services)
    yield
    use_local_services(None)


# -- aggregation (the part both surfaces share) --------------------------------


def run(run_id: str, team: str, at: datetime | None) -> RunSummary:
    """Return one run summary."""
    return RunSummary(run_id=run_id, team_node_id=team, started_at=at)


AUGUST = datetime(2026, 8, 7, tzinfo=UTC)
SEPTEMBER = datetime(2026, 9, 7, tzinfo=UTC)


def test_spend_is_grouped_by_team_and_by_run() -> None:
    report = aggregate_spend(
        [
            (run("r1", "platform", AUGUST), CostReport(runs=1, turns=3, cost=0.10)),
            (run("r2", "platform", AUGUST), CostReport(runs=1, turns=2, cost=0.20)),
            (run("r3", "payments", AUGUST), CostReport(runs=1, turns=1, cost=0.05)),
        ]
    )

    assert [line.label for line in report.by_team] == ["payments", "platform"]
    assert report.by_team[1].cost == pytest.approx(0.30)
    assert report.by_team[1].runs == 2
    assert [line.label for line in report.by_run] == ["r1", "r2", "r3"]
    assert report.total.cost == pytest.approx(0.35)


def test_a_period_excludes_what_falls_outside_it() -> None:
    report = aggregate_spend(
        [
            (run("r1", "platform", AUGUST), CostReport(runs=1, cost=0.10)),
            (run("r2", "platform", SEPTEMBER), CostReport(runs=1, cost=0.20)),
        ],
        since=datetime(2026, 8, 1, tzinfo=UTC),
        until=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert report.total.cost == pytest.approx(0.10)
    assert [line.label for line in report.by_run] == ["r1"]


def test_a_run_with_no_start_time_is_counted_rather_than_dropped() -> None:
    """Excluding it would understate a bill for the least visible reason."""
    report = aggregate_spend(
        [(run("r1", "platform", None), CostReport(runs=1, cost=0.10))],
        since=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert report.total.runs == 1


def test_a_run_with_no_team_is_attributed_somewhere_visible() -> None:
    report = aggregate_spend([(run("r1", "", AUGUST), CostReport(runs=1, cost=0.10))])

    assert [line.label for line in report.by_team] == ["unattributed"]


def test_an_unpriced_run_makes_the_total_a_floor() -> None:
    report = aggregate_spend(
        [
            (run("r1", "platform", AUGUST), CostReport(runs=1, cost=0.10)),
            (run("r2", "platform", AUGUST), CostReport(runs=1, cost=0.0, unpriced_runs=1)),
        ]
    )

    assert report.total.is_complete is False
    assert report.total.unpriced_runs == 1


def test_the_window_is_carried_in_the_report_rather_than_left_to_the_caller() -> None:
    since = datetime(2026, 8, 1, tzinfo=UTC)
    record = aggregate_spend([], since=since).to_record()

    assert record["since"] == since.isoformat()
    assert record["total"]["runs"] == 0


# -- the command ---------------------------------------------------------------


def test_the_cost_command_reports_a_period(services: FakeServices) -> None:
    result = runner.invoke(app, ["cost"])

    assert result.exit_code == 0
    assert "Spend" in result.stdout
    assert "By team" in result.stdout
    assert "By run" in result.stdout


def test_the_cost_command_emits_the_documented_shape() -> None:
    result = runner.invoke(app, ["--json", "cost"])

    payload = json.loads(result.stdout)["data"]

    assert set(payload) == {"since", "until", "total", "by_team", "by_run"}
    assert payload["total"]["runs"] >= 1


def test_a_period_narrows_what_the_command_reports() -> None:
    everything = json.loads(runner.invoke(app, ["--json", "cost"]).stdout)["data"]
    nothing = json.loads(runner.invoke(app, ["--json", "cost", "--since", "2099-01-01"]).stdout)[
        "data"
    ]

    assert everything["total"]["runs"] >= 1
    assert nothing["total"]["runs"] == 0
    assert nothing["by_team"] == []


def test_a_date_that_is_not_a_date_names_the_flag() -> None:
    result = runner.invoke(app, ["--json", "cost", "--until", "last tuesday"])

    assert result.exit_code != 0
    assert "--until" in json.dumps(json.loads(result.stdout)["errors"])


def test_a_purged_run_does_not_stop_the_period_being_reported(
    services: FakeServices,
) -> None:
    """Retention deletions must not look like outages."""
    summaries = asyncio.run(services.runs(team_node_id="", limit=20))
    services.run_details.pop(summaries[0].run_id)

    report = asyncio.run(LocalClient(services=services).spend())

    assert report.total.runs == len(summaries) - 1


# -- integration health --------------------------------------------------------


def test_the_health_command_says_it_in_one_line(services: FakeServices) -> None:
    from surfaces.cli.models import IntegrationStatus

    services.integration_states = {
        "datadog": IntegrationStatus(integration="datadog", configured=True, healthy=True)
    }

    result = runner.invoke(app, ["integrations", "health"])

    assert result.exit_code == 0
    assert result.stdout.strip().endswith("1 healthy, 3 not configured")


def test_the_health_command_emits_the_documented_shape() -> None:
    payload = json.loads(runner.invoke(app, ["--json", "integrations", "health"]).stdout)["data"]

    assert set(payload) == {
        "headline",
        "all_healthy",
        "healthy",
        "unhealthy",
        "unconfigured",
    }


def test_an_integration_that_stopped_answering_is_named(services: FakeServices) -> None:
    from surfaces.cli.models import IntegrationStatus

    services.integration_states = {
        "datadog": IntegrationStatus(
            integration="datadog", configured=True, healthy=False, detail="401 from vendor"
        ),
        "kubernetes": IntegrationStatus(integration="kubernetes", configured=True, healthy=True),
    }

    result = runner.invoke(app, ["integrations", "health"])
    payload = json.loads(runner.invoke(app, ["--json", "integrations", "health"]).stdout)["data"]

    assert "datadog" in result.stdout
    assert "401 from vendor" in result.stdout
    assert payload["unhealthy"] == ["datadog"]
    assert payload["healthy"] == ["kubernetes"]
    assert payload["all_healthy"] is False
