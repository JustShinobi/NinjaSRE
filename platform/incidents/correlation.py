"""Deciding which incidents are the same incident.

One function and one rule: the grouping key comes off the *detector*, not out of
a heuristic here. That is deliberate and it is the plan's mitigation for
correlation's own risk — grouping too aggressively hides a second cause, and the
only defence against that is an operator being able to read why two things were
grouped without reading this module.

Three groupings, and each answers a different question about what "one cause"
means.

``DETECTOR`` — one incident for the whole detector. A node going down takes
twenty guests with it, and twenty incidents about one node is nineteen
interruptions and one fact.

``PARENT`` — one per parent. Two datastores filling on two different nodes are
two problems with two different answers, even though one detector found both.

``RESOURCE`` — one each. For the detector whose subjects genuinely have nothing
to do with each other, and choosing it is a decision somebody makes rather than
a default they inherit.

The key is also what makes the *second* firing of a condition land on the
existing incident rather than opening another, so it has to be stable across
ticks. Nothing in it comes from the instant, the values, or the tick.
"""

from __future__ import annotations

from platform.observation.detectors.model import DetectorDeclaration, GroupingKey
from platform.persistence.ports.estate_repository import Resource

#: What an alert's correlation key is prefixed with, so an incident raised by a
#: webhook cannot collide with one raised by a detector of the same name.
ALERT_PREFIX = "alert"

#: The same, for an incident somebody opened by hand.
HUMAN_PREFIX = "human"

#: And for a detector that could not be evaluated. Its own namespace, because
#: "the disk detector is broken" and "the disk is full" are different incidents
#: and must not correlate onto each other.
FAILURE_PREFIX = "detector-failure"


def for_detector(
    detector: DetectorDeclaration,
    resource: Resource | None = None,
    *,
    resource_id: str = "",
) -> str:
    """Return the key that decides which incident this finding belongs to.

    Stable across ticks by construction: nothing in it comes from the instant,
    the values, or which replica evaluated it. That is what makes the second
    firing of a condition correlate rather than open a second incident.
    """
    subject = resource.resource_id if resource is not None else resource_id
    match detector.grouping_key:
        case GroupingKey.DETECTOR:
            return f"detector:{detector.detector_id}"
        case GroupingKey.PARENT:
            parent = (resource.parent_id if resource is not None else None) or subject
            return f"detector:{detector.detector_id}:parent:{parent}"
        case GroupingKey.RESOURCE:
            return f"detector:{detector.detector_id}:resource:{subject}"


def for_detector_failure(detector_id: str) -> str:
    """Return the key for an incident about a detector that cannot be evaluated."""
    return f"{FAILURE_PREFIX}:{detector_id}"


def for_alert(*, source: str, fingerprint: str) -> str:
    """Return the key an ingested alert correlates on.

    The upstream's own fingerprint, namespaced by the source. Re-deriving one
    from the payload would mean this deployment disagreeing with the system that
    sent it about which alerts are the same alert — and the upstream is the one
    that will send the resolution.
    """
    return f"{ALERT_PREFIX}:{source}:{fingerprint}"


def for_human(*, subject: str, opened_by: str) -> str:
    """Return the key an incident somebody opened by hand correlates on.

    Namespaced by the person as well as the subject, so two people opening an
    incident about the same machine get two incidents. They noticed different
    things; merging them would lose one of the two accounts.
    """
    return f"{HUMAN_PREFIX}:{opened_by}:{subject}"


__all__ = [
    "ALERT_PREFIX",
    "FAILURE_PREFIX",
    "HUMAN_PREFIX",
    "for_alert",
    "for_detector",
    "for_detector_failure",
    "for_human",
]
