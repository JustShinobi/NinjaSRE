"""The things a deployment is responsible for, and how each of them is doing.

The thirteenth port, and the first one whose records describe somebody else's
infrastructure rather than our own work. That difference decides nearly every
shape below.

**Identity is derived, never assigned.** A resource's key is its source
integration plus the identifier that source uses for it, hashed. So a rename
updates a row, a restart finds the same row, and a re-discovery cannot produce a
second one. The derivation itself lives in ``platform/estate/identity.py``,
because it is a rule rather than storage; what this port guarantees is that the
key is the primary key, so a duplicate is unrepresentable rather than merely
unlikely.

**Absent is not unhealthy, and only a successful sweep may assign it.** A
container somebody deleted has not failed. Conflating the two gives an operator
a permanent alarm for every decommissioned machine, and an operator with a
permanent alarm stops reading the estate. ``mark_absent`` therefore takes the
set of identifiers a sweep actually *saw* — a caller with nothing to pass cannot
accidentally mark the world gone — and ``mark_stale`` is the separate operation
a failed sweep gets, which records the reason and touches nothing else.

**Health is a closed set with its working shown.** ``ResourceHealth`` has seven
members and no ``other``. A provider status arrives as a raw string, is mapped
into the set by a declared mapping, and both the mapping's verdict and the raw
string are stored — so an operator can see what the system concluded and what it
was told, and the two can disagree visibly rather than silently.

**Freshness is applied on read, not on write.** Nothing sweeps the estate
turning old rows stale, because a background job that has not run yet would mean
a resource reporting a state the deployment no longer stands behind.
``Resource.reported_health`` takes the instant and the kind's interval and
answers from them, so the answer is right the moment it is asked. The interval
comes from the kind registry, which is why it is a parameter here rather than a
field: this package does not know what kinds exist, and should not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.estate import (
    DEFAULT_FRESHNESS_SECONDS,
    DEFAULT_TRANSITION_HISTORY,
    MAX_ESTATE_PAGE_SIZE,
    MAX_ESTATE_SWEEP_PAGES,
    MAX_MAINTENANCE_SECONDS,
)
from platform.persistence.errors import BoundExceeded


class ResourceHealth(StrEnum):
    """Everything a resource's health may be. There is no eighth member.

    The set is closed because health is compared across providers, and a
    provider-shaped escape hatch would immediately be filled with provider
    strings — at which point "how many things are unhealthy" stops having an
    answer. An observation that maps to nothing is ``UNKNOWN``, which is a real
    answer: we looked, and we cannot say.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STALE = "stale"
    ABSENT = "absent"
    MAINTENANCE = "maintenance"

    @property
    def is_problem(self) -> bool:
        """Return whether this state belongs in an operator's problem count.

        ``MAINTENANCE`` is deliberately excluded and ``ABSENT`` with it: one is
        a machine somebody took down on purpose, the other is a machine
        somebody removed on purpose, and neither is anybody's incident.
        ``STALE`` and ``UNKNOWN`` are excluded too — not knowing is a gap in
        observation rather than a fault in the estate, and counting it as a
        fault makes an integration outage look like an infrastructure one.
        """
        return self in {ResourceHealth.DEGRADED, ResourceHealth.UNHEALTHY}

    @property
    def is_present(self) -> bool:
        """Return whether the resource still exists as far as the estate knows."""
        return self is not ResourceHealth.ABSENT


class SweepOutcome(StrEnum):
    """How one discovery sweep ended.

    ``SUSPENDED`` is not a failure. A sweep that hit its bound and stopped at a
    cursor did everything it was allowed to do, and the resources it did not
    reach are neither absent nor stale — they are simply not this sweep's.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUSPENDED = "suspended"


class ReferenceKind(StrEnum):
    """What kind of thing referenced a resource."""

    RUN = "run"
    INCIDENT = "incident"


@dataclass(frozen=True, slots=True)
class HealthSignal:
    """One named observation, with the value that was actually seen.

    ``value`` is a string rather than a number because half of what a provider
    reports is a word — ``running``, ``stopped``, ``ok`` — and a schema that
    forced numbers would push those into an attribute nobody looks at. The
    comparison that turned it into a state is the rule's, and the rule is named
    on the derivation.
    """

    name: str
    value: str
    observed_at: datetime
    source: str = ""


@dataclass(frozen=True, slots=True)
class HealthDerivation:
    """Why a resource is in the state it is in.

    Every field here exists so that an operator asking "why is this degraded"
    gets an answer rather than a shrug. ``rule`` names the thing that decided;
    ``signals`` are what it decided from; ``raw_status`` is what the provider
    said before anything mapped it, kept because a mapping that turns out to be
    wrong is only diagnosable against the original.
    """

    state: ResourceHealth
    rule: str
    derived_at: datetime
    signals: tuple[HealthSignal, ...] = ()
    raw_status: str = ""
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class HealthTransition:
    """One recorded change of state, and what caused it."""

    transition_id: str
    resource_id: str
    state: ResourceHealth
    occurred_at: datetime
    previous_state: ResourceHealth | None = None
    rule: str = ""
    signal: HealthSignal | None = None


@dataclass(frozen=True, slots=True)
class ResourceSource:
    """One integration's contribution to a resource that several describe.

    Attribution is per source rather than per field. Recording which
    integration supplied which attribute would be more precise and would also
    mean a resource carrying three copies of every value; naming the sources
    and keeping each one's own view of the attributes is what makes "where did
    this come from" answerable without that.
    """

    integration: str
    native_id: str
    display_name: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Resource:
    """One thing the deployment is responsible for.

    ``resource_id`` is derived from ``source`` and ``native_id`` and is the
    primary key. ``sources`` carries every integration that has described this
    resource, the primary one included, so a caller reading attribution does not
    have to special-case the first.
    """

    resource_id: str
    kind: str
    source: str
    native_id: str
    display_name: str = ""
    #: What two integrations describing the same underlying thing agree on: a
    #: machine UUID, a serial number, a fully-qualified hostname. Empty when a
    #: source has nothing to correlate on, and empty never matches empty —
    #: otherwise every uncorrelatable resource would collapse into one.
    correlation_key: str = ""
    parent_id: str | None = None
    team_node_id: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    labels: tuple[str, ...] = ()
    sources: tuple[ResourceSource, ...] = ()
    health: ResourceHealth = ResourceHealth.UNKNOWN
    derivation: HealthDerivation | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    absent_since: datetime | None = None
    maintenance_until: datetime | None = None
    maintenance_reason: str = ""

    def in_maintenance_at(self, now: datetime) -> bool:
        """Return whether a maintenance window covers ``now``."""
        return self.maintenance_until is not None and now < self.maintenance_until

    def is_stale_at(
        self,
        now: datetime,
        *,
        freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
    ) -> bool:
        """Return whether the health observation has aged past its interval.

        A resource that has never been observed is stale rather than fresh: an
        absent derivation is the strongest possible case of "we cannot say".
        """
        if self.derivation is None:
            return True
        return now - self.derivation.derived_at > timedelta(seconds=freshness_seconds)

    def reported_health(
        self,
        now: datetime,
        *,
        freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
    ) -> ResourceHealth:
        """Return the state to show, with absence, maintenance, and age applied.

        The precedence is the whole rule and it is written once, here.
        Absence outranks everything, because a resource that no longer exists
        is not in maintenance and not stale — it is gone. Maintenance outranks
        staleness, because a machine somebody deliberately took down is a thing
        we know rather than a thing we have lost track of. Staleness outranks
        the stored state, which is the point of having it.
        """
        if self.absent_since is not None:
            return ResourceHealth.ABSENT
        if self.in_maintenance_at(now):
            return ResourceHealth.MAINTENANCE
        if self.is_stale_at(now, freshness_seconds=freshness_seconds):
            return ResourceHealth.STALE
        return self.health


@dataclass(frozen=True, slots=True)
class ResourceReference:
    """A run or an incident that touched a resource."""

    resource_id: str
    reference_kind: ReferenceKind
    reference_id: str
    recorded_at: datetime
    summary: str = ""


@dataclass(frozen=True, slots=True)
class SweepRecord:
    """One discovery sweep, and everything that decides what happens next.

    ``cursor`` is what a suspended sweep resumes from and what an incremental
    source is asked to continue from; empty means start at the beginning.
    ``reason`` is populated only for a failure, and it is the text an operator
    reads on every resource the failure made stale.
    """

    sweep_id: str
    source: str
    started_at: datetime
    outcome: SweepOutcome
    completed_at: datetime | None = None
    seen_count: int = 0
    provider_calls: int = 0
    cursor: str = ""
    reason: str = ""
    #: What this sweep concluded beyond the counts. Free-form because it is what
    #: a *post-step* produced — today an enrichment's divergence report, which is
    #: content rather than an error and has to survive the process that found it.
    #: Kept on the sweep rather than on the resources because the interesting
    #: half of a divergence is the entry that has no resource.
    findings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EstateQuery:
    """Every dimension the estate can be sliced by, in one record.

    A record rather than fourteen keyword arguments, because the console, the
    CLI, and the gateway all build the same filter and a signature they each
    spell out is a signature that drifts three ways.

    Empty tuples mean "no filter on this dimension" rather than "match
    nothing". That is the only reading that composes: a caller building a query
    from optional inputs would otherwise have to know which fields to omit.
    """

    kinds: tuple[str, ...] = ()
    health: tuple[ResourceHealth, ...] = ()
    sources: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    team_node_id: str | None = None
    parent_id: str | None = None
    #: Only resources whose health was derived before this instant, which is how
    #: "show me what nobody has looked at lately" is asked.
    observed_before: datetime | None = None
    #: Absent resources are excluded by default. They are history, and an
    #: operator counting their estate is not counting what they deleted.
    include_absent: bool = False
    limit: int = 50
    #: Where to resume: only resources whose identifier sorts strictly after
    #: this one. A keyset cursor rather than an offset, because ``query``
    #: orders by ``resource_id`` and an estate grows underneath an offset — a
    #: sweep that offset-paged one would skip whatever was inserted before its
    #: cursor. Empty means "from the beginning", which is what every caller
    #: that reads one page keeps saying without knowing it.
    after: str = ""


@dataclass(frozen=True, slots=True)
class EstateSummary:
    """The estate in the numbers a dashboard tile shows.

    ``problems`` is computed rather than derivable from ``by_health``, and the
    difference is the point: a resource in maintenance is excluded from the
    problem count and included in ``total``, which is the whole of what an
    operator means by "we know about it and it is not an incident".
    """

    total: int
    captured_at: datetime
    by_kind: Mapping[str, int] = field(default_factory=dict)
    by_health: Mapping[str, int] = field(default_factory=dict)
    by_source: Mapping[str, int] = field(default_factory=dict)
    problems: int = 0
    maintenance: int = 0
    absent: int = 0


# --- The rules both backends share ---------------------------------------------
#
# Four functions rather than four pairs of functions. Everything below is
# *contract* — what a limit above the bound does, what a window longer than the
# bound does, what an upsert preserves, and what identifies a transition — and a
# second copy per backend is a second chance for one of them to clamp where the
# other raises. The shared page-size check in ``fakes/state.py`` and
# ``postgres/repositories/common.py`` is duplicated for historical reasons; this
# port does not repeat the mistake.


def check_estate_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the estate page bound.

    Its own bound rather than the shared query one, because an estate listing is
    what a console table pages through and its natural size is "the whole
    estate" — the one read where the shared bound is the wrong number.
    """
    if limit > MAX_ESTATE_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_ESTATE_PAGE_SIZE,
            constant="MAX_ESTATE_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def check_maintenance_window(*, until: datetime, at: datetime) -> datetime:
    """Return ``until``, or raise if the window exceeds the maintenance bound.

    Raising rather than clamping. An operator who asked for a month and silently
    received a week finds out when the alert they thought was suppressed fires.
    """
    seconds = (until - at).total_seconds()
    if seconds > MAX_MAINTENANCE_SECONDS:
        raise BoundExceeded(
            parameter="maintenance window",
            requested=int(seconds),
            limit=MAX_MAINTENANCE_SECONDS,
            constant="MAX_MAINTENANCE_SECONDS",
        )
    return until


def transition_key(resource_id: str, state: ResourceHealth, at: datetime) -> str:
    """Return the identifier one transition of one resource at one instant gets.

    Deterministic, for the same reason the scheduler's fire key is: two replicas
    that both concluded a resource went absent at the same sweep instant derive
    the same key, and the second write lands on the first rather than beside it.
    """
    return f"{resource_id}@{state.value}@{at.isoformat()}"


def merged(existing: Resource | None, incoming: Resource) -> Resource:
    """Return ``incoming`` merged over ``existing``, keeping what only age knows.

    Five fields survive from the stored record: when it was first seen, whatever
    health was last derived for it, and any maintenance window an operator
    opened. None of them is something a discovery payload has any way to know,
    and all of them are things a naive replace would reset on the next sweep —
    which would make an operator's maintenance window last exactly as long as the
    discovery interval.

    Attributes merge rather than replace, so a second source that knows a
    guest's disk size does not erase the owning team a first source recorded.
    """
    if existing is None:
        return incoming
    return replace(
        incoming,
        first_seen_at=existing.first_seen_at or incoming.first_seen_at,
        attributes={**dict(existing.attributes), **dict(incoming.attributes)},
        health=incoming.health if incoming.derivation is not None else existing.health,
        derivation=incoming.derivation or existing.derivation,
        maintenance_until=incoming.maintenance_until or existing.maintenance_until,
        maintenance_reason=incoming.maintenance_reason or existing.maintenance_reason,
    )


@runtime_checkable
class EstateRepository(Protocol):
    """The estate for one organisation, inside one transaction."""

    # --- The inventory --------------------------------------------------------

    async def upsert(self, resource: Resource) -> Resource:
        """Store ``resource``, merging it over any earlier record, and return it.

        Merging rather than replacing, for the reason ``upsert_node`` merges in
        the topology graph: a second source that knows a guest's disk size must
        not erase the owning team a first source recorded. ``first_seen_at`` is
        preserved from the stored record when it has one, because it is the one
        field a re-discovery can only get wrong.
        """

    async def get(self, resource_id: str) -> Resource | None:
        """Return the resource with ``resource_id``, or ``None``."""

    async def by_native_id(self, *, source: str, native_id: str) -> Resource | None:
        """Return the *present* resource ``source`` calls ``native_id``, or ``None``.

        The lookup reconciliation makes before it decides whether it is looking
        at a new resource or an old one under a new name. Absent resources are
        excluded deliberately: a provider that reuses an identifier after a
        deletion is describing a different thing, and returning the old record
        here is how that thing would be resurrected into somebody else's
        history.
        """

    async def by_correlation_key(self, *, kind: str, correlation_key: str) -> Resource | None:
        """Return the present resource carrying ``correlation_key``, or ``None``.

        How two integrations describing one machine reconcile to one record. An
        empty ``correlation_key`` returns ``None`` rather than matching every
        resource that also has none — the absence of a correlator is not a
        correlator.
        """

    async def query(self, query: EstateQuery) -> tuple[Resource, ...]:
        """Return the resources matching ``query``, by identifier.

        Ordered by ``resource_id`` rather than by anything an operator would
        prefer, because a stable order is what makes paging correct and the
        preferred orders differ per screen. Raises ``BoundExceeded`` above
        ``MAX_ESTATE_PAGE_SIZE``. Ordered by ``resource_id`` so ``after`` is a
        resumable cursor: a caller that wants the whole estate reads a page,
        takes the last identifier, and asks again — which is what makes an
        estate larger than one page answerable rather than truncated.
        """

    async def summarise(self, *, now: datetime) -> EstateSummary:
        """Return the whole estate's counts, with freshness applied at ``now``.

        One pass over the estate rather than one query per bucket. The budget
        this has to meet is declared in ``config.constants.estate``, and a
        summary assembled from nine separate queries has never met it.
        """

    # --- What a sweep concluded ----------------------------------------------

    async def mark_absent(
        self,
        *,
        source: str,
        seen_ids: frozenset[str],
        at: datetime,
        since: datetime | None = None,
    ) -> tuple[str, ...]:
        """Mark ``source``'s resources absent unless seen in or since this sweep.

        Returns the identifiers it marked. Only a *successful* sweep may call
        this, and the argument shape is half the enforcement: the caller has to
        hand over what it actually saw, so "the provider errored and we saw
        nothing" and "the provider answered and there was nothing" cannot be
        spelled the same way by accident.

        ``since`` is what makes a *resumed* sweep safe. A sweep that suspended
        at a cursor and completed on a second pass only holds the second pass's
        identifiers, and marking everything else absent would decommission
        everything the first pass ingested. Passing the instant the sweep chain
        began means "not in ``seen_ids`` **and** not seen since then", which is
        the honest question.

        ``None`` — the default — means ``seen_ids`` alone decides. That is the
        stricter reading and therefore the right default: a caller that has not
        thought about resumption gets the behaviour that cannot silently keep a
        deleted resource, and the sweep opts in to the grace it needs.

        A transition is recorded for each, with the previous state intact.
        Already-absent resources are left exactly as they are, so a second
        sweep does not restamp the timestamp that says when it went.
        """

    async def mark_stale(
        self,
        *,
        source: str,
        at: datetime,
        reason: str,
    ) -> tuple[str, ...]:
        """Mark ``source``'s present resources stale, recording ``reason``.

        What a *failed* sweep gets. Nothing is marked absent, no other source's
        resources are touched, and the reason is stored on each resource's
        derivation so an operator reading one sees the integration failure
        rather than a bare ``stale``.
        """

    async def record_sweep(self, record: SweepRecord) -> SweepRecord:
        """Store ``record``, replacing any earlier one with the same id."""

    async def last_sweep(self, source: str) -> SweepRecord | None:
        """Return ``source``'s most recently started sweep, or ``None``.

        What an incremental source resumes from, and what a suspended sweep
        picks its cursor out of.
        """

    # --- Health ---------------------------------------------------------------

    async def record_health(
        self,
        resource_id: str,
        derivation: HealthDerivation,
    ) -> Resource:
        """Store ``derivation`` as ``resource_id``'s health and return the resource.

        Appends a transition when the state changed and appends nothing when it
        did not, which is what keeps a sweep every fifteen minutes from writing
        ninety-six identical rows a day per resource. Raises ``RecordNotFound``
        for a resource that does not exist: health for something the estate has
        never seen is a caller bug, not a resource.
        """

    async def transitions(
        self,
        resource_id: str,
        *,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[HealthTransition, ...]:
        """Return ``resource_id``'s state changes, most recent first."""

    async def unhealthy_since(
        self,
        resource_ids: tuple[str, ...],
    ) -> Mapping[str, datetime]:
        """Return, for each id currently on an unhealthy streak, when it began.

        The instant of the most recent transition *into* ``UNHEALTHY`` for
        that resource — which is exactly "since when": a resource that
        recovered and fell unhealthy again would have a newer entry, and this
        returns that one. Batched over every id a caller asks about in one
        read, because a listing page asks this question once, not once per
        row. An id with no such transition (or one this build's stored
        history predates) is left out of the mapping rather than guessed at,
        and an id whose current health is not unhealthy may still appear here
        with a stale answer — callers only consult this for resources they
        already know are unhealthy right now.
        """

    async def set_maintenance(
        self,
        resource_id: str,
        *,
        until: datetime,
        reason: str,
        at: datetime,
    ) -> Resource:
        """Put ``resource_id`` into maintenance until ``until`` and return it.

        The window is bounded by ``MAX_MAINTENANCE_SECONDS`` and a longer one
        raises rather than being clamped — an operator who asked for a month and
        silently received a week would find out when the alert fired.
        """

    async def clear_maintenance(self, resource_id: str, *, at: datetime) -> Resource:
        """End ``resource_id``'s maintenance window now and return it."""

    # --- What referenced it ---------------------------------------------------

    async def link(self, reference: ResourceReference) -> ResourceReference:
        """Record that a run or an incident touched a resource. Idempotent."""

    async def references(
        self,
        resource_id: str,
        *,
        reference_kind: ReferenceKind | None = None,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[ResourceReference, ...]:
        """Return what referenced ``resource_id``, most recent first."""


async def whole_estate(
    repository: EstateRepository,
    query: EstateQuery,
    *,
    max_pages: int = MAX_ESTATE_SWEEP_PAGES,
) -> tuple[Resource, ...]:
    """Return every resource ``query`` matches, paging past the page bound.

    The answer to "an estate larger than one page resolves against its first
    page", which 053 recorded, 055 recorded again, and every whole-estate pass
    since has quietly lived with. It pages on ``after``, which is a keyset
    cursor over the same ordering ``query`` returns — so a resource inserted
    while the sweep runs is either seen or not yet reached, and never skipped
    the way an offset would skip it.

    ``max_pages`` is a bound and not a formality: this walks the whole table,
    and a pass with no ceiling is one that turns an estate somebody grew into a
    request that never ends. Reaching it returns what was read rather than
    raising, because a caller enriching four thousand resources wants the four
    thousand it got — and ``len(...) == max_pages * limit`` is how it can tell.
    """
    limit = check_estate_limit(query.limit)
    collected: list[Resource] = []
    cursor = query.after
    for _ in range(max_pages):
        page = await repository.query(replace(query, after=cursor, limit=limit))
        collected.extend(page)
        if len(page) < limit:
            break
        cursor = page[-1].resource_id
    return tuple(collected)


__all__ = [
    "EstateQuery",
    "EstateRepository",
    "EstateSummary",
    "HealthDerivation",
    "HealthSignal",
    "ResourceHealth",
    "HealthTransition",
    "ReferenceKind",
    "Resource",
    "ResourceReference",
    "ResourceSource",
    "SweepOutcome",
    "SweepRecord",
    "whole_estate",
    "check_estate_limit",
    "check_maintenance_window",
    "merged",
    "transition_key",
]
