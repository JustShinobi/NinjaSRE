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
"""

from __future__ import annotations

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
) -> IncidentRaise:
    """Return the raise this alert describes, in the same shape a detector's takes.

    Every field a detected incident has is filled from the alert, and none is
    left for a downstream component to special-case. That structural identity is
    what ``tests`` asserts, and what makes "there is one kind of incident" a
    property rather than an intention.
    """
    subjects = tuple(
        IncidentSubject(
            resource_id=component,
            detail=summary or description,
            evidence=_evidence(alert_name, reference),
        )
        for component in components
    ) or (
        IncidentSubject(
            resource_id=f"{UNNAMED_SUBJECT_PREFIX}:{source}",
            detail=summary or description or alert_name,
            evidence=_evidence(alert_name, reference),
        ),
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


def resolution_key(*, source: str, fingerprint: str) -> str:
    """Return the correlation key a resolution notification closes.

    The same key the firing alert opened under. A resolution that could not find
    its incident would leave one open for ever, and an operator who watched the
    upstream go green would be looking at a deployment that disagreed with it.
    """
    return correlation.for_alert(source=source, fingerprint=fingerprint)


def _evidence(alert_name: str, reference: str) -> dict[str, str]:
    """Return what the alert itself said, as the subject's evidence.

    Thin on purpose. The upstream already decided this was worth sending, and
    copying its whole payload in here would put an unbounded document on an
    incident that a console has to render.
    """
    evidence = {"alert": alert_name} if alert_name else {}
    if reference:
        evidence["reference"] = reference
    return evidence


__all__ = ["UNNAMED_SUBJECT_PREFIX", "raise_for_alert", "resolution_key"]
