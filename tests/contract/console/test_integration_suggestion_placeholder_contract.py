"""What ``GET /v1/integrations`` says about a vendor the estate has already found.

The catalogue's "Suggested by your estate" section needs three things kept
apart: an address it can offer as a form placeholder, the resource's own
display name (the service and the container it was found in, for the card's
own text), and the resource's raw identifier — which may travel in a link,
never in a card's text (FR-014). All three already live on ``SuggestionView``;
this file is the contract that they stay apart rather than collapsing onto one
string, and that the address is derived from what the estate actually found
rather than written into the route.
"""

from __future__ import annotations

import inspect
import re

from gateway.http.routes.integrations import SuggestionView, list_integrations
from platform.estate.signal_map import ADDRESS_ATTRIBUTE
from platform.estate.suggestions import suggest_integrations
from platform.persistence.ports.estate_repository import Resource

#: A dotted-quad address. Its presence in the route's own source would mean an
#: address reached a response by way of a literal rather than by way of
#: discovery — the thing FR-029 forbids.
_IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def test_suggestion_view_declares_the_address_the_label_and_the_identifier_as_separate_fields() -> (
    None
):
    fields = SuggestionView.model_fields
    for name in ("address", "from_resource", "resource_label", "resource_kind", "because"):
        assert name in fields, f"SuggestionView has no {name!r} field"


def test_the_resource_identifier_and_its_display_label_are_genuinely_different_values() -> None:
    """A card names the service and the container it was found in — never the
    raw identifier — and the identifier still has to travel, in the link.

    Built from a resource whose id and display name are deliberately unlike
    each other, so a suggestion that quietly returned the identifier as its own
    label would be caught here rather than passing by coincidence.
    """
    resource = Resource(
        resource_id="proxmox:ct:139",
        kind="container",
        source="proxmox",
        native_id="139",
        display_name="prometheus-lxc",
        attributes={ADDRESS_ATTRIBUTE: "10.20.20.37"},
        labels=("prometheus",),
    )

    found = suggest_integrations([resource], offers={"prometheus": 9090})

    assert len(found) == 1
    suggestion = found[0]
    assert suggestion.from_resource == "proxmox:ct:139"
    assert suggestion.resource_label == "prometheus-lxc"
    assert suggestion.resource_kind == "container"
    assert suggestion.address == "http://10.20.20.37:9090"
    # The identifier a link may carry is never the string a card's face shows.
    assert suggestion.from_resource != suggestion.resource_label


def test_the_suggested_address_is_derived_from_discovery_never_a_literal_in_the_route() -> None:
    """FR-029: the address a placeholder offers comes from the estate, not from
    a constant this route wrote down.

    Asserted on the route's own source: no dotted-quad address appears in it,
    because there is nothing for one to be doing there — every address the
    route can ever emit is read off a resource ``EstateService`` returned.
    """
    source = inspect.getsource(list_integrations)
    literal_addresses = _IPV4.findall(source)
    assert not literal_addresses, (
        f"list_integrations names a literal address {literal_addresses}; the suggested "
        f"address must come from estate discovery, never from a constant in the route"
    )
    assert "suggested[entry.name].address" in source, (
        "list_integrations does not forward the discovered suggestion's own address into "
        "SuggestionView; a placeholder with nowhere to read a real address from would be "
        "invented rather than discovered"
    )
