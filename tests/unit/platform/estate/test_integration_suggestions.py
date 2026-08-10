"""Which integrations to offer first, derived from what the estate turned out to hold.

An operator who has just discovered fifty-seven containers is then shown a
catalogue of ninety vendors in alphabetical order, and the first useful thing on
it is on the second screen. What the deployment already knows is that one of
those containers is called ``prometheus`` and sits on ``10.20.20.37`` — so the
Prometheus entry comes first with the address filled in, and the operator's job
shrinks to pasting a token.

The matching is total and boring on purpose. Name and label, exact, no scoring
and no model: a suggestion that was *guessed* is a suggestion whose address an
operator has to check anyway, which is the whole of the saving gone. A resource
nothing matches simply does not produce one, and the catalogue keeps its order.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.estate.suggestions import suggest_integrations
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

SEEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

#: What the catalogue offers, and where a default install of each listens.
OFFERS = {
    "prometheus": 9090,
    "grafana": 3000,
    "loki": 3100,
    "datadog": 0,
}


def resource(
    name: str,
    *,
    address: str = "",
    kind: str = KIND_CONTAINER,
    labels: tuple[str, ...] = (),
) -> Resource:
    return Resource(
        resource_id=f"prox-{name}",
        kind=kind,
        source="proxmox",
        native_id=f"lxc/HAL9000/{name}",
        display_name=name,
        attributes={"address": address} if address else {},
        labels=labels,
        last_seen_at=SEEN,
    )


ESTATE = (
    resource("prometheus", address="10.20.20.37"),
    resource("grafana", address="10.20.20.33"),
    resource("adguard", address="10.20.20.4"),
    resource("pve01", address="10.20.10.11", kind=KIND_NODE),
)


class TestWhatTheEstateMakesObvious:
    def test_a_container_named_for_an_integration_suggests_it(self) -> None:
        found = suggest_integrations(ESTATE, offers=OFFERS)

        assert {suggestion.integration for suggestion in found} == {"prometheus", "grafana"}

    def test_the_address_is_filled_in_from_the_resource_that_matched(self) -> None:
        found = {entry.integration: entry for entry in suggest_integrations(ESTATE, offers=OFFERS)}

        assert found["prometheus"].address == "http://10.20.20.37:9090"
        assert found["grafana"].address == "http://10.20.20.33:3000"

    def test_the_suggestion_says_which_resource_it_came_from(self) -> None:
        """An address an operator cannot trace back is an address they re-check."""
        found = {entry.integration: entry for entry in suggest_integrations(ESTATE, offers=OFFERS)}

        assert found["prometheus"].from_resource == "prox-prometheus"
        assert "prometheus" in found["prometheus"].because

    def test_a_label_matches_as_well_as_a_name(self) -> None:
        estate = (resource("obs-01", address="10.20.20.12", labels=("loki", "lxc")),)

        found = suggest_integrations(estate, offers=OFFERS)

        assert [entry.integration for entry in found] == ["loki"]
        assert found[0].address == "http://10.20.20.12:3100"


class TestWhatItRefusesToGuess:
    def test_a_resource_matching_nothing_suggests_nothing(self) -> None:
        found = suggest_integrations((resource("adguard", address="10.20.20.4"),), offers=OFFERS)

        assert found == ()

    def test_a_partial_name_is_not_a_match(self) -> None:
        """``prometheus-backup`` is a backup of it, not an endpoint for it."""
        estate = (resource("prometheus-backup", address="10.20.20.99"),)

        assert suggest_integrations(estate, offers=OFFERS) == ()

    def test_a_matching_resource_with_no_address_suggests_nothing(self) -> None:
        """The saving is the address. Without one there is nothing to prefill,
        and an entry that jumped the queue with an empty box is worse than the
        alphabet."""
        estate = (resource("prometheus"),)

        assert suggest_integrations(estate, offers=OFFERS) == ()

    def test_an_integration_the_catalogue_does_not_offer_is_never_suggested(self) -> None:
        estate = (resource("nagios", address="10.20.20.50"),)

        assert suggest_integrations(estate, offers=OFFERS) == ()

    def test_a_hosted_vendor_with_no_default_port_is_not_suggested_from_an_address(self) -> None:
        """A container called ``datadog`` is not a Datadog endpoint; Datadog is
        somebody else's API, and offering a local address for it would be
        offering a wrong answer first."""
        estate = (resource("datadog", address="10.20.20.60"),)

        assert suggest_integrations(estate, offers=OFFERS) == ()


class TestTheOrderIsStable:
    def test_two_matches_come_back_in_a_fixed_order(self) -> None:
        """Two runs that disagree about the order are two screens that disagree."""
        once = suggest_integrations(ESTATE, offers=OFFERS)
        again = suggest_integrations(tuple(reversed(ESTATE)), offers=OFFERS)

        assert [entry.integration for entry in once] == [entry.integration for entry in again]

    def test_one_integration_is_suggested_once_even_from_two_resources(self) -> None:
        estate = (
            resource("prometheus", address="10.20.20.37"),
            resource("prometheus", address="10.20.20.38"),
        )

        found = suggest_integrations(estate, offers=OFFERS)

        assert len(found) == 1
        assert found[0].address == "http://10.20.20.37:9090"
