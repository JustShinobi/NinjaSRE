"""Searching what the team wrote down, once there is something to search on.

The second half of the recall discipline. Memory answers "has this happened
before"; this answers "did anybody write down what to do about it". Both are
searched on evidence rather than on the alert, and for the same reason: a search
run on alert text returns documents that share vocabulary with the alert, and a
runbook that merely mentions the same service is worse than no runbook at all.

The unavailability path is explicit. A knowledge tool that quietly returned
nothing would be indistinguishable from one that searched a corpus nobody has
written into, and an investigation would report "this team has no documented
procedure" on the strength of a store that was never configured.
"""

from __future__ import annotations

from capabilities.tools.system.knowledge_search import binding, results
from config.constants.knowledge import DEFAULT_KNOWLEDGE_SEARCH_RESULTS
from config.prompts.knowledge import KNOWLEDGE_UNCONFIGURED
from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.knowledge.base.search import KnowledgeQuery

TOOL_NAME = "search_knowledge_base"

_KNOWLEDGE_USE_CASES = (
    "find the runbook for a symptom you have already observed",
    "check whether a documented procedure exists before improvising one",
    "read the post-mortem of a previous incident with the same signature",
)

_KNOWLEDGE_ANTI_EXAMPLES = (
    "searching on the raw alert text before any symptom has been established",
    "looking up current system state, which a vendor tool reads directly",
    "treating a returned passage as an observation of this incident",
)


@tool(
    name=TOOL_NAME,
    display_name="Search the knowledge base",
    description=(
        "Search this team's runbooks, post-mortems, architecture notes, and operational "
        "procedures, and return the matching passages with the document and section "
        "they came from. Search on concrete symptoms you have observed — an error "
        "string, a failing check, an established boundary — not on the alert text. Cite "
        "what comes back rather than restating it: a runbook records what was true when "
        "somebody wrote it, and where it disagrees with what you have observed, what you "
        "observed wins."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.KNOWLEDGE_BASE,
    evidence_type=EvidenceType.DOCUMENT,
    # Reads the team's own documents and nothing else. Every document passed the
    # guardrail engine on the way in, so what comes back here has already been
    # through the boundary once.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("knowledge", "runbook", "documentation", "procedure"),
    use_cases=_KNOWLEDGE_USE_CASES,
    anti_examples=_KNOWLEDGE_ANTI_EXAMPLES,
)
async def search_knowledge_base(
    query: str,
    document_type: str = "",
    limit: int = DEFAULT_KNOWLEDGE_SEARCH_RESULTS,
) -> CapabilityResult:
    """Return citable passages, an empty search, or an explicit unavailability.

    Three outcomes, and the agent's next move differs for each. Passages are
    something to cite and check against what has been observed. An empty search
    means nobody has written about this failure, which is a finding about the
    team's documentation rather than about the incident. An unavailability means
    there was nowhere to look, and returning it as an empty search would teach
    the agent that the team has no runbooks when the truth is that nobody
    configured the store.
    """
    source = binding.current()
    if source is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            KNOWLEDGE_UNCONFIGURED,
            detail=f"searched for {query!r}, up to {limit} passage(s)",
        )

    result = await source.search(
        KnowledgeQuery(text=query, document_type=document_type, limit=limit)
    )
    if not result.searched:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            result.reason or KNOWLEDGE_UNCONFIGURED,
            detail=f"searched for {query!r}, up to {limit} passage(s)",
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value=results.shape(result),
        evidence=results.evidence_for(result),
    )
