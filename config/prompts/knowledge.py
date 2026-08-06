"""What the agent is told about topology and the knowledge base, and when.

The same decision episodic memory made, made twice more: the prompt gets
*guidance* and never *content*. Nothing about a service's dependencies and
nothing from a runbook enters the opening prompt.

The reason differs slightly between the two stores, and both are worth writing
down because they are what the guidance has to convey.

**Topology, pre-injected, is a map of the wrong territory.** An alert names one
service; the graph around it names twenty. Handed those before it has looked at
anything, an agent explains the failure with whichever neighbour sounds most
plausible. Asked *after* an affected service is established, the same graph
answers two specific questions — what could have caused this, and who is
affected — and both of those change what the investigation does next.

**A runbook, pre-injected, is an instruction.** A runbook retrieved on the alert
text is retrieved on vocabulary; retrieved on a symptom the agent has actually
observed, it is retrieved on the failure. The difference between those two is
the difference between a procedure that applies and one that merely mentions the
same service.

Both guidance paragraphs therefore say the same three things in their own terms:
when to ask, what to ask with, and that an empty answer is an answer.
"""

from __future__ import annotations

from typing import Final

# --- Topology ----------------------------------------------------------------

#: Appended to the root system prompt at ``on_run_start`` when topology is
#: enabled. It carries no service, no dependency, and no blast radius, and a test
#: asserts that.
TOPOLOGY_GUIDANCE: Final[str] = (
    "Service topology is available but is NOT loaded for you. Once you have identified "
    "an affected service, deployment, or datastore, query topology for it. Two answers "
    "come back and they are used differently: what the service depends on narrows where "
    "the cause can be, and what depends on the service is the impact statement — the "
    "blast radius — which you should never infer from naming conventions.\n\n"
    "Each dependency carries the date it was last verified. Treat an unverified or stale "
    "edge as a lead to confirm rather than as a fact, and say so if you rely on one. An "
    "empty result means the graph has nothing recorded for that service, which is a gap "
    "in the topology data and not evidence that the service stands alone."
)

#: What the capability returns when the deployment has no graph configured.
#: Deliberately distinguishable from an empty result: "nothing recorded" and
#: "nowhere to look" lead to different next moves.
TOPOLOGY_UNCONFIGURED: Final[str] = (
    "Service topology is not configured for this deployment. Continue the investigation "
    "without it, and do not treat the absence of dependencies as evidence that this "
    "service has none."
)

#: What it returns when an operator has switched topology off for the team.
TOPOLOGY_DISABLED: Final[str] = (
    "Service topology is switched off for this team, so no dependency or blast-radius "
    "information was consulted. Continue without it."
)

#: What it returns when the graph exists but storage cannot answer right now
#: (Article's degradation path: the investigation continues, visibly degraded).
TOPOLOGY_UNAVAILABLE: Final[str] = (
    "Service topology could not be reached ({reason}). The investigation continues "
    "without dependency or blast-radius information; this is a gap in what you know, "
    "not a finding about the service."
)

#: What it returns when the graph answered and holds nothing for the service.
TOPOLOGY_EMPTY: Final[str] = (
    "The topology graph has nothing recorded for {service}. That is a gap in the "
    "topology data rather than evidence that the service has no dependencies or "
    "dependents. Continue without it."
)

#: The header of a topology answer. Says how the traversal was bounded, so a
#: partial answer is never read as a complete one.
TOPOLOGY_HEADER: Final[str] = (
    "Topology for {service}, traversed to depth {depth}. {dependencies} dependency(ies) "
    "and {dependents} dependent(s) within that bound."
)

#: Appended when a bound cut the answer short (FR-004). Its own sentence, because
#: an operator scanning the result has to be able to see it without reading the
#: node list.
TOPOLOGY_TRUNCATED: Final[str] = (
    "This answer is PARTIAL: the result bound was reached, so services beyond it are "
    "not listed. Treat the impact statement as a lower bound."
)

#: One dependency or dependent, as the agent is shown it.
TOPOLOGY_EDGE: Final[str] = "    - {name} ({kind}) — {relation}, last verified {verified}"

#: The suffix on an edge nobody has re-verified inside the staleness window.
TOPOLOGY_EDGE_STALE: Final[str] = " [UNVERIFIED — confirm before relying on it]"

# --- Knowledge base ----------------------------------------------------------

#: Appended to the root system prompt at ``on_run_start`` when the knowledge base
#: is enabled. No document content, and a test asserts that.
KNOWLEDGE_GUIDANCE: Final[str] = (
    "This team keeps runbooks, post-mortems, architecture notes, and operational "
    "procedures in a searchable knowledge base. It is NOT loaded for you. Search it once "
    "you have concrete symptoms — an error string, a failing check, an established "
    "boundary — and search on those symptoms rather than on the alert text.\n\n"
    "Results come back as passages with the document and section they came from. Cite "
    "them: name the document and quote the passage rather than paraphrasing it as your "
    "own conclusion. A runbook describes what was true when somebody wrote it, so where "
    "it disagrees with what you have observed in this incident, what you observed wins "
    "and the disagreement is worth reporting. An empty result is a normal outcome and "
    "means this team has not written anything about this failure."
)

#: What the capability returns when the deployment has no knowledge base.
KNOWLEDGE_UNCONFIGURED: Final[str] = (
    "The knowledge base is not configured for this deployment, so no runbook or "
    "procedure could be consulted. Treat this as no documentation being reachable, not "
    "as none existing."
)

#: What it returns when an operator has switched the knowledge base off.
KNOWLEDGE_DISABLED: Final[str] = (
    "Knowledge base search is switched off for this team, so no runbook or procedure was "
    "consulted. Continue without it."
)

#: What it returns when the search ran and matched nothing.
KNOWLEDGE_EMPTY: Final[str] = (
    "No documentation in this team's knowledge base matches that. That is a normal "
    "result — nobody has written about this failure — and it is not a reason to search "
    "again with different wording."
)

#: The header a knowledge answer carries.
KNOWLEDGE_HEADER: Final[str] = (
    "{count} passage(s) from this team's knowledge base, most relevant first. Cite the "
    "document and section rather than restating a passage as your own finding."
)

#: One retrieved passage, as the agent is shown it. The citation leads, because
#: a passage read before its source is a passage quoted without one.
KNOWLEDGE_CHUNK: Final[str] = (
    "[{rank}] {title} — {section} ({document_type})\n"
    "    source: {location}\n"
    "    updated: {updated}\n"
    "    passage: {text}"
)

# --- Proposals ---------------------------------------------------------------

#: What the proposal capability returns once a proposal is queued. It says
#: outright that nothing has been written, because an agent that believed its
#: proposal had taken effect would go on to cite it.
PROPOSAL_QUEUED: Final[str] = (
    "Your proposal has been placed in the review queue as {proposal_id} and is NOT part "
    "of the knowledge base. A human has to approve it first. Do not cite it, and do not "
    "assume a later search will find it."
)

#: What it returns when there is no queue to write to.
PROPOSAL_UNCONFIGURED: Final[str] = (
    "The knowledge review queue is not configured for this deployment, so the proposal "
    "was not recorded. Include what you would have proposed in your conclusion instead."
)

#: What it returns when the proposal itself was refused at the boundary — most
#: often because it carried something a guardrail rule blocks.
PROPOSAL_REFUSED: Final[str] = (
    "The proposal was not recorded: {reason} Nothing was written to the review queue."
)

#: Recorded on a document that entered the knowledge base through review (FR-019).
#: One sentence rather than a flag, because it is shown to whoever later reads
#: the document and "agent-originated" is the part they need.
PROPOSAL_ATTRIBUTION: Final[str] = (
    "Proposed by the investigation agent during {correlation_id} and approved by "
    "{approved_by} on {approved_at}."
)


__all__ = [
    "KNOWLEDGE_CHUNK",
    "KNOWLEDGE_DISABLED",
    "KNOWLEDGE_EMPTY",
    "KNOWLEDGE_GUIDANCE",
    "KNOWLEDGE_HEADER",
    "KNOWLEDGE_UNCONFIGURED",
    "PROPOSAL_ATTRIBUTION",
    "PROPOSAL_QUEUED",
    "PROPOSAL_REFUSED",
    "PROPOSAL_UNCONFIGURED",
    "TOPOLOGY_DISABLED",
    "TOPOLOGY_EDGE",
    "TOPOLOGY_EDGE_STALE",
    "TOPOLOGY_EMPTY",
    "TOPOLOGY_GUIDANCE",
    "TOPOLOGY_HEADER",
    "TOPOLOGY_TRUNCATED",
    "TOPOLOGY_UNAVAILABLE",
    "TOPOLOGY_UNCONFIGURED",
]
