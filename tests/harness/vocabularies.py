"""The four controlled vocabularies a fixture is checked against.

Two of them are closed sets written down here. A failure mode and an
adversarial signal are properties of the *incident*, and nothing in the
repository declares either — so the alternative to a list is free text, and
free text means ``probe_misconfig`` and ``probe_misconfiguration`` are two
failure modes as far as any report is concerned.

The other two are read from the running system, and that is the load-bearing
half. Root causes come from the shipped taxonomy; trajectory actions come from
the live capability catalogue. An answer key that names ``list_pods`` after the
capability became ``kubernetes_workload_events`` would otherwise go on scoring
— badly, silently, and in a way indistinguishable from the agent getting worse.
Making it a load error means a rename breaks the build, in the change that
caused it, naming the scenario that has to be updated.

Both live lookups are cached for the process. Building the capability registry
imports every capability package in the repository, and doing that once per
fixture would put a package walk inside a loop over the corpus.
"""

from __future__ import annotations

from functools import cache
from typing import Final

# --- Closed vocabularies -----------------------------------------------------

#: What kind of thing went wrong, at the granularity a scenario is designed
#: around. Coarser than a root cause on purpose: several failure modes map onto
#: ``resource_exhaustion``, and the pair is what makes "the agent gets memory
#: pressure right and connection pools wrong" a sentence the suite can support.
FAILURE_MODES: Final[frozenset[str]] = frozenset(
    {
        "none",
        "memory_exhaustion",
        "cpu_saturation",
        "disk_pressure",
        "file_descriptor_exhaustion",
        "connection_pool_exhaustion",
        "probe_misconfiguration",
        "misconfigured_limit",
        "missing_configuration",
        "secret_expiry",
        "certificate_expiry",
        "bad_deployment",
        "failed_rollout",
        "dependency_timeout",
        "dependency_outage",
        "rate_limited",
        "throttled_quota",
        "dns_failure",
        "network_partition",
        "load_balancer_misrouting",
        "slow_query",
        "lock_contention",
        "replication_lag",
        "connection_refused",
        "message_backlog",
        "consumer_lag",
        "cache_stampede",
        "data_corruption",
        "schema_mismatch",
        "clock_skew",
        "node_failure",
        "zone_outage",
        "control_plane_degraded",
        "scheduled_maintenance",
        "credential_compromise",
        "unauthorised_access",
        "traffic_spike",
        "unhandled_exception",
        "infinite_retry_loop",
    }
)

#: The confounders a scenario may plant. Declared per scenario so the suite can
#: report resistance to misleading evidence separately from plain accuracy — an
#: agent that is right when the evidence is clean and wrong when it is not has
#: a specific weakness, and one accuracy number hides it.
ADVERSARIAL_SIGNALS: Final[frozenset[str]] = frozenset(
    {
        "healthy_replicas_present",
        "benign_prior_event",
        "coincident_deployment",
        "coincident_traffic_spike",
        "misleading_error_log",
        "noisy_neighbour_metric",
        "recovered_dependency",
        "stale_alert_annotation",
        "unrelated_recent_change",
        "louder_secondary_symptom",
        "resolved_upstream_incident",
        "misattributed_saturation",
    }
)

#: How severe the incident is said to be when it arrives. The same words the
#: alert adapters normalise onto, so a scenario's severity and a run's severity
#: are comparable without a translation table.
SEVERITIES: Final[frozenset[str]] = frozenset(
    {"critical", "high", "medium", "low", "info", "unknown"}
)

#: How a golden trajectory is compared against what the agent actually did.
#: ``exact`` demands the sequence; ``lcs`` demands the order without demanding
#: adjacency; ``set`` demands the actions and ignores order entirely.
TRAJECTORY_MATCHINGS: Final[frozenset[str]] = frozenset({"exact", "lcs", "set"})


# --- Vocabularies read from the running system -------------------------------


@cache
def trajectory_actions() -> frozenset[str]:
    """Return every capability name an answer key may reference (FR-005).

    Tools and skills both, because a trajectory that consulted a methodology
    before calling anything is a trajectory, and an answer key should be able
    to say so.
    """
    from capabilities.registry.catalogue import build_registry

    registry = build_registry()
    return frozenset(registry.tools) | frozenset(registry.skills)


@cache
def root_cause_categories() -> frozenset[str]:
    """Return the closed root-cause vocabulary a diagnosis is scored against."""
    from core.domain.diagnosis.taxonomy import ROOT_CAUSE_CATEGORIES

    return frozenset(found.value for found in ROOT_CAUSE_CATEGORIES)


@cache
def integration_names() -> frozenset[str]:
    """Return every integration the repository ships, as an evidence fixture names one."""
    from integrations._catalogue.discovery import catalogue

    return frozenset(entry.name for entry in catalogue())


@cache
def evidence_sources() -> frozenset[str]:
    """Return every source a scenario may declare evidence from.

    Integrations plus the sources that belong to no vendor — reasoning, memory,
    the knowledge base — because those are what a capability declares as its
    ``evidence_source`` and therefore what an evidence entry is attributed to.
    Nothing here is written down twice: the set is the union of what the
    integration catalogue found and what the metadata enum names.
    """
    from core.capability.metadata import EvidenceSource

    return integration_names() | frozenset(found.value for found in EvidenceSource)


__all__ = [
    "ADVERSARIAL_SIGNALS",
    "FAILURE_MODES",
    "SEVERITIES",
    "TRAJECTORY_MATCHINGS",
    "evidence_sources",
    "integration_names",
    "root_cause_categories",
    "trajectory_actions",
]
