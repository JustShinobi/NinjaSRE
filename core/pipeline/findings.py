"""One line per stage, saying what that stage established.

A trace grouped by stage is worth more than a flat list of turns only if the
groups say something. Four of the six stages produce no turn at all — resolving
reads a catalogue, planning ranks it, intake and diagnosis each make a model
call of their own and hand back a value — so without a line they would be
headings over nothing, and a heading over nothing is a worse reading of a run
than the numbered list it replaced.

**Every line is read out of the slice the stage just wrote.** Nothing here asks
a model to summarise anything and nothing paraphrases the report: a stage that
established a countable fact says the count, and the one stage that already
writes a sentence about its own outcome hands that sentence over unchanged.
That is the difference between a finding and a caption — a caption would be a
second account of the run, free to disagree with the first.

**A stage that established nothing says nothing.** Empty, and the surface
prints the stage with no line rather than a filler sentence, because "the
deployment recorded no finding here" is a fact and an invented sentence is not.

A ``match`` over the stage name rather than a method on each stage. The six are
a closed set — the enum is closed, ``STAGE_ORDER`` is final, and the lifecycle
refuses a pipeline built out of order — so the exhaustiveness a protocol would
buy is already guaranteed one level up, and keeping the six lines in one file
is what makes them readable as a set. They are read together far more often
than any one of them is read alone.
"""

from __future__ import annotations

from core.state.agent_state import AgentState
from core.state.types import OutcomeKind, StageName


def finding_for(stage: StageName, state: AgentState) -> str:
    """Return the one line ``stage`` established, in the state it produced.

    ``state`` is the state *after* the stage merged its updates. Reading the
    state before would report what the previous stage left behind, which for
    every stage but the first is a sentence about somebody else's work.
    """
    match stage:
        case StageName.RESOLVE_INTEGRATIONS:
            return _resolved(state)
        case StageName.INTAKE:
            return _taken_in(state)
        case StageName.PLAN_EVIDENCE:
            return _planned(state)
        case StageName.GATHER_EVIDENCE:
            return _gathered(state)
        case StageName.DIAGNOSE:
            return _diagnosed(state)
        case StageName.DELIVER:
            return _delivered(state)


def _resolved(state: AgentState) -> str:
    """Return what the team can actually call, as the resolving stage found it."""
    available = state.investigation.catalogue.available
    if not available:
        return "No capability on this team can serve this alert"
    return f"{_plural(len(available), 'capability', 'capabilities')} available on this team"


def _taken_in(state: AgentState) -> str:
    """Return intake's verdict: a repeat, noise, or something new.

    The link is checked before the classification because a burst joined onto an
    open incident was still classified an incident — reporting only the
    classification would say "a new incident" about the third alert of a
    firing that has been open for an hour.
    """
    classification = state.investigation.classification
    if classification is None:
        return ""
    link = state.investigation.link
    if link is not None:
        return f"Attached to incident {link.incident_id}, already open"
    if not classification.is_incident:
        return f"Not an incident: {classification.reason}" if classification.reason else ""
    return "A new incident, not a repeat of one already open"


def _planned(state: AgentState) -> str:
    """Return how far the plan narrowed the catalogue."""
    shortlisted = len(state.investigation.plan.actions)
    if shortlisted == 0:
        return ""
    return f"{_plural(shortlisted, 'capability', 'capabilities')} shortlisted, best first"


def _gathered(state: AgentState) -> str:
    """Return what the loop came back with, counted rather than paraphrased.

    Never a sentence cut out of the conclusion. The conclusion is a Markdown
    document that opens on a heading, and the run's own one-line summary of it
    is already the headline the surface shows above everything else — a stage
    line lifted from either would be that headline a second time.
    """
    outcome = state.investigation.outcome
    if outcome is not None and outcome.kind is OutcomeKind.FAILED:
        return outcome.headline
    held = len(state.evidence)
    if held == 0:
        return "" if not state.investigation.conclusion else "No observation was gathered"
    return f"{_plural(held, 'observation', 'observations')} gathered"


def _diagnosed(state: AgentState) -> str:
    """Return how much of the diagnosis the run's own evidence stands behind."""
    diagnosis = state.investigation.diagnosis
    if diagnosis is None:
        return ""
    total = len(diagnosis.claims)
    if total == 0:
        return "No claim was made"
    backed = len(diagnosis.validated_claims)
    return f"{backed} of {total} claims tied to an observation the run holds"


def _delivered(state: AgentState) -> str:
    """Return where the report went, in the words the delivering stage wrote.

    Read rather than composed. ``DeliverStage`` already writes one sentence
    naming every destination that accepted the report and every one that did
    not, onto the outcome it ends the run with; a second sentence written here
    would be a second answer to a question that has a writer.
    """
    outcome = state.investigation.outcome
    if outcome is None or state.investigation.delivery is None:
        return ""
    return outcome.detail


def _plural(count: int, singular: str, plural: str) -> str:
    """Return ``count`` with the right noun after it."""
    return f"{count} {singular if count == 1 else plural}"


__all__ = ["finding_for"]
