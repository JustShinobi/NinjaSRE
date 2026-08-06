"""Proposing something worth writing down — and being told, plainly, that it is not written.

The capability exists because the agent is often the only party that knows
something is worth recording: it has just spent forty minutes establishing that a
particular symptom means a particular cause, and the next investigation would
otherwise spend the same forty minutes. The capability is *bounded* because an
agent that wrote knowledge it later read, unreviewed, would build a
self-reinforcing belief system with no external correction.

So the receipt says outright that nothing was written and that a later search
will not find it. That sentence is doing real work: an agent that believed its
proposal had taken effect would go on to cite it in the same investigation, and a
citation to a document that does not exist is the exact failure Article I exists
to prevent.

The declared side-effect level is a write, with approval required, and that is
deliberate even though the write is to a review queue rather than to anything
operational. A capability that under-declares because "it does not really change
anything" is how the scale stops meaning what it says — and the plan's own
constitution check puts agent-proposed knowledge under the same default-deny
posture as a production write.
"""

from __future__ import annotations

from uuid import uuid4

from capabilities.tools.system.knowledge_propose import binding
from config.prompts.knowledge import PROPOSAL_QUEUED, PROPOSAL_REFUSED, PROPOSAL_UNCONFIGURED
from core.capability.decorator import tool
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.knowledge.base.models import DocumentType
from platform.knowledge.errors import KnowledgeError
from platform.knowledge.proposals import KnowledgeProposal

TOOL_NAME = "propose_knowledge"

#: How a proposal id is built when the caller does not supply one. Random rather
#: than derived from the content: two investigations proposing the same runbook
#: are two proposals a reviewer should see separately, because the second one is
#: evidence that the first was worth approving.
PROPOSAL_ID = "prop-{token}"

_PROPOSE_USE_CASES = (
    "record a symptom-to-cause link this investigation established, for the next one",
    "propose an amendment to a runbook that turned out to be wrong or incomplete",
    "capture a diagnostic step that worked and is not written down anywhere",
)

_PROPOSE_ANTI_EXAMPLES = (
    "recording an unconfirmed hypothesis as though it were established",
    "restating what a runbook already says",
    "using this to store notes for the current investigation — it is not readable back",
)


@tool(
    name=TOOL_NAME,
    display_name="Propose a knowledge change",
    description=(
        "Propose an addition or amendment to the team's knowledge base. The proposal "
        "enters a review queue with the investigation that produced it attached, and it "
        "does NOT become part of the knowledge base until a human approves it — a later "
        "search in this investigation will not find it, and you must not cite it. Use it "
        "for something you established with evidence and that a future investigation "
        "would want, not for a hypothesis."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.KNOWLEDGE_BASE,
    evidence_type=EvidenceType.DOCUMENT,
    # A write, declared as one. Nothing operational changes and nothing takes
    # effect without review, but a capability that under-declares because the
    # write is "only" to an internal queue is how the scale stops meaning what
    # it says.
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires_approval=True,
    approval_reason=(
        "The agent is proposing text for the team's knowledge base. Approving means a "
        "human has read the proposed content and the investigation behind it, and accepts "
        "it as documentation a future investigation will read and cite."
    ),
    rollback_plan=(
        "Delete the proposed document and its chunks from the knowledge base. Nothing "
        "outside NinjaSRE is affected, and no other document is modified."
    ),
    tags=("knowledge", "proposal", "review", "documentation"),
    use_cases=_PROPOSE_USE_CASES,
    anti_examples=_PROPOSE_ANTI_EXAMPLES,
)
async def propose_knowledge(
    title: str,
    body: str,
    correlation_id: str,
    document_type: str = DocumentType.RUNBOOK.value,
    amends: str = "",
    rationale: str = "",
) -> CapabilityResult:
    """Queue a proposal for review and return a receipt that says it is not applied.

    ``correlation_id`` is required and is the investigation this came out of
    (FR-018). A reviewer with no evidence to look at is a reviewer who approves
    it, and a proposal that could not name its own investigation would be one
    nobody could check.
    """
    sink = binding.current()
    if sink is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            PROPOSAL_UNCONFIGURED,
            detail=f"proposed {title!r}",
        )

    try:
        proposal = await sink.propose(
            KnowledgeProposal(
                proposal_id=PROPOSAL_ID.format(token=uuid4().hex[:12]),
                org_id="",
                team_node_id="",
                title=title,
                body=body,
                document_type=DocumentType.parse(document_type),
                correlation_id=correlation_id,
                amends=amends,
                rationale=rationale,
            )
        )
    except KnowledgeError as refused:
        # The queue screened the text and refused it — most often because the
        # proposal carried credential material the agent read from production.
        # The reason never quotes the match.
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            PROPOSAL_REFUSED.format(reason=str(refused)),
            detail=f"proposed {title!r}",
        )
    except ValueError as invalid:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            str(invalid),
            detail=f"proposed {title!r}",
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "proposal_id": proposal.proposal_id,
            "state": proposal.state.value,
            "applied": False,
            "text": PROPOSAL_QUEUED.format(proposal_id=proposal.proposal_id),
            **proposal.to_record(),
        },
        # No evidence. A proposal is not an observation of anything, and an
        # evidence entry for one would put the agent's own suggestion into the
        # trace as a finding — which is the shape of citation this whole review
        # workflow exists to prevent.
        evidence=(),
    )
