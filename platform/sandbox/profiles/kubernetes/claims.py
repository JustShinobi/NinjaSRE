"""Binding one investigation to one instance, safely when replicas compete.

A claim answers a question with exactly one correct answer: *this* pod now
belongs to *that* investigation, and no other replica may hand it to a second
one. Getting it wrong is not a performance problem — it is two tenants sharing a
filesystem — so the mechanism is a compare-and-set on the pod's own annotations
rather than anything held in a process.

Three properties, and each is why the code is shaped the way it is.

**The cluster holds the claim, not the agent.** A replica that dies mid-claim
leaves the record where the next replica can read it. A claim held in memory
would be lost with the process, and the pod would be idle-looking and already
bound.

**A claim is single-tenant and re-checked at bind, not only at pool fill**
``bind`` refuses an instance whose organisation or team does not match
outright — not because the pool would normally offer one, but because "would
normally" is the assumption that a cross-tenant handover is made of.

**A lease bounds the claim, not just the sandbox.** An investigation that
crashed between claiming and running would otherwise hold a pod until the TTL.
The claim carries its own expiry, refreshed alongside the sandbox's, so a
half-claimed instance rejoins the pool in seconds rather than minutes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.security import (
    SANDBOX_INVESTIGATION_LABEL,
    SANDBOX_LEASE_EXPIRES_AT_ANNOTATION,
    SANDBOX_LEASE_HOLDER_ANNOTATION,
    SANDBOX_ORG_LABEL,
    SANDBOX_STATE_LABEL,
    SANDBOX_TEAM_LABEL,
)
from platform.sandbox.port import SandboxState
from platform.sandbox.profiles.kubernetes import ttl
from platform.sandbox.profiles.kubernetes.engine import KubernetesApi
from platform.sandbox.spec import SandboxSpec


@dataclass(frozen=True, slots=True)
class Claim:
    """One investigation's hold on one instance, as the cluster records it."""

    pod: str
    org_id: str
    team_id: str
    investigation_id: str
    holder: str
    expires_at: datetime

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return whether this claim has lapsed and the instance may be taken back."""
        at = now if now is not None else datetime.now(UTC)
        return at >= self.expires_at


def claim_of(pod: Mapping[str, Any]) -> Claim | None:
    """Return the claim recorded on ``pod``, or ``None`` if it is unclaimed."""
    metadata = pod.get("metadata")
    if not isinstance(metadata, dict):
        return None
    labels = metadata.get("labels") or {}
    annotations = metadata.get("annotations") or {}
    if not isinstance(labels, dict) or not isinstance(annotations, dict):
        return None

    holder = annotations.get(SANDBOX_LEASE_HOLDER_ANNOTATION)
    expires = annotations.get(SANDBOX_LEASE_EXPIRES_AT_ANNOTATION)
    if not holder or not isinstance(expires, str):
        return None
    parsed = ttl.parse(expires)
    if parsed is None:
        return None
    return Claim(
        pod=str(metadata.get("name", "")),
        org_id=str(labels.get(SANDBOX_ORG_LABEL, "")),
        team_id=str(labels.get(SANDBOX_TEAM_LABEL, "")),
        investigation_id=str(labels.get(SANDBOX_INVESTIGATION_LABEL, "")),
        holder=str(holder),
        expires_at=parsed,
    )


def is_claimable(pod: Mapping[str, Any], spec: SandboxSpec, *, now: datetime) -> bool:
    """Return whether ``spec``'s investigation may take ``pod``.

    Three conditions, and the tenancy one is not an optimisation. An instance
    that ever held another organisation's work is not offered to this one, full
    stop — there is no reset that makes reuse across tenants acceptable, because
    the thing being reset is the one that would have to be trusted.
    """
    metadata = pod.get("metadata")
    if not isinstance(metadata, dict):
        return False
    labels = metadata.get("labels") or {}
    if not isinstance(labels, dict):
        return False

    if ttl.is_expired(metadata, now=now):
        return False
    if labels.get(SANDBOX_ORG_LABEL) not in (None, "", spec.org_id):
        return False
    if labels.get(SANDBOX_TEAM_LABEL) not in (None, "", spec.team_id):
        return False

    existing = claim_of(pod)
    return existing is None or existing.is_expired(now=now)


async def bind(
    api: KubernetesApi,
    pod: str,
    spec: SandboxSpec,
    *,
    holder: str,
    lease_seconds: float,
    now: datetime | None = None,
) -> Claim | None:
    """Bind ``pod`` to ``spec``'s investigation, or return ``None`` if somebody else did.

    The compare-and-set is against the *absence* of a live holder. Two replicas
    reaching this line with the same pod produce one ``Claim`` and one ``None``,
    which is the property the whole warm pool rests on — and it is a property of
    the cluster's write semantics rather than of any lock this process holds.
    """
    at = now if now is not None else datetime.now(UTC)
    current = await api.get_pod(pod)
    if current is None or not is_claimable(current, spec, now=at):
        return None

    metadata = current.get("metadata", {})
    annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
    existing_holder = annotations.get(SANDBOX_LEASE_HOLDER_ANNOTATION)

    expires_at = at + timedelta(seconds=lease_seconds)
    landed = await api.compare_and_set_annotations(
        pod,
        expected={SANDBOX_LEASE_HOLDER_ANNOTATION: existing_holder},
        annotations={
            SANDBOX_LEASE_HOLDER_ANNOTATION: holder,
            SANDBOX_LEASE_EXPIRES_AT_ANNOTATION: ttl.render(expires_at),
        },
        labels={
            SANDBOX_ORG_LABEL: spec.org_id,
            SANDBOX_TEAM_LABEL: spec.team_id,
            SANDBOX_INVESTIGATION_LABEL: spec.investigation_id,
            SANDBOX_STATE_LABEL: str(SandboxState.CLAIMED),
        },
    )
    if not landed:
        return None
    return Claim(
        pod=pod,
        org_id=spec.org_id,
        team_id=spec.team_id,
        investigation_id=spec.investigation_id,
        holder=holder,
        expires_at=expires_at,
    )


async def renew(
    api: KubernetesApi,
    claim: Claim,
    *,
    lease_seconds: float,
    now: datetime | None = None,
) -> Claim | None:
    """Extend ``claim``, or return ``None`` if this holder no longer owns it.

    Renewal is conditional on still being the holder. A replica that was
    partitioned long enough for its lease to lapse and the pod to be re-claimed
    must find out here, not by continuing to execute into somebody else's
    sandbox.
    """
    at = now if now is not None else datetime.now(UTC)
    expires_at = at + timedelta(seconds=lease_seconds)
    landed = await api.compare_and_set_annotations(
        claim.pod,
        expected={SANDBOX_LEASE_HOLDER_ANNOTATION: claim.holder},
        annotations={
            SANDBOX_LEASE_HOLDER_ANNOTATION: claim.holder,
            SANDBOX_LEASE_EXPIRES_AT_ANNOTATION: ttl.render(expires_at),
        },
    )
    if not landed:
        return None
    return Claim(
        pod=claim.pod,
        org_id=claim.org_id,
        team_id=claim.team_id,
        investigation_id=claim.investigation_id,
        holder=claim.holder,
        expires_at=expires_at,
    )


__all__ = [
    "Claim",
    "bind",
    "claim_of",
    "is_claimable",
    "renew",
]
