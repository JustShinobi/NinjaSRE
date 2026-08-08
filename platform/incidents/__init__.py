"""Incidents: the noun a result attaches to, and the one lifecycle behind it.

An incident is what this platform concludes when something is wrong. Everything
downstream — the investigation, the decision to act, the remediation, the
report — hangs off one, so the shape of this package is decided by a single
claim: **there is exactly one kind of incident and exactly one way to raise
one.**

``lifecycle``
    The only place an ``Incident`` is constructed, asserted structurally by the
    architecture suite. A webhook alert, a detected condition, a failing
    detector, and a person opening one by hand all arrive here and differ in one
    field.

``correlation``
    Which findings are the same finding. The grouping key comes off the
    detector, where an operator can read it, rather than out of a heuristic.

``dispatch``
    Turning an incident into an investigation, under a per-team and a global
    rate limit, and never twice for one correlation.

``escalation``
    Following up on an incident nobody addressed, through the notification
    registry that already exists, and cancelling the moment it closes.

The alternative shape — an ``Alert`` from webhooks and an ``Incident`` from
detectors — means every component downstream handles two cases, and the second
one is the one nobody tests.
"""

from __future__ import annotations
