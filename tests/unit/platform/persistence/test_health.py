"""Which findings take a deployment out of rotation, and which merely narrow it.

Every rule here is a decision that can be got wrong in one of two expensive
directions: reporting a working platform as unavailable, or reporting a broken
one as fine. Both are cheap to test and neither is cheap to discover in
production, which is the whole argument for the judgement being a pure function
over what a probe found rather than something each backend decides for itself.
"""

from __future__ import annotations

import pytest

from config.constants.persistence import MINIMUM_POSTGRES_VERSION
from platform.persistence.health import summarise
from platform.persistence.ports import ExtensionStatus, HealthState, MigrationStatus

pytestmark = pytest.mark.unit

HEAD = "0007_topology"


def present(name: str) -> ExtensionStatus:
    """Return an extension the probe found."""
    return ExtensionStatus(name=name, available=True, version="0.7.0")


def missing(name: str) -> ExtensionStatus:
    """Return an extension the probe looked for and did not find."""
    return ExtensionStatus(name=name, available=False)


def test_a_complete_deployment_is_healthy() -> None:
    health = summarise(
        connected=True,
        server_version=MINIMUM_POSTGRES_VERSION,
        extensions=(present("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    assert health.state is HealthState.HEALTHY
    assert health.is_ready is True
    assert health.is_live is True
    assert health.reasons == ()


def test_an_unreachable_database_reports_nothing_it_did_not_observe() -> None:
    # A probe that could not connect has no opinion on extensions it never
    # queried, and inventing one would be a health check making things up.
    health = summarise(connected=False, failure="Connection refused on port 5432.")

    assert health.state is HealthState.UNAVAILABLE
    assert health.is_ready is False
    assert health.is_live is False
    assert health.extensions == ()
    assert health.migrations is None
    assert health.reasons == ("Connection refused on port 5432.",)


def test_a_missing_graph_extension_degrades_rather_than_stops() -> None:
    """FR-002. Taking a working platform out of rotation for this is the bug."""
    health = summarise(
        connected=True,
        extensions=(present("vector"), missing("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    assert health.state is HealthState.DEGRADED
    assert health.is_ready is True
    assert "topology" in " ".join(health.reasons).lower()


def test_a_missing_vector_extension_stops_it() -> None:
    # Without pgvector there is no episodic recall and no knowledge retrieval,
    # which is most of what the platform is for.
    health = summarise(
        connected=True,
        extensions=(missing("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    assert health.state is HealthState.UNAVAILABLE
    assert health.is_ready is False


def test_an_extension_nobody_probed_counts_as_missing() -> None:
    # Otherwise a deployment reports healthy because the probe forgot to look,
    # which is the failure a health check exists to make impossible.
    health = summarise(
        connected=True,
        extensions=(),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    assert health.state is HealthState.UNAVAILABLE
    assert len(health.reasons) == 2


def test_an_unmigrated_schema_stops_it_and_names_both_revisions() -> None:
    health = summarise(
        connected=True,
        extensions=(present("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision="0003_identity"),
    )

    assert health.state is HealthState.UNAVAILABLE
    reason = " ".join(health.reasons)
    assert "0003_identity" in reason
    assert HEAD in reason


def test_an_empty_database_says_so_rather_than_naming_a_revision() -> None:
    health = summarise(
        connected=True,
        extensions=(present("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=None),
    )

    assert "an empty database" in " ".join(health.reasons)


def test_unknown_migration_status_is_not_treated_as_current() -> None:
    health = summarise(
        connected=True,
        extensions=(present("vector"), present("age")),
        migrations=None,
    )

    assert health.state is HealthState.UNAVAILABLE


def test_too_old_a_server_stops_it() -> None:
    health = summarise(
        connected=True,
        server_version=MINIMUM_POSTGRES_VERSION - 1,
        extensions=(present("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    assert health.state is HealthState.UNAVAILABLE
    assert str(MINIMUM_POSTGRES_VERSION) in " ".join(health.reasons)


def test_undecryptable_credentials_degrade_and_are_named() -> None:
    # Surfaces at start, rather than during the first incident that needs the
    # one integration nobody tested.
    health = summarise(
        connected=True,
        extensions=(present("vector"), present("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
        undecryptable_credentials=("slack-bot-token", "pagerduty-key"),
    )

    assert health.state is HealthState.DEGRADED
    assert health.is_ready is True
    reason = " ".join(health.reasons)
    assert "slack-bot-token" in reason
    assert "pagerduty-key" in reason


def test_every_finding_is_reported_and_the_worst_one_decides() -> None:
    # An operator whose deployment is missing an extension *and* behind on
    # migrations should learn both from one probe, not from two restarts.
    health = summarise(
        connected=True,
        server_version=MINIMUM_POSTGRES_VERSION,
        extensions=(present("vector"), missing("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision="0003_identity"),
        undecryptable_credentials=("slack-bot-token",),
    )

    assert health.state is HealthState.UNAVAILABLE
    assert len(health.reasons) == 3


def test_liveness_asks_only_whether_the_connection_works() -> None:
    # A restart fixes a missing extension in no deployment that has ever
    # existed, and restarting on an unmigrated schema turns a stalled release
    # into a crash loop.
    health = summarise(
        connected=True,
        extensions=(missing("vector"), missing("age")),
        migrations=None,
    )

    assert health.state is HealthState.UNAVAILABLE
    assert health.is_live is True


def test_an_extension_can_be_looked_up_by_name() -> None:
    health = summarise(
        connected=True,
        extensions=(present("vector"), missing("age")),
        migrations=MigrationStatus(head_revision=HEAD, applied_revision=HEAD),
    )

    vector = health.extension("vector")
    assert vector is not None
    assert vector.version == "0.7.0"
    assert health.extension("postgis") is None


@pytest.mark.parametrize(
    ("applied", "current"),
    [(HEAD, True), ("0003_identity", False), (None, False)],
)
def test_a_schema_is_current_only_when_it_matches_head(applied: str | None, current: bool) -> None:
    assert MigrationStatus(head_revision=HEAD, applied_revision=applied).is_current is current
