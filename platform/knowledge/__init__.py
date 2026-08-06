"""Two knowledge stores: what the estate looks like, and what the team wrote down.

The **topology graph** answers two questions an investigation cannot answer from
naming conventions — what could have caused this, and who is affected. The
**knowledge base** answers a third: has anybody written down what to do about it.
They are one package because they share four mechanisms, and splitting them would
mean four duplications for no benefit: the recall discipline, the ablation shape,
the team scoping, and the review workflow for agent-proposed changes.

Four decisions shape everything here.

**Both are queried agent-driven, never pre-injected.** Topology handed to an
agent before it knows which service is affected is a map of the wrong territory;
a runbook retrieved on the alert text is retrieved on vocabulary. The opening
prompt gets guidance about *when* to ask, and the answers arrive when there is
something to ask about.

**Discovery reconciles; it never replaces.** Re-running discovery against a
Kubernetes API having a bad minute must not delete a team's topology, and it must
never delete the operator annotations that record what no scraper could have
seen. A source that cannot confirm an edge marks it unverified and leaves it
there.

**Agent-proposed knowledge goes through a human.** An agent that writes knowledge
it later reads, unreviewed, builds a self-reinforcing belief system with no
external correction. There is no code path from a proposal to the knowledge base
that does not pass a review, and a test asserts it by trying.

**The two switches are independent.** "Does the graph help" and "do the runbooks
help" are two experiments, and one switch would answer neither.
"""

from __future__ import annotations

from platform.knowledge.clock import is_stale, now
from platform.knowledge.errors import (
    DocumentRejected,
    ImportInvalid,
    KnowledgeError,
    ProposalNotApproved,
    ProposalUnknown,
    UnknownDependency,
)
from platform.knowledge.guidance import KnowledgeGuidance
from platform.knowledge.policy import (
    KNOWLEDGE_SWITCH,
    KNOWLEDGE_SWITCHES,
    TOPOLOGY_SWITCH,
    KnowledgePolicy,
)
from platform.knowledge.proposals import (
    KnowledgeProposal,
    ProposalDecision,
    ProposalQueue,
    ProposalState,
)
from platform.knowledge.service import KnowledgeService

__all__ = [
    "KNOWLEDGE_SWITCH",
    "KNOWLEDGE_SWITCHES",
    "TOPOLOGY_SWITCH",
    "DocumentRejected",
    "ImportInvalid",
    "KnowledgeError",
    "KnowledgeGuidance",
    "KnowledgePolicy",
    "KnowledgeProposal",
    "KnowledgeService",
    "ProposalDecision",
    "ProposalNotApproved",
    "ProposalQueue",
    "ProposalState",
    "ProposalUnknown",
    "UnknownDependency",
    "is_stale",
    "now",
]
