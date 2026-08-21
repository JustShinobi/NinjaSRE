"""What actually happens when a change is approved, one adapter per change type.

The service knows how to decide. It deliberately does not know how to write a
configuration node, install a prompt, enable a capability, or ingest a knowledge
document — those belong to the packages that own them, and a service that
reached into all four would be the place every one of their invariants got
re-implemented slightly differently.

So each adapter here is thin by design: read the current value, and apply the
proposed one through the owning package's own write path. That is what keeps the
configuration schema validated by the configuration service, and the knowledge
corpus written by the ingestor that knows how to chunk and embed it.

**The dependency runs one way.** This module imports the configuration service
and the knowledge queue; neither imports the approval layer. A gated write there
hands the approval layer a callback (``GatedChangeQueue``) rather than importing
it, so the two packages stay separable and the import graph stays a graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.proposals import PROPOSAL_ACTOR
from platform.approvals.models import ChangeTarget, ChangeType, PendingChange
from platform.approvals.service import ApprovalService
from platform.config_service.document import NodeDocument
from platform.config_service.errors import UnknownNode
from platform.config_service.service import ConfigService
from platform.knowledge.proposals import ProposalQueue
from platform.persistence.ports import ActorKind
from platform.persistence.ports.approval_store import RollbackStep
from platform.proposals.models import AgentProposal, ProposalType
from platform.remediation.components import ComponentRegistry
from platform.remediation.execution import RemediationApplier

#: The capability an approved proposal's rollback plan calls to put a node's own
#: settings back. Named here because the plan is stored at propose time, months
#: before anybody might run it, and the name has to survive that gap.
CONFIG_ROLLBACK_CAPABILITY = "config.set_settings"

#: The capability that removes a document an approved knowledge proposal wrote.
KNOWLEDGE_ROLLBACK_CAPABILITY = "knowledge.delete_document"


@dataclass(slots=True)
class ConfigurationApplier:
    """Reads and writes a configuration node's own settings (feature 013).

    Reads the node's *own* document rather than its effective configuration.
    The change is to what this node declares; diffing against what it resolves
    to would show a reviewer every value it inherits and never changed, and
    fingerprinting against it would mark every ancestor edit as a conflict on
    every descendant's queued change.
    """

    service: ConfigService

    async def read(self, target: ChangeTarget) -> Mapping[str, Any] | None:
        """Return the node's own settings, or ``None`` if the node is gone."""
        try:
            document = await self.service.document(target.identifier)
        except UnknownNode:
            return None
        return document.settings

    async def apply(self, change: PendingChange) -> None:
        """Write the approved settings through the configuration service.

        Through the service, so the write is validated, lock-checked, and
        audited exactly as an ungated one is. Writing the node directly would
        make an approved change the one path into storage that skipped the
        schema — and the changes worth gating are the ones worth validating.

        ``replace`` because the queued document is the whole of what the node
        should declare: it was captured as a complete document at queue time and
        re-reviewed against a complete one, and merging it as a patch would
        silently keep fields the reviewer saw being removed.
        """
        await self.service.set_settings(
            change.target.identifier,
            change.proposed,
            actor_id=change.requester,
            actor_kind=ActorKind.USER,
            replace=True,
        )


@dataclass(slots=True)
class PromptApplier:
    """Installs an approved prompt, which is a configuration write underneath.

    A separate type from ``ConfigurationApplier`` because a prompt change is a
    separate thing to gate — an organisation that wants prompts reviewed and
    ordinary configuration not is the common case — even though what happens on
    approval is the same write.
    """

    service: ConfigService

    async def read(self, target: ChangeTarget) -> Mapping[str, Any] | None:
        """Return the prompt values the node declares, or ``None`` if it is gone."""
        try:
            document = await self.service.document(target.identifier)
        except UnknownNode:
            return None
        return _at(document, target.path)

    async def apply(self, change: PendingChange) -> None:
        """Write the approved prompt through the configuration service."""
        await self.service.set_settings(
            change.target.identifier,
            _under(change.target.path, change.proposed),
            actor_id=change.requester,
            actor_kind=ActorKind.USER,
        )


@dataclass(slots=True)
class CapabilityApplier:
    """Enables or disables capabilities at a node (Article IX).

    A capability toggle is configuration too, and it is a distinct change type
    because it is the one that widens what an agent may do during somebody
    else's incident. Everything about it that is not the diff renderer is a
    configuration write.
    """

    service: ConfigService
    path: str = "capabilities"

    async def read(self, target: ChangeTarget) -> Mapping[str, Any] | None:
        """Return the node's capability settings, or ``None`` if it is gone."""
        try:
            document = await self.service.document(target.identifier)
        except UnknownNode:
            return None
        return _at(document, target.path or self.path)

    async def apply(self, change: PendingChange) -> None:
        """Write the approved capability set through the configuration service."""
        await self.service.set_settings(
            change.target.identifier,
            _under(change.target.path or self.path, change.proposed),
            actor_id=change.requester,
            actor_kind=ActorKind.USER,
        )


@dataclass(slots=True)
class KnowledgeApplier:
    """Accepts an agent-proposed document into the corpus (feature 012).

    The proposal itself is the target, not the document: a knowledge proposal
    that has been *superseded* by a second proposal for the same document is a
    conflict worth catching, and the proposal identifier is what makes the two
    distinguishable.
    """

    proposals: ProposalQueue

    async def read(self, target: ChangeTarget) -> Mapping[str, Any] | None:
        """Return the proposal as it stands, or ``None`` if it is gone.

        ``None`` for an unknown proposal is what turns "the agent withdrew it"
        or "another team's queue" into an unrecoverable conflict rather than an
        approval of nothing.
        """
        proposal = await self.proposals.get(target.identifier)
        if proposal is None:
            return None
        return {
            "document_id": proposal.document_id,
            "title": proposal.title,
            "body": proposal.body,
            "state": proposal.state.value,
        }

    async def apply(self, change: PendingChange) -> None:
        """Accept the proposal into the knowledge base.

        Through feature 012's own approval path, which records the decision
        before it writes the document — so a crash between the two leaves a
        recorded approval and no document rather than a document nobody
        approved.
        """
        await self.proposals.approve(
            change.target.identifier,
            reviewer=change.decision.decided_by if change.decision else change.requester,
            reason=change.decision.reason or "" if change.decision else "",
        )


@dataclass(slots=True)
class ConfigurationProposalApplier:
    """An agent-proposed configuration change, written through the ordinary path.

    The payload is a settings patch at a node, and applying it is
    ``set_settings`` — validated, lock-checked, gate-checked and audited exactly
    as an operator's edit is. Anything else would make an approved proposal the
    one way into storage that skipped the schema, and the changes worth proposing
    are the changes worth validating.

    ``ActorKind.AGENT`` with both names in the actor is acceptance 5's audit
    half: the trail says the agent proposed it and says who let it through, and a
    query for what the platform did to itself finds it without parsing a string.
    """

    service: ConfigService

    async def rollback_steps(self, proposal: AgentProposal) -> Sequence[RollbackStep]:
        """Return the step that puts the node's own settings back as they are now.

        Read at *propose* time, which is the point: the undo is the document as
        it stood when somebody was asked, not as it stands when they answer. A
        plan computed at approval time would restore a state the reviewer never
        saw.
        """
        return (
            RollbackStep(
                ordinal=1,
                description=f"Restore {proposal.node_id!r} to the settings it declares now",
                capability=CONFIG_ROLLBACK_CAPABILITY,
                arguments={
                    "node_id": proposal.node_id,
                    "settings": dict(await self._settings(proposal.node_id)),
                },
            ),
        )

    async def apply(self, proposal: AgentProposal, *, approved_by: str) -> str:
        """Write the proposed patch and return what changed."""
        await self.service.set_settings(
            proposal.node_id,
            proposal.payload,
            actor_id=PROPOSAL_ACTOR.format(
                proposal_id=proposal.proposal_id, approved_by=approved_by
            ),
            actor_kind=ActorKind.AGENT,
        )
        return f"{proposal.node_id}: applied {proposal.summary}"

    async def _settings(self, node_id: str) -> Mapping[str, Any]:
        """Return the node's own settings, or nothing when the node is gone."""
        try:
            document = await self.service.document(node_id)
        except UnknownNode:
            return {}
        return document.settings


@dataclass(slots=True)
class OperatingContextProposalApplier(ConfigurationProposalApplier):
    """A proposed fact about how this team's estate actually behaves (feature 059).

    A configuration write underneath, and a separate type because it is a
    separate thing to decide: "every LXC investigation had to learn that the
    metric comes from the host" is a sentence a person judges on whether it is
    *true*, not on whether the value is in range. The screen renders its effect
    as the prompt the model will read rather than as a diff of settings.
    """


@dataclass(slots=True)
class DetectorProposalApplier(ConfigurationProposalApplier):
    """Enabling a detector the corpus proposed, or adding one it described.

    The list is read, merged and written back whole, because
    ``policies.observation.detectors`` is a list and a patch over one replaces
    all of it. Reading first is what stops enabling one candidate from deleting
    every other detector the team runs — the failure a partial write would cause
    is silent until the night nothing fires.

    The rollback is the inherited one — the node's whole document as it stands
    at propose time — rather than the detector list on its own. Restoring only
    the list would leave every other setting the write touched wherever the
    write left it, and a partial undo is the kind that reads as a completed one.
    """

    async def apply(self, proposal: AgentProposal, *, approved_by: str) -> str:
        """Add or enable the proposed detector, leaving the rest of the set alone."""
        declared = dict(proposal.payload)
        detector_id = str(declared.get("detector_id", ""))
        rows = [dict(row) for row in await self._rows(proposal)]

        found = next((row for row in rows if row.get("detector_id") == detector_id), None)
        if found is None:
            rows.append({**declared, "enabled": True})
        else:
            found.update(declared)
            found["enabled"] = True

        await self.service.set_settings(
            proposal.node_id,
            {"policies": {"observation": {"detectors": rows}}},
            actor_id=PROPOSAL_ACTOR.format(
                proposal_id=proposal.proposal_id, approved_by=approved_by
            ),
            actor_kind=ActorKind.AGENT,
        )
        return f"{proposal.node_id}: {detector_id} is now running"

    async def _rows(self, proposal: AgentProposal) -> Sequence[Mapping[str, Any]]:
        """Return the detector rows the node declares today."""
        try:
            document = await self.service.document(proposal.node_id)
        except UnknownNode:
            return ()
        section = document.settings.get("policies", {})
        observation = section.get("observation", {}) if isinstance(section, Mapping) else {}
        rows = observation.get("detectors", ()) if isinstance(observation, Mapping) else ()
        return tuple(row for row in rows if isinstance(row, Mapping))


@dataclass(slots=True)
class KnowledgeProposalApplier:
    """A proposed document, accepted through feature 012's own review path.

    Thin on purpose. The knowledge queue already records the decision before it
    writes, attributes the document to the agent and the approver, and stores the
    delete that undoes it; this adapter exists so the unified queue can reach
    that path rather than reimplement any of it.
    """

    proposals: ProposalQueue

    async def rollback_steps(self, proposal: AgentProposal) -> Sequence[RollbackStep]:
        """Return the delete that removes the document an approval would create."""
        return (
            RollbackStep(
                ordinal=1,
                description=f"Delete the document {proposal.target!r} and its chunks",
                capability=KNOWLEDGE_ROLLBACK_CAPABILITY,
                arguments={"document_id": proposal.target},
            ),
        )

    async def apply(self, proposal: AgentProposal, *, approved_by: str) -> str:
        """Accept the proposal into the corpus through the knowledge queue.

        ``apply`` rather than ``approve``: the decision is already a row by the
        time this runs — the unified queue recorded it before calling — and
        approving twice is refused by the store, correctly. This is the write
        half on its own, and it still reads the store and still refuses on
        anything but a recorded approval.

        ``approved_by`` is unused here for the same reason: the attribution the
        document carries is read off the decided row by feature 012's own
        applier, which is where the sentence a later reader sees is composed.
        """
        del approved_by
        decision = await self.proposals.apply(proposal.proposal_id)
        return f"{decision.proposal.document_id}: written to the knowledge base"


def proposal_appliers_for(
    *,
    config: ConfigService | None = None,
    knowledge: ProposalQueue | None = None,
) -> dict[ProposalType, Any]:
    """Return the proposal appliers a deployment wires its review queue with.

    Only what this deployment can carry out. A type with no applier cannot be
    proposed and does not appear in the queue, which is the correct failure: a
    deployment with no knowledge base should refuse a knowledge proposal rather
    than accept one it could never honour.

    Knowledge arrives through the capability the agent already has, and the row
    it writes is the same row this queue reads — the action feature 012 stores it
    under is exactly ``knowledge.proposal``. So wiring it here does not give one
    proposal two queues; it gives the one queue the fourth origin.
    """
    built: dict[ProposalType, Any] = {}
    if config is not None:
        built[ProposalType.CONFIGURATION] = ConfigurationProposalApplier(service=config)
        built[ProposalType.OPERATING_CONTEXT] = OperatingContextProposalApplier(service=config)
        built[ProposalType.DETECTOR] = DetectorProposalApplier(service=config)
    if knowledge is not None:
        built[ProposalType.KNOWLEDGE] = KnowledgeProposalApplier(proposals=knowledge)
    return built


def appliers_for(
    *,
    config: ConfigService | None = None,
    proposals: ProposalQueue | None = None,
    remediation: ComponentRegistry | None = None,
) -> dict[ChangeType, Any]:
    """Return the applier map a deployment wires its approval service with.

    Only the types this deployment can actually apply. A change type with no
    applier cannot be queued, which is the correct failure: a deployment with no
    knowledge base should refuse a knowledge proposal at the queue rather than
    accept one it could never honour.

    ``remediation`` is the registry of what this deployment can remediate with,
    which is assembled where the capabilities are. It is a parameter rather than
    something built here because this module is below that assembly and would
    otherwise have to reach up into it.

    The remediation applier is the one that does not itself apply. Approval
    authorises; the executor re-evaluates the conditions, locks the target, and
    performs the action. Its ``read`` is what conflict detection fingerprints
    against, which is why it belongs in this map rather than beside it.
    """
    built: dict[ChangeType, Any] = {}
    if config is not None:
        built[ChangeType.CONFIGURATION] = ConfigurationApplier(service=config)
        built[ChangeType.PROMPT] = PromptApplier(service=config)
        built[ChangeType.CAPABILITY] = CapabilityApplier(service=config)
    if proposals is not None:
        built[ChangeType.KNOWLEDGE] = KnowledgeApplier(proposals=proposals)
    if remediation is not None:
        built[ChangeType.REMEDIATION] = RemediationApplier(registry=remediation)
    return built


@dataclass(slots=True)
class ApprovalQueueAdapter:
    """The callback a gated write hands to the approval layer.

    Satisfies the configuration service's ``GatedChangeQueue``, which is
    declared there as a protocol so that package never imports this one. That
    is what keeps the dependency running one way: the approval layer knows about
    configuration, and configuration knows only that *something* takes its gated
    writes away.
    """

    service: ApprovalService
    change_type: ChangeType = ChangeType.CONFIGURATION

    async def __call__(
        self,
        *,
        node_id: str,
        settings: Mapping[str, Any],
        gated_paths: tuple[str, ...],
        actor_id: str,
    ) -> str:
        """Queue the gated write and return the identifier the caller reports."""
        change = await self.service.queue(
            change_type=self.change_type,
            target=ChangeTarget(
                identifier=node_id,
                node_id=node_id,
                path=gated_paths[0] if len(gated_paths) == 1 else None,
            ),
            proposed=settings,
            requester=actor_id,
            rationale=f"Changes {', '.join(sorted(gated_paths))}, which this organisation gates.",
        )
        return change.change_id


def _at(document: NodeDocument, path: str | None) -> Mapping[str, Any]:
    """Return the sub-document at ``path``, or the whole thing when there is none."""
    if path is None:
        return document.settings
    from platform.config_service import paths

    value = paths.value_at(document.settings, path)
    return value if isinstance(value, Mapping) else {path.rpartition(".")[2]: value}


def _under(path: str | None, values: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``values`` nested beneath ``path``, as a patch the service accepts."""
    if path is None:
        return dict(values)
    nested: Any = dict(values)
    for segment in reversed(path.split(".")):
        nested = {segment: nested}
    return dict(nested)


__all__ = [
    "CONFIG_ROLLBACK_CAPABILITY",
    "KNOWLEDGE_ROLLBACK_CAPABILITY",
    "ApprovalQueueAdapter",
    "CapabilityApplier",
    "ConfigurationApplier",
    "ConfigurationProposalApplier",
    "DetectorProposalApplier",
    "KnowledgeApplier",
    "KnowledgeProposalApplier",
    "OperatingContextProposalApplier",
    "PromptApplier",
    "appliers_for",
    "proposal_appliers_for",
]
