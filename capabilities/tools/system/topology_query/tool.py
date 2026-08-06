"""Asking the graph what a service depends on, and what depends on it.

The capability the root prompt's guidance points at, and the timing is the whole
of its value. Called on the alert, it returns the neighbours of whichever service
the alert happened to name. Called once the agent has established which service
is actually affected, it answers the two questions an investigation cannot answer
from naming conventions: where the cause can be, and who is affected.

The unavailability path is explicit and stays that way. A topology tool that
quietly returned nothing would be indistinguishable from one that answered and
found nothing recorded, and an investigation would report "no downstream impact"
on the strength of a graph extension nobody installed.
"""

from __future__ import annotations

from capabilities.tools.system.topology_query import binding, results
from config.constants.persistence import DEFAULT_GRAPH_DEPTH
from config.prompts.knowledge import TOPOLOGY_UNCONFIGURED
from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.knowledge.clock import now

TOOL_NAME = "query_service_topology"

_TOPOLOGY_USE_CASES = (
    "find what an affected service depends on, to narrow where the cause can be",
    "establish the blast radius of an outage before writing an impact statement",
    "check whether two services are connected at all before assuming they are",
)

_TOPOLOGY_ANTI_EXAMPLES = (
    "querying on the alert text before an affected service has been identified",
    "reading current health or state, which a vendor tool reads directly",
    "guessing dependencies from service names when the graph has no record",
)


@tool(
    name=TOOL_NAME,
    display_name="Query service topology",
    description=(
        "Return what a service depends on, what depends on it, and the blast radius of "
        "an outage at it, from the team's topology graph. Dependencies narrow where the "
        "cause can be; dependents are the impact statement. Each result carries when it "
        "was last verified, and an unverified dependency is a lead to confirm rather "
        "than a fact. Call this once you have identified an affected service — not on "
        "the alert text."
    ),
    domain="topology",
    evidence_source=EvidenceSource.KNOWLEDGE_BASE,
    evidence_type=EvidenceType.TOPOLOGY,
    # Reads the team's own topology graph and nothing else. No traversal here
    # accepts a query string, so there is nothing for a generated query to reach.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=("topology", "dependencies", "blast-radius", "impact"),
    use_cases=_TOPOLOGY_USE_CASES,
    anti_examples=_TOPOLOGY_ANTI_EXAMPLES,
)
async def query_service_topology(
    service: str,
    depth: int = DEFAULT_GRAPH_DEPTH,
) -> CapabilityResult:
    """Return the graph's record for a service, an empty answer, or an unavailability.

    Three outcomes, because the next move differs for each. A populated answer
    narrows the investigation and scopes the impact. An empty answer is a gap in
    the topology data — the investigation continues, and the absence is not
    evidence that the service stands alone. An unavailability means there was
    nowhere to look, and returning it as an empty answer would teach the agent
    that a service has no dependents when the truth is that nobody configured the
    graph.
    """
    source = binding.current()
    if source is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            TOPOLOGY_UNCONFIGURED,
            detail=f"asked about {service!r} to depth {depth}",
        )

    answer = await source.query(service, depth=depth)
    if not answer.searched:
        # Switched off for this team, or the graph could not be reached. Either
        # way the traversal did not happen, and saying "nothing recorded" would
        # be a claim about the estate that nobody checked.
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            answer.reason or TOPOLOGY_UNCONFIGURED,
            detail=f"asked about {service!r} to depth {depth}",
        )

    moment = now()
    return CapabilityResult.ok(
        TOOL_NAME,
        value=results.shape(answer, moment=moment),
        evidence=results.evidence_for(answer),
        truncated=answer.truncated,
    )
