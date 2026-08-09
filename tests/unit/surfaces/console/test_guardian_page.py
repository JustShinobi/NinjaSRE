"""FR-015: the reasoning is on the screen, not only in a document.

The point of these tests is not that the page renders. It is that the *reason*
for each threshold is in the rendered output — because the moment an operator
needs that reason is the moment they are looking at the incident it raised, and
a document they would have to go and find is a document they do not read.

The page is driven from the document the API serves, built here by the real
resolution rather than by a hand-written fixture. A fixture would let the page
and the server drift apart in exactly the way the console's own architecture
rule exists to prevent.
"""

from __future__ import annotations

from typing import Any

import pytest

from platform.config_service.schema.policies import DetectorOverrideSettings, GuardianSettings
from platform.guardian.resolution import resolve
from platform.guardian.topology import ClusterShape
from surfaces.console.pages.guardian import detector_detail, guardian_body
from surfaces.console.pages.shell import AREAS, PageContext

pytestmark = pytest.mark.unit


def _served(shape: ClusterShape = ClusterShape.TWO_NODE, **kwargs: Any) -> dict[str, Any]:
    """Return the document the API would serve for a deployment in this state."""
    return resolve(GuardianSettings(enabled=True, **kwargs), shape=shape).to_record()


def _rendered(shape: ClusterShape = ClusterShape.TWO_NODE, **kwargs: Any) -> str:
    """Return the guardian page as the browser receives it."""
    return guardian_body(PageContext(path="/guardian"), _served(shape, **kwargs)).render()


def test_every_active_detector_s_rationale_is_in_the_rendered_page() -> None:
    """SC-003's console half, over the whole active set rather than a sample."""
    html = _rendered()

    for detector in _served()["detectors"]:
        assert detector["name"] in html, detector["detector_id"]
        assert detector["threshold"][:40] in html, detector["detector_id"]
        assert detector["rationale"][:40] in html, detector["detector_id"]
        assert detector["remedy"][:40] in html, detector["detector_id"]


def test_the_page_says_which_topology_it_detected_and_what_follows_from_it() -> None:
    assert "quorum" in _rendered(ClusterShape.TWO_NODE)
    assert "One node" in _rendered(ClusterShape.SINGLE_NODE)


def test_a_dormant_detector_is_shown_as_waiting_rather_than_left_out() -> None:
    """An absent detector reads as one that does not exist."""
    html = _rendered(ClusterShape.SINGLE_NODE)

    assert "cluster-quorum-lost" in html
    assert "they are waiting" in html


def test_an_override_that_changed_nothing_is_reported_on_the_page() -> None:
    """Otherwise it is a threshold that never takes effect for a reason nothing states."""
    html = _rendered(
        overrides=(DetectorOverrideSettings(detector_id="storage-datastore-usag", fire_value=90.0),)
    )

    assert "storage-datastore-usag" in html
    assert "mistyped" in html


def test_a_deployment_that_never_enabled_the_guardian_gets_a_page_rather_than_an_error() -> None:
    document = resolve(GuardianSettings(), shape=ClusterShape.SINGLE_NODE).to_record()

    html = guardian_body(PageContext(path="/guardian"), document).render()

    assert "not enabled" in html.lower()


def test_a_node_the_console_could_not_ask_about_still_renders() -> None:
    """A viewer with no team is a real state, and a page that raised on it would
    be a console that 500s rather than one that says there is nothing to show."""
    html = guardian_body(PageContext(path="/guardian"), {}).render()

    assert "not enabled" in html.lower()


def test_one_detector_in_full_carries_where_its_reading_comes_from() -> None:
    """Which is what tells an operator whether a silent detector is their exporter."""
    detector = next(
        entry
        for entry in _served()["detectors"]
        if entry["detector_id"] == "host-systemd-units-failed"
    )

    html = detector_detail(PageContext(path="/guardian"), detector).render()

    assert "costs the cluster nothing" in html
    assert detector["signal"] in html


def test_the_guardian_is_a_navigable_area_rather_than_an_unlinked_path() -> None:
    assert any(area.path == "/guardian" for area in AREAS)
