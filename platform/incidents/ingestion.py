"""An alert somebody else raised, arriving as an incident of ours.

This is the whole of the plan's unification. A webhook alert does not become an
``Alert``; it becomes an ``IncidentRaise`` and goes through the same lifecycle a
detected condition does. Everything downstream — the console, the dispatcher,
the escalation registry, the report — therefore handles one kind of thing.

Two translations happen here and both are deliberate.

**The upstream's fingerprint is the correlation key.** Re-deriving one from the
payload would mean this deployment disagreeing with the system that sent the
alert about which alerts are the same alert — and the upstream is the one that
will eventually send the resolution.

**The alert's components become subjects.** An alert that names no component
still gets one subject, the alert itself, because an incident with nothing to
point at is unrepresentable and an alert about "the checkout service" with the
service unnamed is still a real alert. Naming the source rather than inventing a
resource is honest: it says what we actually know.

A *resolved* notification is not an incident. It is the strongest evidence
available that an incident ended, and ``resolution_of`` is how the router asks
which one.

**A resolved alert's subject is the estate resource, not the label value.** When
the caller has resolved the alert against the estate, the incident points at the
resource identifier everything else is keyed by — so the resource's own page
shows the incident, and an investigation of it starts on the right machine. When
the target resolved to nothing, the finding becomes a subject of its own rather
than being dropped: an alert for something this estate does not hold is
information about the estate.
"""

from __future__ import annotations

from config.constants.observation import MAX_INCIDENT_SUBJECTS
from platform.estate.alert_resolution import AlertResolution
from platform.incidents import correlation
from platform.incidents.lifecycle import IncidentRaise
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject

#: What an alert's subject is called when the alert names no component. The
#: source rather than a placeholder, because "prometheus" is a true statement
#: about what we know and "unknown" is not.
UNNAMED_SUBJECT_PREFIX = "alert"


def raise_for_alert(
    *,
    source: str,
    fingerprint: str,
    alert_name: str,
    summary: str,
    description: str,
    severity: str,
    components: tuple[str, ...],
    team_node_id: str,
    reference: str = "",
    actor: str = "system:webhook",
    resolution: AlertResolution | None = None,
    group_key: str = "",
) -> IncidentRaise:
    """Return the raise this alert describes, in the same shape a detector's takes.

    Every field a detected incident has is filled from the alert, and none is
    left for a downstream component to special-case. That structural identity is
    what ``tests`` asserts, and what makes "there is one kind of incident" a
    property rather than an intention.

    ``resolution`` is what the caller resolved the alert's labels to against the
    estate. Optional, because a caller that holds no estate is not wrong to
    raise an incident — it just raises one whose subjects are the components the
    alert named, which is what this did before resolution existed.
    """
    subjects = _subjects(
        source=source,
        alert_name=alert_name,
        summary=summary,
        description=description,
        components=components,
        reference=reference,
        resolution=resolution,
        group_key=group_key,
    )

    return IncidentRaise(
        correlation_key=correlation.for_alert(source=source, fingerprint=fingerprint),
        title=alert_name or summary or f"an alert from {source}",
        summary=summary or description or alert_name,
        origin=IncidentOrigin.ALERT,
        origin_id=source,
        severity=severity,
        subjects=subjects,
        team_node_id=team_node_id,
        actor=actor,
        cause=description or summary or alert_name,
    )


def _subjects(
    *,
    source: str,
    alert_name: str,
    summary: str,
    description: str,
    components: tuple[str, ...],
    reference: str,
    resolution: AlertResolution | None,
    group_key: str,
) -> tuple[IncidentSubject, ...]:
    """Return what this incident is about, in the terms the estate is keyed by.

    Three cases, in order of how much is known. A resolved alert is about one
    resource and says so, and the component names it also carried are already in
    the objective and in the alert record — repeating them as subjects would put
    a label value beside a resource identifier in a list a screen renders as one
    kind of thing.

    An unresolved target leads the list rather than trailing it, because the
    list is bounded: an alert naming ``MAX_INCIDENT_SUBJECTS`` components would
    otherwise push the finding off the end, and losing it is exactly the
    behaviour the finding exists to replace.
    """
    evidence = _evidence(alert_name, reference, group_key)
    detail = summary or description

    if resolution is not None and resolution.resolved is not None:
        target = resolution.resolved
        return (
            IncidentSubject(
                resource_id=target.resource_id,
                detail=detail or alert_name,
                evidence={**evidence, **target.evidence()},
            ),
        )

    named = tuple(
        IncidentSubject(resource_id=component, detail=detail, evidence=evidence)
        for component in components
    )

    if resolution is not None and resolution.unresolved is not None:
        finding = resolution.unresolved
        named = (
            IncidentSubject(
                resource_id=finding.subject_id,
                detail=finding.why,
                evidence={**evidence, **finding.evidence()},
            ),
            *named,
        )

    if not named:
        return (
            IncidentSubject(
                resource_id=f"{UNNAMED_SUBJECT_PREFIX}:{source}",
                detail=detail or alert_name,
                evidence=evidence,
            ),
        )
    return named[:MAX_INCIDENT_SUBJECTS]


def resolution_key(*, source: str, fingerprint: str) -> str:
    """Return the correlation key a resolution notification closes.

    The same key the firing alert opened under. A resolution that could not find
    its incident would leave one open for ever, and an operator who watched the
    upstream go green would be looking at a deployment that disagreed with it.
    """
    return correlation.for_alert(source=source, fingerprint=fingerprint)


def _evidence(alert_name: str, reference: str, group_key: str = "") -> dict[str, str]:
    """Return what the alert itself said, as the subject's evidence.

    Thin on purpose. The upstream already decided this was worth sending, and
    copying its whole payload in here would put an unbounded document on an
    incident that a console has to render.

    The group is the exception worth carrying: it is what the sender called the
    set of notifications this one belongs to, and an operator asking why eight
    pages became one incident is asking about exactly that string.
    """
    evidence = {"alert": alert_name} if alert_name else {}
    if reference:
        evidence["reference"] = reference
    if group_key:
        evidence["group"] = group_key
    return evidence


__all__ = ["UNNAMED_SUBJECT_PREFIX", "raise_for_alert", "resolution_key"]
