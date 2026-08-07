"""FR-007. A vendor in eleven places, described once.

The assertion that matters most is the last one: the region map and the egress
allow-list are the same tuple. Two lists is how an integration ends up permitted
to reach a region it can no longer name, and nothing fails until an audit.
"""

from __future__ import annotations

import pytest

from integrations._base.regions import Region, RegionMap, UnknownRegion


def test_a_template_builds_every_regional_host_from_one_pattern() -> None:
    """The AWS shape, and the reason regions are data rather than code."""
    regions = RegionMap.from_template(
        "aws",
        template="logs.{region}.amazonaws.com",
        names=("us-east-1", "eu-west-1", "ap-southeast-2"),
        default="us-east-1",
    )

    assert regions.host_for("eu-west-1") == "logs.eu-west-1.amazonaws.com"
    assert regions.names() == ("us-east-1", "eu-west-1", "ap-southeast-2")


def test_a_template_with_no_placeholder_is_refused() -> None:
    """Otherwise every region resolves to one host and nothing says so."""
    with pytest.raises(ValueError, match="every region would resolve to the same host"):
        RegionMap.from_template(
            "aws", template="logs.amazonaws.com", names=("us-east-1",), default="us-east-1"
        )


def test_a_vendor_with_named_rather_than_patterned_hosts_declares_them() -> None:
    regions = RegionMap(
        integration="datadog",
        regions=(
            Region(name="us1", host="api.datadoghq.com", display_name="US1"),
            Region(name="eu1", host="api.datadoghq.eu", display_name="EU1"),
        ),
        default="us1",
    )

    assert regions.base_url("eu1") == "https://api.datadoghq.eu"
    assert regions.get("eu1").label == "EU1"


def test_the_default_region_is_what_a_blank_request_resolves_to() -> None:
    regions = RegionMap.single("pagerduty", host="api.pagerduty.com")

    assert regions.host_for() == "api.pagerduty.com"
    assert regions.get().name == "global"


def test_a_region_nobody_declared_is_named_alongside_the_ones_that_exist() -> None:
    """An operator who typed eu-west for eu-west-1 needs to see the list."""
    regions = RegionMap.from_template(
        "aws", template="logs.{region}.amazonaws.com", names=("eu-west-1",), default="eu-west-1"
    )

    with pytest.raises(UnknownRegion) as raised:
        regions.host_for("eu-west")

    assert "eu-west-1" in str(raised.value)


def test_a_default_that_is_not_a_declared_region_is_refused() -> None:
    with pytest.raises(ValueError, match="the default region"):
        RegionMap(
            integration="acme",
            regions=(Region(name="us", host="api.acme.example"),),
            default="eu",
        )


def test_a_region_whose_host_is_a_url_is_refused() -> None:
    """It would enter the egress allow-list as one, and permit nothing."""
    with pytest.raises(ValueError, match="host name, not a URL"):
        Region(name="us", host="https://api.acme.example/v1")


def test_the_region_map_is_the_egress_allow_list() -> None:
    """One tuple, because two would drift and the drift widens egress."""
    regions = RegionMap.from_template(
        "aws",
        template="logs.{region}.amazonaws.com",
        names=("us-east-1", "eu-west-1"),
        default="us-east-1",
    )

    assert regions.hosts() == ("logs.us-east-1.amazonaws.com", "logs.eu-west-1.amazonaws.com")
    assert all(
        host == regions.host_for(name)
        for name, host in zip(regions.names(), regions.hosts(), strict=True)
    )
