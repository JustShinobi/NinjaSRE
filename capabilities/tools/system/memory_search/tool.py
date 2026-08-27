"""Recall of previous investigations, with the store behind it.

The name is unchanged from the declaration that stood here before there was
anything to search. That is deliberate: the investigation skill directs this tool
by name and tells the agent *when* in the five phases to reach for it, and
renaming it would have silently detached the methodology from the capability it
is methodology about.

What changed is that it now searches, and that the two optional arguments are
*signals* rather than filters. A caller that names a component or a class of
failure says which episodes it would rather read first; it never says which
episodes exist. That distinction was measured rather than reasoned about: an
investigation searching for ``ProxmoxGuestStopped`` on ``pve-exporter`` returned
nothing from a corpus holding the episode about its own incident, written
forty-four seconds earlier by a run that had called the same failure
``manual_shutdown`` on ``service:redis``. Both filters excluded it. Neither run
was wrong; nothing made them agree.

``issue_type`` is now drawn from a closed vocabulary — the same
``IssueType`` the extractor writes episodes under, so that the agent searching
and the agent that recorded are choosing from one list rather than each
inventing a word. Anything outside the list is still accepted and classified
into it, because a schema enum is a request most providers do not enforce.

The unavailability path is kept and is still explicit. A recall tool that quietly
returned nothing would be indistinguishable from one that searched and found
nothing, and an investigation would conclude "no similar incidents" on the
strength of a store that was never configured.
"""

from __future__ import annotations

from capabilities.tools.system.memory_search import binding, results
from config.constants.memory import DEFAULT_MEMORY_RECALL_RESULTS
from config.prompts.memory import MEMORY_UNCONFIGURED
from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.memory.models import IssueType, RecallQuery

TOOL_NAME = "recall_similar_incidents"

#: The arguments the model sees, declared rather than derived from the
#: signature, so ``issue_type`` can carry the vocabulary as an enum. A prose
#: description of the same list would be a second copy of it, and a second copy
#: is how the two ends came to disagree in the first place.
_RECALL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Evidence you have gathered — an error string, an exit code, a failing "
                "component. Not the alert text."
            ),
        },
        "component": {
            "type": "string",
            "description": (
                "The system you believe is failing, as 'type:name' or a bare name. "
                "Episodes touching it rank first; nothing is excluded, so a component "
                "an earlier run recorded under another name is still returned."
            ),
        },
        "issue_type": {
            "type": "string",
            "enum": [member.value for member in IssueType],
            "description": (
                "The class of failure you believe this is. Episodes filed under it "
                "rank first; nothing is excluded, so a guess costs you nothing."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "How many episodes to return at most.",
        },
    },
    "required": ["query"],
}

_RECALL_USE_CASES = (
    "find previous incidents with the same symptom on the same service",
    "check whether this alert has fired before and what resolved it",
    "recall which investigation strategy worked on this class of failure",
)

_RECALL_ANTI_EXAMPLES = (
    "looking up current system state, which a vendor tool reads directly",
    "searching on the raw alert text before any evidence has been gathered",
)


@tool(
    name=TOOL_NAME,
    display_name="Recall similar incidents",
    description=(
        "Search previous investigations for incidents resembling this one, and return "
        "what was concluded, what the cause turned out to be, and which capabilities "
        "found it. Where enough similar incidents exist, a synthesised playbook is "
        "returned alongside them — common causes, an effective investigation order, "
        "and approaches that previously led nowhere. Search on evidence you have "
        "gathered — an error string, an exit code, a failing component — not on the "
        "alert text. Naming a component or an issue type ranks those episodes "
        "first and excludes nothing, so name what you believe even when you are "
        "not sure of it."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.MEMORY,
    evidence_type=EvidenceType.INCIDENT,
    # Reads the team's own past investigations and nothing else. Episodes are
    # scanned by the guardrail engine on the way in, so what comes back here has
    # already been through the boundary once.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("memory", "recall", "history"),
    use_cases=_RECALL_USE_CASES,
    anti_examples=_RECALL_ANTI_EXAMPLES,
    input_schema=_RECALL_INPUT_SCHEMA,
)
async def recall_similar_incidents(
    query: str,
    component: str = "",
    issue_type: str = "",
    limit: int = DEFAULT_MEMORY_RECALL_RESULTS,
) -> CapabilityResult:
    """Return ranked past episodes, an empty search, or an explicit unavailability.

    ``component`` and ``issue_type`` are passed through verbatim. Classifying
    here would leave the trace holding the bucket and not the words, and "what
    did the agent actually search for" is the first question a surprising recall
    gets asked; the retriever canonicalises for comparison and records both.

    Three outcomes, and they are three because the agent's next move differs for
    each. Episodes are a lead to check. An empty search means this failure is new
    to the team, which is a finding. An unavailability means there was nowhere to
    look, which is not a finding at all — and returning it as an empty search
    would teach the agent that the team has no history when the truth is that
    nobody configured memory.
    """
    source = binding.current()
    if source is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            MEMORY_UNCONFIGURED,
            detail=f"searched for {query!r}, up to {limit} result(s)",
        )

    result = await source.search(
        RecallQuery(text=query, component=component, issue_type=issue_type, limit=limit)
    )
    if not result.searched:
        # Switched off for this team, or the store could not be reached. Either
        # way the search did not happen, and saying "nothing found" would be a
        # claim about the corpus that nobody checked.
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            result.reason or MEMORY_UNCONFIGURED,
            detail=f"searched for {query!r}, up to {limit} result(s)",
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value=results.shape(result),
        evidence=(
            *results.evidence_for(result.episodes),
            *results.strategy_evidence(result.strategies),
        ),
    )
