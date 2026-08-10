"""Correlating a change to the resource that broke, and grading the link honestly.

Correlating by time alone produces a false positive in every busy window, and a
report that presents one as a cause is worse than a report that says nothing. So
the correlation runs through the resource — a path names a component, a
component's own state names the machines it manages, and one of those machines
is the one under investigation — and the answer carries how far along that chain
it actually got.

Three strengths, and the fixture is built so that one change produces all three
depending on which resource is asked about. That is the assertion worth having:
the strength is a property of the *pair*, not of the change, and a correlation
engine that graded changes rather than pairs would give the same answer for the
disk that filled up and the container that lost its network.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.changes.correlation import (
    ComponentMap,
    CorrelationStrength,
    ResourceView,
    component_for,
    correlate,
    correlate_all,
)
from platform.changes.models import Change

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 14, 32, tzinfo=UTC)

#: What the cluster's apply record says each component built. The half of the
#: chain a repository layout cannot supply.
COMPONENTS = ComponentMap(
    managed={
        "monitoring": ("hal9000/lxc/115", "hal9000/lxc/116"),
        "networking": ("hal9000/lxc/104",),
        "storage": ("hal9000/lxc/120",),
    }
)

#: The container the monitoring component built, sitting on the infrastructure
#: network. Both facts matter: one reaches it through its component, the other
#: through the firewall profile its zone shares.
MONITORED = ResourceView(
    resource_id="res-aaa",
    correlation_key="hal9000/lxc/115",
    display_name="mon-prometheus",
    zone="infra-zone",
    kind="container",
)

#: The container whose disk filled up. A different component built it, and it is
#: on a different network.
STORAGE = ResourceView(
    resource_id="res-bbb",
    correlation_key="hal9000/lxc/120",
    display_name="fileserver",
    zone="storage-zone",
    kind="container",
)


def _change(*, component: str = "", paths: tuple[str, ...] = ()) -> Change:
    return Change(
        change_id="9f2c1ab",
        occurred_at=NOW,
        author="erik",
        message="a change",
        paths=paths,
        source="infra_apply",
        component=component,
        applied_at=NOW,
    )


class TestPathToComponent:
    """The half of the chain the repository's own layout answers."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("services/monitoring/stack/values.yaml", "monitoring"),
            ("services/monitoring/", "monitoring"),
            ("components/networking/main.tf", "networking"),
            ("monitoring/stack/values.yaml", "monitoring"),
            # A component nothing declares. Not a guess and not the directory
            # name: a path that resolves to a component nobody has is how a
            # correlation gets invented.
            ("services/whatever/main.tf", ""),
            ("README.md", ""),
            ("policies/firewall/infra-zone.yaml", ""),
        ],
    )
    def test_a_path_resolves_to_a_component_only_when_one_is_declared(
        self, path: str, expected: str
    ) -> None:
        assert component_for(path, COMPONENTS.components) == expected

    def test_the_rule_is_driven_by_the_declared_components_rather_than_hard_coded(self) -> None:
        # The same path resolves differently against a different cluster's
        # components, which is what "data-driven" has to mean to be worth
        # saying.
        elsewhere = ComponentMap(managed={"observability": ()})

        assert component_for("services/observability/main.tf", elsewhere.components) == (
            "observability"
        )
        assert component_for("services/monitoring/main.tf", elsewhere.components) == ""


class TestStrength:
    """One change, three resources, three different answers."""

    def test_a_change_whose_component_manages_the_resource_is_the_strong_one(self) -> None:
        change = _change(component="monitoring", paths=("services/monitoring/stack/values.yaml",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.MANAGES_RESOURCE
        assert found.component == "monitoring"
        assert found.matched_path == "services/monitoring/stack/values.yaml"

    def test_the_chain_it_travelled_is_reported_rather_than_only_the_verdict(self) -> None:
        change = _change(component="monitoring", paths=("services/monitoring/stack/values.yaml",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.chain == (
            "services/monitoring/stack/values.yaml",
            "monitoring",
            "hal9000/lxc/115",
        )

    def test_a_shared_policy_naming_the_resources_zone_is_the_middle_strength(self) -> None:
        # The spec's own example: a change under the firewall policy, and a
        # connectivity alert on a workload whose profile lives there. The
        # networking component did not build this container, so the strong link
        # is genuinely absent — and the link that is there is genuinely there.
        change = _change(component="networking", paths=("policies/firewall/infra-zone.yaml",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.TOUCHES_SHARED_POLICY
        assert found.matched_path == "policies/firewall/infra-zone.yaml"

    def test_the_same_change_against_a_disk_that_filled_up_is_temporal_only(self) -> None:
        # The assertion the whole feature turns on. Same change, same window,
        # different resource — and nothing connects them, so nothing is claimed.
        change = _change(component="networking", paths=("policies/firewall/infra-zone.yaml",))

        found = correlate(change, resource=STORAGE, components=COMPONENTS)

        assert found.strength is CorrelationStrength.WINDOW_ONLY
        assert found.chain == ()

    def test_a_window_only_correlation_says_it_is_a_coincidence_in_words(self) -> None:
        change = _change(component="networking", paths=("policies/firewall/infra-zone.yaml",))

        found = correlate(change, resource=STORAGE, components=COMPONENTS)

        assert "coincidence" in found.why.lower()
        assert found.strength.is_temporal_only is True

    def test_proximity_in_time_alone_never_produces_the_strong_verdict(self) -> None:
        # A change with no paths and no component — everything a git host can
        # supply — lands in the window and nowhere else.
        change = _change()

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.WINDOW_ONLY

    def test_a_component_that_manages_nothing_this_estate_knows_is_not_a_link(self) -> None:
        change = _change(component="storage", paths=("services/storage/datastore/main.tf",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.WINDOW_ONLY

    def test_a_path_naming_the_resource_itself_is_a_shared_policy_link(self) -> None:
        # The other reading of the spec's sentence: a workload whose own
        # firewall profile is the file that changed.
        change = _change(paths=("policies/firewall/mon-prometheus.yaml",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.TOUCHES_SHARED_POLICY

    def test_a_policy_path_naming_nothing_the_resource_carries_is_not_a_link(self) -> None:
        change = _change(paths=("policies/firewall/cluster.yaml",))

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.WINDOW_ONLY

    def test_the_strongest_link_wins_when_a_change_touched_both(self) -> None:
        change = _change(
            component="monitoring",
            paths=("policies/firewall/infra-zone.yaml", "services/monitoring/stack/main.tf"),
        )

        found = correlate(change, resource=MONITORED, components=COMPONENTS)

        assert found.strength is CorrelationStrength.MANAGES_RESOURCE


class TestOrdering:
    """What a set of correlated changes looks like when a report reads it."""

    def test_the_strongest_correlations_come_first_and_the_clock_breaks_ties(self) -> None:
        strong = _change(component="monitoring", paths=("services/monitoring/main.tf",))
        policy = _change(paths=("policies/firewall/infra-zone.yaml",))
        noise = _change(paths=("README.md",))

        found = correlate_all([noise, policy, strong], resource=MONITORED, components=COMPONENTS)

        assert [entry.strength for entry in found] == [
            CorrelationStrength.MANAGES_RESOURCE,
            CorrelationStrength.TOUCHES_SHARED_POLICY,
            CorrelationStrength.WINDOW_ONLY,
        ]

    def test_an_unapplied_commit_never_outranks_an_apply_of_the_same_strength(self) -> None:
        # A commit nobody applied did not change the cluster. It is still
        # reported, and it is reported second.
        applied = _change(component="monitoring", paths=("services/monitoring/main.tf",))
        committed = Change(
            change_id="3d81e0c",
            occurred_at=NOW,
            author="erik",
            message="a commit nobody applied",
            paths=("services/monitoring/rules/node.yaml",),
            source="infra_apply",
            component="monitoring",
        )

        found = correlate_all([committed, applied], resource=MONITORED, components=COMPONENTS)

        assert [entry.change.change_id for entry in found] == ["9f2c1ab", "3d81e0c"]

    def test_the_same_input_correlates_to_the_same_order_twice(self) -> None:
        changes = [
            _change(component="monitoring", paths=("services/monitoring/main.tf",)),
            _change(paths=("policies/firewall/infra-zone.yaml",)),
        ]

        first = correlate_all(changes, resource=MONITORED, components=COMPONENTS)
        second = correlate_all(changes, resource=MONITORED, components=COMPONENTS)

        assert [entry.to_record() for entry in first] == [entry.to_record() for entry in second]


def test_the_component_map_reports_which_components_manage_a_resource() -> None:
    assert COMPONENTS.managing(MONITORED) == ("monitoring",)
    assert COMPONENTS.managing(ResourceView(resource_id="res-ccc")) == ()
