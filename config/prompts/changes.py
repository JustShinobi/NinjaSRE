"""How a change is described to the model, and how the negative is stated.

Two things live here rather than beside the correlation, for the reason every
prompt does: the wording is what the model repeats into a report, and wording
that lives at a call site is wording nobody reviews.

The sentences are written to be *repeated*. A model shown "correlation:
window_only" writes "a change correlated with the incident"; a model shown "this
change shares a window with the incident and nothing connects it to this
resource — treat it as coincidence unless something else links them" writes
that. The strength labels are therefore whole clauses, not adjectives.

The negative is the one that earns its place. "No change touched this resource
in the last 24 hours" is what makes somebody stop looking at deploys and start
looking elsewhere, and it is only worth saying if it names what was consulted:
an absence from a source nobody configured is not evidence of anything.
"""

from __future__ import annotations

from typing import Final

# --- What each strength means, in words the report can carry ------------------

#: The strong link: the component that was applied is the one that built this
#: resource. Names the whole chain, because the chain is the evidence.
CHANGE_MANAGES_RESOURCE: Final[str] = (
    "{path} belongs to the {component} component, and {component} manages this resource. "
    "This change altered something that governs the resource under investigation."
)

#: The middle link: a shared declarative policy that names this resource or the
#: network it sits on. Real, and weaker than the first, and the sentence says so.
CHANGE_TOUCHES_SHARED_POLICY: Final[str] = (
    "{path} is shared policy that names {matched}, which this resource carries. The change "
    "did not alter the resource's own component, so this is a plausible link rather than a "
    "governing one."
)

#: The absence of a link, said as an absence. The word "coincidence" is
#: deliberate: it is what a reader has to conclude, and leaving them to conclude
#: it from a label like "window_only" is how a coincidence becomes a cause.
CHANGE_WINDOW_ONLY: Final[str] = (
    "This change happened in the same window and nothing connects it to this resource — no "
    "path it touched belongs to a component that manages the resource, and none names it. "
    "Treat it as a temporal coincidence unless other evidence links them."
)

#: Appended where the source could not say which files a change touched, so the
#: absence of a stronger link is not read as evidence that there is none.
CHANGE_PATHS_UNAVAILABLE: Final[str] = (
    " The source that reported this change does not list the files it touched, so a stronger "
    "link may exist and could not be checked."
)

# --- The two statements a report makes ----------------------------------------

#: What a report says when something did change. One sentence per correlated
#: change is the model's job; this is the frame it goes in.
CHANGES_FOUND: Final[str] = (
    "{count} change(s) landed in {window}, from {sources}. {strong} of them altered something "
    "that manages this resource."
)

#: The negative, first-class. Names the sources and the window, because "nothing
#: changed" from a deployment with no change source configured is not a finding.
NO_CHANGE_TOUCHED: Final[str] = (
    "No change touched {resource} in {window}. This was established by consulting {sources}, "
    "which reported {total} change(s) in that window, none of them linked to this resource. "
    "Changes are not the cause here."
)

#: The other negative, and it is a different statement: nothing changed at all,
#: anywhere, in the window.
NO_CHANGE_AT_ALL: Final[str] = (
    "No change of any kind landed in {window}. This was established by consulting {sources}. "
    "Changes are not the cause here."
)

#: What is said when there is nothing to consult. Not a negative claim — an
#: inability to make one, which is a different thing and leads somewhere else.
NO_CHANGE_SOURCE: Final[str] = (
    "No change source is configured for this deployment, so whether anything changed before "
    "this incident is unknown rather than answered. Point the platform at the repository that "
    "applies this cluster's state, or at the git host it lives on."
)

#: The guidance the agent is given about the capability, once, at run start. It
#: carries no change and no resource — the same rule topology and the knowledge
#: base follow.
CHANGES_GUIDANCE: Final[str] = (
    "Change history is available but is NOT loaded for you. Once you have identified the "
    "resource that is actually affected, ask what changed for it. The answer is correlated "
    "through the resource rather than by time: a change reported as managing the resource "
    "altered something that governs it, and a change reported as a temporal coincidence "
    "shares only a window and must not be presented as a cause. An empty answer is an "
    "answer — 'nothing changed here' is evidence, and it is worth stating in the report."
)


__all__ = [
    "CHANGES_FOUND",
    "CHANGES_GUIDANCE",
    "CHANGE_MANAGES_RESOURCE",
    "CHANGE_PATHS_UNAVAILABLE",
    "CHANGE_TOUCHES_SHARED_POLICY",
    "CHANGE_WINDOW_ONLY",
    "NO_CHANGE_AT_ALL",
    "NO_CHANGE_SOURCE",
    "NO_CHANGE_TOUCHED",
]
