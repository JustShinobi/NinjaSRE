"""What an alert is about, in this deployment's own terms.

An alert arrives naming something in the vocabulary of whatever sent it: a
scrape target's address, a hypervisor guest's number, the URL a prober asked
for. None of those is a resource identifier, and every stage after intake — the
signal map, the capability selection, the incident's subject, the resource
page's history — is keyed by one. Resolving the two is this module's whole job.

Three properties decide the shape.

**The order the labels are tried is the correctness argument.** A host-side
exporter publishes a guest's series labelled with the *host's* address and the
guest's own number, so an alert about a container under memory pressure carries
both. Reading the address first resolves to the hypervisor, and the resulting
investigation is about the wrong machine — with citations. The numeric
identifier is the specific answer, so it is asked for first, and
``ALERT_TARGET_LABELS`` is where that order is written down.

**A target nothing matches is a finding, not a discard.** "An alert arrived for
something this estate does not hold" is information about the estate — the same
class of thing as the reconciliation divergence a sweep produces, and it means
one of two useful things: a resource nobody swept, or a receiver pointed at the
wrong deployment. ``AlertResolution`` therefore carries exactly one of a
resolved target and an ``UnresolvedAlertTarget``, and there is no way to
construct it carrying neither.

**Resolution is pure, and estate-side.** It takes the resources rather than a
store, so the webhook handler, a routing rule, and a detector can all use it
against whatever they already hold. It lives in ``platform/estate/`` rather than
in the webhook package for the same reason: the handler is a caller, and a tier
1 module owning this would leave tier 2 and 3 consumers reaching upwards for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, ip_address, ip_network
from typing import Any, Final
from urllib.parse import urlsplit

from config.constants.estate import (
    ALERT_TARGET_LABELS,
    ALERT_VMID_LABEL,
    ALERT_ZONE_INFERENCE_PREFIX,
)
from core.domain.alerts.normalisation import NormalisedAlert
from platform.estate.enrichment import ZoneMap
from platform.estate.signal_map import ADDRESS_ATTRIBUTE, VMID_ATTRIBUTE
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.incident_store import Incident

#: The attribute a workload carries the domain it answers on. Written by the
#: declared inventory rather than by a sweep — a provider knows a container's
#: address and never what it is for.
DOMAIN_ATTRIBUTE: Final = "domain"

#: The attribute an applied enrichment records a resource's network division in.
ZONE_ATTRIBUTE: Final = "zone"

#: What an unresolved target is called where a resource identifier is expected —
#: an incident subject, most of all. Prefixed rather than left bare so a finding
#: can never be mistaken for a resource this deployment holds, and so the
#: findings can be selected without a second store to keep them in.
UNRESOLVED_TARGET_PREFIX: Final = "unresolved-target:"

#: What the finding is called when the alert named nothing at all. A word rather
#: than an empty tail, because ``unresolved-target:`` on its own reads as a
#: truncation and this is a real, distinct case: a rule that does not say what
#: it is about.
UNNAMED_TARGET: Final = "unnamed"


class AlertMatch(StrEnum):
    """How a target was recognised.

    Recorded on the resolution and carried onto the incident, because "this
    alert is about that container" is a claim and the way it was reached is the
    evidence for it. A resolution by address and one by declared domain are
    trusted differently when the answer turns out to be wrong.
    """

    #: The guest's own numeric identifier, which is what a host-side series is
    #: labelled with and what the hypervisor itself is keyed by.
    VMID = "vmid"
    #: The address the resource reports, matched exactly.
    ADDRESS = "address"
    #: The domain the declared inventory says this workload answers on.
    DOMAIN = "domain"
    #: The resource's own name, matched when nothing more structural did.
    NAME = "name"


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """The estate resource an alert turned out to be about."""

    resource_id: str
    kind: str
    display_name: str
    matched_on: AlertMatch
    #: The label that carried the target, and the value read out of it after
    #: any scheme, path and port were removed.
    label: str
    value: str
    #: Where the resource sits, when the estate knows. Reported rather than
    #: re-derived by every reader: an investigation that says "in the apps zone"
    #: and a screen that says otherwise is a disagreement nobody can settle.
    zone: str = ""

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form an incident stores."""
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "display_name": self.display_name,
            "matched_on": self.matched_on.value,
            "label": self.label,
            "value": self.value,
            "zone": self.zone,
        }

    def evidence(self) -> dict[str, str]:
        """Return what an incident subject records about how it was identified.

        Narrower than the record: the resource is already the subject, so what
        is left to say is how the claim was reached — which is what an operator
        checks when the answer turns out to be about the wrong machine.
        """
        return {
            "matched_on": self.matched_on.value,
            "target_label": self.label,
            "target": self.value,
            "zone": self.zone,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, str]) -> ResolvedTarget:
        """Return the target a stored record describes."""
        return cls(
            resource_id=str(record.get("resource_id", "")),
            kind=str(record.get("kind", "")),
            display_name=str(record.get("display_name", "")),
            matched_on=AlertMatch(record.get("matched_on", AlertMatch.NAME.value)),
            label=str(record.get("label", "")),
            value=str(record.get("value", "")),
            zone=str(record.get("zone", "")),
        )


@dataclass(frozen=True, slots=True)
class UnresolvedAlertTarget:
    """An alert target this estate does not hold, kept as a finding.

    ``why`` is a sentence rather than a code, for the reason 053's divergence
    detail is one: what an operator does about it depends entirely on which of
    the two it is — something nobody swept, or a receiver pointed at the wrong
    deployment — and only prose distinguishes them.
    """

    label: str
    value: str
    why: str
    #: The zone the address would sit in, when the target was an address and
    #: something could place it. A finding that says "in the apps zone, and no
    #: resource there holds it" is one an operator can act on.
    zone: str = ""

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form an incident stores."""
        return {"label": self.label, "value": self.value, "why": self.why, "zone": self.zone}

    @property
    def subject_id(self) -> str:
        """Return the identifier an incident names this finding by.

        Prefixed, so a screen listing subjects never renders a finding as
        though it were a resource, and so the findings can be selected out of
        the incidents that hold them without a store of their own.
        """
        return f"{UNRESOLVED_TARGET_PREFIX}{self.value or self.label or UNNAMED_TARGET}"

    def evidence(self) -> dict[str, str]:
        """Return what an incident subject records about this finding."""
        return {"target_label": self.label, "target": self.value, "zone": self.zone}

    @classmethod
    def from_record(cls, record: Mapping[str, str]) -> UnresolvedAlertTarget:
        """Return the finding a stored record describes."""
        return cls(
            label=str(record.get("label", "")),
            value=str(record.get("value", "")),
            why=str(record.get("why", "")),
            zone=str(record.get("zone", "")),
        )


@dataclass(frozen=True, slots=True)
class AlertResolution:
    """What one alert turned out to be about: a resource, or a finding.

    Exactly one of the two, enforced at construction. Neither would be a target
    nobody accounted for, which is the failure this module exists to prevent;
    both would be two answers, and whichever a caller happened to read first
    would not be a decision anybody took.
    """

    resolved: ResolvedTarget | None = None
    unresolved: UnresolvedAlertTarget | None = None

    def __post_init__(self) -> None:
        if (self.resolved is None) == (self.unresolved is None):
            raise ValueError(
                "an alert resolution is exactly one of a resolved target and an "
                "unresolved one. Neither means a target went unaccounted for; both "
                "means there are two answers and no way to choose."
            )

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form an incident and a route carry."""
        if self.resolved is not None:
            return {"resolved": self.resolved.to_record()}
        assert self.unresolved is not None  # noqa: S101 — the invariant above
        return {"unresolved": self.unresolved.to_record()}


@dataclass(frozen=True, slots=True)
class UnresolvedTargetFinding:
    """One unresolved target, and the incident that is the record of it.

    Read back out of the incidents rather than kept in a store of its own. The
    finding only exists because an alert arrived, the incident is already the
    record of that alert, and a second store would be a second thing to expire.
    """

    target: UnresolvedAlertTarget
    incident_id: str
    alert_name: str
    observed_at: datetime

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a route serves and a screen renders."""
        return {
            **self.target.to_record(),
            "incident_id": self.incident_id,
            "alert_name": self.alert_name,
            "observed_at": self.observed_at.isoformat(),
        }


def unresolved_targets(incidents: Sequence[Incident]) -> tuple[UnresolvedTargetFinding, ...]:
    """Return every unresolved alert target ``incidents`` recorded, newest first.

    One entry per target rather than per incident: a receiver pointed at the
    wrong deployment produces the same finding on every delivery, and a list
    that repeated it would bury the second thing it is telling you.
    """
    found: dict[str, UnresolvedTargetFinding] = {}
    for incident in incidents:
        for subject in incident.subjects:
            if not subject.resource_id.startswith(UNRESOLVED_TARGET_PREFIX):
                continue
            target = UnresolvedAlertTarget(
                label=subject.evidence.get("target_label", ""),
                value=subject.evidence.get("target", ""),
                why=subject.detail,
                zone=subject.evidence.get("zone", ""),
            )
            existing = found.get(subject.resource_id)
            if existing is not None and existing.observed_at >= incident.opened_at:
                continue
            found[subject.resource_id] = UnresolvedTargetFinding(
                target=target,
                incident_id=incident.incident_id,
                alert_name=subject.evidence.get("alert", incident.title),
                observed_at=incident.opened_at,
            )
    return tuple(
        sorted(
            found.values(), key=lambda entry: (entry.observed_at, entry.target.value), reverse=True
        )
    )


def resolve_alert(
    alert: NormalisedAlert,
    *,
    resources: Sequence[Resource],
    zones: ZoneMap = ZoneMap(),
) -> AlertResolution:
    """Return the estate resource ``alert`` is about, or the finding that it is not.

    ``resources`` is what the caller already holds — a page of the estate, a
    filtered slice, or the whole of a small one. ``zones`` is the operator's
    declared network map when there is one; without it an unmatched address is
    placed by the estate's own neighbours on the same ``/24``, which is an
    inference and is why a declared map outranks it.
    """
    index = _EstateIndex.of(resources)

    for label in ALERT_TARGET_LABELS:
        raw = str(alert.labels.get(label, "")).strip()
        if not raw:
            continue
        return _resolve_target(label, raw, index=index, zones=zones)

    return AlertResolution(
        unresolved=UnresolvedAlertTarget(
            label="",
            value="",
            why=(
                f"the alert {alert.alert_name or 'that arrived'} names no target: none of "
                f"{', '.join(ALERT_TARGET_LABELS)} is set on it, so there is nothing to look "
                f"up. An alert rule that names what it is about is what makes an "
                f"investigation start on the right machine"
            ),
        )
    )


def _resolve_target(
    label: str,
    raw: str,
    *,
    index: _EstateIndex,
    zones: ZoneMap,
) -> AlertResolution:
    """Return the resolution for the one label that carried a target.

    The first label in declared order wins outright rather than falling through
    to the next: an alert carrying both a guest number this estate does not hold
    and its host's address would otherwise resolve to the host, which is the
    wrong-machine failure the order exists to prevent.
    """
    if label == ALERT_VMID_LABEL:
        found = index.by_vmid(raw)
        if found is not None:
            return AlertResolution(resolved=_target(found, AlertMatch.VMID, label, raw))
        return AlertResolution(
            unresolved=UnresolvedAlertTarget(
                label=label,
                value=raw,
                why=(
                    f"the alert is about hypervisor guest {raw}, and no guest in this estate "
                    f"carries that identifier. Either it was created since the last sweep, or "
                    f"this receiver is pointed at a deployment that does not watch that cluster"
                ),
            )
        )

    host = _host_of(raw)
    address = _address_of(host)
    if address is not None:
        zone = zones.zone_for(host) or index.zone_near(address)
        found = index.by_address(host)
        if found is not None:
            return AlertResolution(
                resolved=_target(found, AlertMatch.ADDRESS, label, host, zone=zone)
            )
        return AlertResolution(
            unresolved=UnresolvedAlertTarget(
                label=label,
                value=host,
                zone=zone,
                why=(
                    f"the alert is about {host}"
                    + (f", which sits in the {zone} zone" if zone else "")
                    + ", and no resource in this estate reports that address. Either it was "
                    "never swept, or something outside this estate is being watched by a "
                    "receiver pointed here"
                ),
            )
        )

    found = index.by_domain(host)
    if found is not None:
        return AlertResolution(
            resolved=_target(found, AlertMatch.DOMAIN, label, host, zone=_zone_of(found))
        )
    found = index.by_name(host)
    if found is not None:
        return AlertResolution(
            resolved=_target(found, AlertMatch.NAME, label, host, zone=_zone_of(found))
        )
    return AlertResolution(
        unresolved=UnresolvedAlertTarget(
            label=label,
            value=host,
            why=(
                f"the alert is about {host}, which no declared domain points at and which "
                f"matches nothing this estate holds by name. A services entry naming the "
                f"workload that answers it is what would resolve this"
            ),
        )
    )


def _target(
    resource: Resource,
    matched_on: AlertMatch,
    label: str,
    value: str,
    *,
    zone: str = "",
) -> ResolvedTarget:
    """Return the resolved target ``resource`` is, with its zone filled in."""
    return ResolvedTarget(
        resource_id=resource.resource_id,
        kind=resource.kind,
        display_name=resource.display_name or resource.native_id,
        matched_on=matched_on,
        label=label,
        value=value,
        zone=zone or _zone_of(resource),
    )


def _zone_of(resource: Resource) -> str:
    """Return the zone an applied enrichment placed ``resource`` in, or ``""``."""
    return str(resource.attributes.get(ZONE_ATTRIBUTE, "") or "")


def _host_of(raw: str) -> str:
    """Return the host inside a target, whatever the sender wrapped it in.

    A prober's target is a URL, an exporter's ``instance`` is ``host:port``, and
    a hostname is neither. All three arrive on the same labels, so all three are
    reduced here rather than at three call sites that would disagree.
    """
    candidate = raw.strip()
    if "://" in candidate:
        split = urlsplit(candidate)
        candidate = split.hostname or ""
    else:
        # A bare IPv6 address has colons of its own; only a bracketed one or a
        # single trailing colon is a port, and splitting on the last colon of
        # ``fe80::1`` would produce a host nothing matches.
        head, separator, tail = candidate.rpartition(":")
        if separator and tail.isdigit() and head.count(":") == 0:
            candidate = head
    return candidate.strip("[]").rstrip(".").lower()


def _address_of(host: str) -> IPv4Address | None:
    """Return ``host`` as an IPv4 address, or ``None`` when it is a name."""
    try:
        parsed = ip_address(host)
    except ValueError:
        return None
    return parsed if isinstance(parsed, IPv4Address) else None


@dataclass(frozen=True, slots=True)
class _EstateIndex:
    """The three lookups resolution needs, built once per call.

    Built rather than queried because the estate has no attribute filter and
    adding one would be a repository change for a read that is already bounded
    by the page the caller holds.
    """

    by_vmid_value: Mapping[str, Resource]
    by_address_value: Mapping[str, Resource]
    by_domain_value: Mapping[str, Resource]
    by_name_value: Mapping[str, Resource]
    #: Address to zone, for the resources that report both. What an unmatched
    #: address is placed by when no zone map is declared.
    placed: tuple[tuple[IPv4Address, str], ...]

    @classmethod
    def of(cls, resources: Sequence[Resource]) -> _EstateIndex:
        """Return the index ``resources`` supports.

        First writer wins on every lookup. Two resources reporting one address
        is a divergence the sweep already records, and picking the later one
        here would make which resource an alert resolves to depend on the order
        a query happened to return.
        """
        vmids: dict[str, Resource] = {}
        addresses: dict[str, Resource] = {}
        domains: dict[str, Resource] = {}
        names: dict[str, Resource] = {}
        placed: list[tuple[IPv4Address, str]] = []

        for resource in resources:
            attributes = dict(resource.attributes)
            vmid = str(attributes.get(VMID_ATTRIBUTE, "") or "")
            if vmid:
                vmids.setdefault(vmid, resource)
            address = str(attributes.get(ADDRESS_ATTRIBUTE, "") or "").split("/", 1)[0]
            parsed = _address_of(address.lower()) if address else None
            if parsed is not None:
                addresses.setdefault(str(parsed), resource)
                zone = _zone_of(resource)
                if zone:
                    placed.append((parsed, zone))
            domain = str(attributes.get(DOMAIN_ATTRIBUTE, "") or "").lower().rstrip(".")
            if domain:
                domains.setdefault(domain, resource)
            for name in (resource.display_name, resource.native_id):
                if name:
                    names.setdefault(name.lower(), resource)

        return cls(
            by_vmid_value=vmids,
            by_address_value=addresses,
            by_domain_value=domains,
            by_name_value=names,
            placed=tuple(placed),
        )

    def by_vmid(self, value: str) -> Resource | None:
        """Return the guest carrying this numeric identifier, or ``None``."""
        return self.by_vmid_value.get(value.strip())

    def by_address(self, value: str) -> Resource | None:
        """Return the resource reporting this address, or ``None``."""
        parsed = _address_of(value)
        return None if parsed is None else self.by_address_value.get(str(parsed))

    def by_domain(self, value: str) -> Resource | None:
        """Return the workload the declared inventory says answers this domain."""
        return self.by_domain_value.get(value)

    def by_name(self, value: str) -> Resource | None:
        """Return the resource of this name, or ``None``."""
        return self.by_name_value.get(value)

    def zone_near(self, address: IPv4Address) -> str:
        """Return the zone this address's neighbours sit in, or ``""``.

        One distinct answer or none. Two zones sharing a ``/24`` means the
        division is finer than the inference, and naming either of them would
        put a finding in a zone by coincidence — which is worse than a finding
        that does not name one.
        """
        network = ip_network(f"{address}/{ALERT_ZONE_INFERENCE_PREFIX}", strict=False)
        found = {zone for placed, zone in self.placed if placed in network}
        return found.pop() if len(found) == 1 else ""


__all__ = [
    "DOMAIN_ATTRIBUTE",
    "UNNAMED_TARGET",
    "UNRESOLVED_TARGET_PREFIX",
    "ZONE_ATTRIBUTE",
    "AlertMatch",
    "AlertResolution",
    "ResolvedTarget",
    "UnresolvedAlertTarget",
    "UnresolvedTargetFinding",
    "resolve_alert",
    "unresolved_targets",
]
