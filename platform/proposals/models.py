"""A proposal, whichever origin it came from, and the form it is stored in.

Four origins, one queue. The alternative — a queue per origin — was rejected for
a reason that is easy to state and expensive to discover late: a reviewer's
question is "what is waiting on me", not "what is waiting on me about
detectors", and three lists is three places to look before the answer is none.

**The approval store is the queue.** It already holds state, a decision, a
reason, an expiry, an audit trail and — the one that matters most — a rollback
plan written before anything can be approved. A second store beside it would
have to reimplement all six, and the sixth is Article III.

So a proposal is an approval request whose action is ``<type>.proposal`` and
whose arguments carry the four things a review cannot happen without: what would
change, why, which investigation produced it, and where to see the effect. Those
four are required by the validator rather than by convention — a proposal
missing any of them is a proposal a reviewer would approve because there was
nothing to read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from config.constants.proposals import PROPOSAL_ACTION_SUFFIX, PROPOSAL_DECISION_TTL_HOURS
from config.constants.security import SIDE_EFFECT_WRITE_REVERSIBLE
from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState

#: Keys a proposal keeps inside the approval request's arguments. The store holds
#: approvals, not configuration and not runbooks, and teaching it what a detector
#: is would be the wrong direction of dependency.
NODE_KEY = "node_id"
PAYLOAD_KEY = "payload"
RATIONALE_KEY = "rationale"
EVIDENCE_KEY = "evidence"
CORRELATION_KEY = "correlation_id"
TARGET_KEY = "target"

#: How the knowledge queue spells the node, from before this queue existed. Read
#: rather than migrated: rewriting the arguments of a stored approval rewrites
#: what somebody was asked to approve.
LEGACY_NODE_KEY = "team_node_id"


class ProposalState(StrEnum):
    """Where a proposal got to.

    A mirror of ``ApprovalState`` rather than a reuse of it, because this is the
    vocabulary the console, the capability, and the operator documentation
    speak, and a reviewer should not have to know the approval store's names.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @classmethod
    def of(cls, state: ApprovalState) -> ProposalState:
        """Return the proposal state an approval state describes."""
        return cls(state.value)

    @property
    def is_decided(self) -> bool:
        """Return whether this state is final."""
        return self is not ProposalState.PENDING


class ProposalType(StrEnum):
    """Where a proposal came from, which is also how its effect is shown.

    The type is not a label. It decides which mechanism renders the consequence
    — a configuration preview, a detector dry run, or the final text — and a
    proposal whose type nothing can render is a proposal nobody can review.
    """

    KNOWLEDGE = "knowledge"
    OPERATING_CONTEXT = "operating_context"
    DETECTOR = "detector"
    CONFIGURATION = "configuration"

    @property
    def action(self) -> str:
        """Return the approval action a proposal of this type is stored under."""
        return f"{self.value}{PROPOSAL_ACTION_SUFFIX}"

    @classmethod
    def of_action(cls, action: str) -> ProposalType | None:
        """Return the type an approval action names, or ``None`` if it names none.

        ``None`` rather than a raise: the approval store holds remediation
        approvals and configuration gates too, and a listing walks all of them.
        """
        if not action.endswith(PROPOSAL_ACTION_SUFFIX):
            return None
        stem = action[: -len(PROPOSAL_ACTION_SUFFIX)]
        return cls(stem) if stem in set(cls) else None


#: How the effect of each type is shown. Named here rather than in the console,
#: because the answer is a property of the platform: a configuration change is
#: previewed by the configuration service and a detector by its own dry run, and
#: a client choosing differently would show somebody the wrong consequence.
EFFECT_MECHANISM: Mapping[ProposalType, str] = {
    ProposalType.KNOWLEDGE: "text",
    ProposalType.OPERATING_CONTEXT: "context-preview",
    ProposalType.DETECTOR: "detector-dry-run",
    ProposalType.CONFIGURATION: "config-preview",
}


@dataclass(frozen=True, slots=True)
class EffectReference:
    """Where to see what a proposal would do, and to what.

    A reference rather than the effect itself. Computing the consequence means
    calling the configuration service or running a detector over history, and a
    queue listing that did that for every row would be a listing nobody could
    load — so the row says which mechanism and which target, and the review
    screen asks.
    """

    mechanism: str
    target: str

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form the console reads."""
        return {"mechanism": self.mechanism, "target": self.target}


@dataclass(frozen=True, slots=True)
class AgentProposal:
    """One change an agent proposed, with everything a decision rests on."""

    proposal_id: str
    proposal_type: ProposalType
    org_id: str
    team_node_id: str
    summary: str
    #: The node the change lands at. Empty for a knowledge proposal, which lands
    #: in the corpus rather than at a node.
    node_id: str = ""
    #: What the applier writes: a settings patch, a detector declaration, or a
    #: section body. Shape is the applier's business; the queue keeps it whole.
    payload: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""
    evidence: tuple[str, ...] = ()
    #: The investigation this came out of. The link a reviewer follows, and the
    #: reason acceptance 1 is a field rather than a sentence in the summary.
    run_id: str = ""
    #: What makes two proposals "the same proposal" for rejection recall. Derived
    #: by the caller from what the change is about, never from the run — two runs
    #: proposing the same thing is exactly the case the recall exists for.
    correlation_id: str = ""
    proposed_at: datetime | None = None
    state: ProposalState = ProposalState.PENDING
    decided_by: str = ""
    decided_at: datetime | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("a proposal must have an id")
        if not self.summary.strip():
            raise ValueError(f"{self.proposal_id}: a proposal must say what would change")

    @property
    def effect(self) -> EffectReference:
        """Return the mechanism that shows what this proposal would do."""
        return EffectReference(
            mechanism=EFFECT_MECHANISM[self.proposal_type],
            target=self.target,
        )

    @property
    def target(self) -> str:
        """Return what the effect mechanism is asked about.

        The node for anything that resolves through the hierarchy, the detector
        for a detector, and the proposal itself for knowledge — whose effect is
        its own text, so there is nothing else to name.
        """
        if self.proposal_type is ProposalType.DETECTOR:
            return str(self.payload.get("detector_id", "")) or self.proposal_id
        return self.node_id or self.proposal_id

    @property
    def is_decided(self) -> bool:
        """Return whether a human has answered this."""
        return self.state.is_decided

    def arguments(self) -> dict[str, Any]:
        """Return what the approval request stores verbatim.

        The whole proposal, not a reference to one. An approval granted against
        different content than was applied is not an approval, and keeping the
        exact payload on the request is what lets an audit prove they matched.
        """
        return {
            NODE_KEY: self.node_id,
            PAYLOAD_KEY: dict(self.payload),
            RATIONALE_KEY: self.rationale,
            EVIDENCE_KEY: list(self.evidence),
            CORRELATION_KEY: self.correlation_id,
            TARGET_KEY: self.target,
        }

    def to_request(self, *, at: datetime) -> ApprovalRequest:
        """Return the approval request this proposal is stored as."""
        return ApprovalRequest(
            approval_id=self.proposal_id,
            run_id=self.run_id,
            action=self.proposal_type.action,
            # Reversible, and the plan that says how is stored beside this
            # request in the same unit of work before anybody can approve it.
            side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
            summary=self.summary,
            requested_at=at,
            expires_at=at + timedelta(hours=PROPOSAL_DECISION_TTL_HOURS),
            arguments=self.arguments(),
        )

    @classmethod
    def from_request(cls, request: ApprovalRequest, *, org_id: str) -> AgentProposal | None:
        """Return the proposal ``request`` describes, or ``None`` if it is not one."""
        proposal_type = ProposalType.of_action(request.action)
        if proposal_type is None:
            return None
        arguments: Mapping[str, Any] = request.arguments
        payload = arguments.get(PAYLOAD_KEY)
        # ``team_node_id`` is the knowledge queue's spelling, and it is read here
        # rather than migrated. A knowledge proposal written before this queue
        # existed is still a proposal waiting on somebody, and rewriting stored
        # approval arguments to unify a key would rewrite what was approved.
        node = str(arguments.get(NODE_KEY) or arguments.get(LEGACY_NODE_KEY, ""))
        return cls(
            proposal_id=request.approval_id,
            proposal_type=proposal_type,
            org_id=org_id,
            team_node_id=node,
            summary=request.summary,
            node_id=node,
            payload=dict(payload) if isinstance(payload, Mapping) else _rest(arguments),
            rationale=str(arguments.get(RATIONALE_KEY, "")),
            evidence=tuple(str(item) for item in arguments.get(EVIDENCE_KEY) or ()),
            run_id=request.run_id,
            correlation_id=str(arguments.get(CORRELATION_KEY, "")),
            proposed_at=request.requested_at,
            state=ProposalState.of(request.state),
            decided_by=request.decided_by or "",
            decided_at=request.decided_at,
            reason=request.reason or "",
        )

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the console and the trace read."""
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type.value,
            "node_id": self.node_id,
            "summary": self.summary,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
            "effect": self.effect.to_record(),
            "state": self.state.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "reason": self.reason,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
        }


def _rest(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Return the arguments that are not the shared envelope, as the payload.

    What a knowledge proposal would change *is* its title, body and document
    type, which the knowledge queue stores as top-level arguments rather than
    under a payload key. Reading the remainder is what lets one queue show a
    proposal written by a capability that predates it, without either side
    learning the other's shape.
    """
    envelope = {
        NODE_KEY,
        LEGACY_NODE_KEY,
        PAYLOAD_KEY,
        RATIONALE_KEY,
        EVIDENCE_KEY,
        CORRELATION_KEY,
        TARGET_KEY,
    }
    return {name: value for name, value in arguments.items() if name not in envelope}


@dataclass(frozen=True, slots=True)
class PriorRejection:
    """One earlier refusal of the same proposal, as the review screen shows it.

    The spec's argument turns on this: a proposal refused three times for three
    different reasons is a proposal whose reasons nobody is learning, and one
    refused three times for the same reason is either a lesson that never got
    written down or an operator who is wrong. Both are useful and neither is
    reachable if a rejection is a state with no text.
    """

    proposal_id: str
    reason: str
    decided_by: str
    decided_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the review screen reads."""
        return {
            "proposal_id": self.proposal_id,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }


__all__ = [
    "CORRELATION_KEY",
    "LEGACY_NODE_KEY",
    "EFFECT_MECHANISM",
    "EVIDENCE_KEY",
    "NODE_KEY",
    "PAYLOAD_KEY",
    "RATIONALE_KEY",
    "TARGET_KEY",
    "AgentProposal",
    "EffectReference",
    "PriorRejection",
    "ProposalState",
    "ProposalType",
]
