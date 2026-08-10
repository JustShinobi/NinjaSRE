"""Turning a change answer into something a report can quote and a console can draw.

Three decisions here, and each one is a way the answer could arrive true and be
read wrongly.

**Every row carries its strength as a clause, not a label.** A model shown
``strength: window_only`` writes "a change correlated with the incident". Shown
the sentence the correlation produced, it writes what the sentence says. The
label is in the structured half for the console to filter on; the text half is
what the model reads.

**The negative is an evidence entry.** A quiet resource produces one observation
saying what was consulted, over what window, and how many changes were in it —
because "no change touched this" is a finding, and a finding with no citation is
an assertion. This is the entry the whole feature is for: it is what makes
somebody stop looking at deploys.

**The evidence cites the change, not the repository.** One entry per correlated
change, referenced by identifier, so a conclusion that names a deploy can be
followed back to the apply that is being blamed.
"""

from __future__ import annotations

from typing import Any

from config.constants.changes import CHANGE_REFERENCE_PREFIX, CHANGES_TOOL_NAME
from core.capability.metadata import EvidenceType
from core.capability.result import Evidence
from platform.changes.correlation import CorrelatedChange
from platform.changes.service import ChangeAnswer

#: What the evidence entries name as their source. Not a vendor: the claim is
#: made from the change history, whichever sources answered, and each entry says
#: which one in its own summary.
CHANGE_EVIDENCE_SOURCE = "change_history"


def describe(entry: CorrelatedChange) -> str:
    """Return one correlated change as the model is shown it."""
    change = entry.change
    verb = "applied" if change.applied else "committed and never applied"
    return (
        f"{change.change_id} — {change.message or 'no message'} — "
        f"{change.author or 'unknown author'}, {verb} {change.instant.isoformat()}"
        f"{f' via the {change.component} component' if change.component else ''}. "
        f"{entry.why}"
    )


def render(answer: ChangeAnswer) -> str:
    """Return the whole answer as one block of text, the negative included."""
    lines = [answer.statement]
    lines.extend(describe(entry) for entry in answer.changes)
    if answer.truncated:
        lines.append(
            "More changes matched than were read, so this is a lower bound on what landed in "
            "the window."
        )
    lines.extend(
        f"{degradation} — so 'nothing changed' cannot be concluded from this answer."
        for degradation in answer.degraded
    )
    return "\n".join(lines)


def evidence_for(answer: ChangeAnswer) -> tuple[Evidence, ...]:
    """Return the negative when nothing was linked, then one entry per change.

    The negative comes first and comes *whenever nothing reached the resource* —
    not only when the window was empty. A window holding four unrelated changes
    is exactly the case where an investigation needs to be told, in one
    sentence, that none of them touched this: leaving it to be inferred from
    four coincidence labels is how one of them becomes the cause.

    An investigation that established "nothing changed here" learned something,
    and an observation that never entered the trace did not happen.
    """
    negative: tuple[Evidence, ...] = ()
    if not answer.linked:
        negative = (
            Evidence(
                source=CHANGE_EVIDENCE_SOURCE,
                evidence_type=EvidenceType.CHANGE,
                summary=answer.statement,
                reference=f"{CHANGE_REFERENCE_PREFIX}:none:{answer.resource.resource_id}",
            ),
        )

    return negative + tuple(
        Evidence(
            source=CHANGE_EVIDENCE_SOURCE,
            evidence_type=EvidenceType.CHANGE,
            summary=describe(entry),
            reference=f"{CHANGE_REFERENCE_PREFIX}:{entry.change.change_id}",
        )
        for entry in answer.changes
    )


def shape(answer: ChangeAnswer) -> dict[str, Any]:
    """Return the structured value the tool hands back.

    Both a rendered block and the structured answer. The text is what the model
    reads; the structure is what the trace, the console timeline and the
    evaluation harness read, and deriving one from the other afterwards is how
    the two come to disagree.
    """
    return {**answer.to_record(), "text": render(answer), "tool": CHANGES_TOOL_NAME}


__all__ = ["CHANGE_EVIDENCE_SOURCE", "describe", "evidence_for", "render", "shape"]
