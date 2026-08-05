"""The closed, versioned vocabulary a root cause is allowed to be.

Closed, because the evaluation suite scores ``root_cause_category`` by equality
against an answer key. A free-text category would make that comparison a string
match against whatever the model felt like calling it, and the accuracy number
would move for reasons nobody could attribute.

Versioned, because answer keys reference these names. Adding, removing, or
renaming a category is a migration: the version goes up in the same change that
updates the keys, and every diagnosis records the version it was produced
under, so a corpus scored against two versions is visibly a corpus scored
against two versions.

``UNKNOWN`` is a real answer, not a parse failure. An investigation that
gathered evidence and could not attribute a cause has produced a finding, and
recording it as such is the difference between an honest corpus and one where
every run claims to have found something.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class RootCauseCategory(StrEnum):
    """What kind of thing went wrong."""

    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONFIGURATION_ERROR = "configuration_error"
    DEPENDENCY_FAILURE = "dependency_failure"
    CODE_DEFECT = "code_defect"
    DEPLOYMENT_REGRESSION = "deployment_regression"
    CAPACITY_LIMIT = "capacity_limit"
    NETWORK_FAILURE = "network_failure"
    DATA_QUALITY = "data_quality"
    SECURITY_EVENT = "security_event"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    EXTERNAL_PROVIDER = "external_provider"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    HEALTHY = "healthy"
    UNKNOWN = "unknown"


#: The registry's version, recorded on every diagnosis. Semantic: the major
#: part changes when a category is removed or renamed — which invalidates
#: answer keys — and the minor part when one is added, which does not.
TAXONOMY_VERSION: Final[str] = "1.0.0"

#: Every category, in the order a console or a report should list them, with
#: ``healthy`` and ``unknown`` last because they are outcomes rather than causes.
ROOT_CAUSE_CATEGORIES: Final[tuple[RootCauseCategory, ...]] = tuple(RootCauseCategory)

#: One sentence per category, sent to the model with the structured-output
#: request. Without them a model asked to choose from fourteen bare identifiers
#: routinely picks ``configuration_error`` for anything it cannot place.
CATEGORY_DESCRIPTIONS: Final[dict[RootCauseCategory, str]] = {
    RootCauseCategory.RESOURCE_EXHAUSTION: (
        "A finite resource ran out at run time — memory, disk, file descriptors, "
        "connection-pool slots, threads."
    ),
    RootCauseCategory.CONFIGURATION_ERROR: (
        "A setting was wrong or missing: a limit, a flag, a route, a credential "
        "reference, an environment variable."
    ),
    RootCauseCategory.DEPENDENCY_FAILURE: (
        "Something this system depends on failed or degraded, and the fault is in "
        "that dependency rather than here."
    ),
    RootCauseCategory.CODE_DEFECT: (
        "A bug in the application's own logic, present regardless of load or configuration."
    ),
    RootCauseCategory.DEPLOYMENT_REGRESSION: (
        "A change that shipped caused this, and the previous version did not have the problem."
    ),
    RootCauseCategory.CAPACITY_LIMIT: (
        "Demand exceeded what the system was provisioned for. Nothing is broken; "
        "there is not enough of it."
    ),
    RootCauseCategory.NETWORK_FAILURE: (
        "Connectivity, DNS, routing, TLS, or a load balancer between components."
    ),
    RootCauseCategory.DATA_QUALITY: (
        "Malformed, missing, stale, or unexpected data drove the failure."
    ),
    RootCauseCategory.SECURITY_EVENT: (
        "An attack, an abuse pattern, a credential compromise, or an access-control failure."
    ),
    RootCauseCategory.INFRASTRUCTURE_FAILURE: (
        "A host, node, disk, availability zone, or platform component failed "
        "underneath the workload."
    ),
    RootCauseCategory.EXTERNAL_PROVIDER: (
        "A third-party service or vendor outside the operator's control was the cause."
    ),
    RootCauseCategory.SCHEDULED_MAINTENANCE: (
        "Planned work explains the symptoms; this is not an incident."
    ),
    RootCauseCategory.HEALTHY: (
        "The evidence shows the system is behaving correctly and the alert was "
        "not describing a real problem."
    ),
    RootCauseCategory.UNKNOWN: (
        "The evidence gathered does not support attributing a cause. Choose this "
        "rather than the closest-sounding category."
    ),
}


def category_for(value: str) -> RootCauseCategory:
    """Return the category ``value`` names, or ``UNKNOWN`` when it names none.

    Lenient on shape and strict on membership: a model that answered
    ``"Resource Exhaustion"`` meant the category, and one that answered
    ``"thundering_herd"`` invented a category the answer keys do not have.
    """
    normalised = value.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return RootCauseCategory(normalised)
    except ValueError:
        return RootCauseCategory.UNKNOWN


def is_conclusive(category: RootCauseCategory) -> bool:
    """Return whether ``category`` attributes a cause at all."""
    return category is not RootCauseCategory.UNKNOWN


__all__ = [
    "CATEGORY_DESCRIPTIONS",
    "ROOT_CAUSE_CATEGORIES",
    "TAXONOMY_VERSION",
    "RootCauseCategory",
    "category_for",
    "is_conclusive",
]
