"""Turning an incident into an investigation, and refusing to start a hundred.

The objective is derived rather than written. An incident already knows what is
wrong, which resources it is about, and what evidence led there; asking an
operator to also type an objective would be asking them to restate it, and a
run started from a restatement investigates the restatement.
"""

from __future__ import annotations

from config.constants.observation import MAX_INCIDENT_SUBJECTS
from platform.persistence.ports.incident_store import Incident

#: Subjects named in an objective before it says "and N others". A prompt that
#: listed five hundred identifiers would spend its context on a list the model
#: cannot act on, and the incident carries all of them for anything that can.
MAX_NAMED_SUBJECTS = 8


def objective_for(incident: Incident) -> str:
    """Return the objective an investigation of ``incident`` is started with.

    Derived from the incident and its subjects, in the order an investigator
    needs them: what is wrong, what it is about, and what was seen. The
    identifiers are named rather than counted because they are what the first
    capability call will use.
    """
    named = incident.subject_ids[:MAX_NAMED_SUBJECTS]
    remaining = len(incident.subject_ids) - len(named)
    subjects = ", ".join(named)
    if remaining > 0:
        subjects = f"{subjects} and {remaining} other(s)"

    evidence = _leading_evidence(incident)
    parts = [
        f"{incident.title}: {incident.summary}".strip(": "),
        f"Affected: {subjects}." if subjects else "",
        f"Observed: {evidence}." if evidence else "",
        "Find the cause and say what evidence supports it.",
    ]
    return " ".join(part for part in parts if part)


def _leading_evidence(incident: Incident, limit: int = MAX_NAMED_SUBJECTS) -> str:
    """Return the first few observations, as ``name=value`` pairs.

    The first few rather than all of them, for the reason the subject list is
    truncated: an objective is a prompt, and a prompt made mostly of numbers is
    one the model reads past.
    """
    pairs: list[str] = []
    for subject in incident.subjects[:MAX_INCIDENT_SUBJECTS]:
        for name, value in subject.evidence.items():
            if name == "observed_at":
                continue
            pairs.append(f"{subject.resource_id} {name}={value}")
            if len(pairs) >= limit:
                return "; ".join(pairs)
    return "; ".join(pairs)


__all__ = ["MAX_NAMED_SUBJECTS", "objective_for"]
