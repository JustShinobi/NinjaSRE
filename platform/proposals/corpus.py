"""The checks a repository already documents, offered as proposals nobody enabled.

Feature 056 reads a team's verification document into candidate detectors and
returns them. Returning them was the whole of it: a caller held a tuple, and
there was no caller. This is the other half — the candidates become rows in the
review queue, each with the sentence its author wrote as evidence and the
document as its origin, and a person decides.

**Nothing here writes a detector.** The proposal is queued; approving it is what
runs the applier, which writes through the configuration service with its audit
line and its approval gate. That ordering is the point of the whole feature and
it is the point of 056's scope note: a document that could turn itself into
something which pages people is the one outcome this must not have.

**A candidate already answered is not offered again.** The correlation key is the
detector's identifier, so a nightly sync over an unchanged document proposes
nothing after the first night — pending, approved and refused all count as
answered. A queue that regrew every morning is a queue people stop opening, and
the recurrence worth surfacing is an *investigation* hitting the same symptom
again, which arrives through the agent rather than through a file that has not
changed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from platform.observability.logging import get_logger
from platform.proposals.errors import ProposalRefused
from platform.proposals.models import AgentProposal, ProposalType
from platform.proposals.service import ProposalQueue

logger = get_logger(__name__)

#: How a detector candidate's correlation key is built. The identifier alone,
#: so the same check read out of a renamed document is still the same proposal
#: and still carries whatever was said about it last time.
CORRELATION = "detector:{detector_id}"

#: How the proposal's own identifier is built. Derived rather than random,
#: because a sync that ran twice before anybody looked should leave one row.
PROPOSAL_ID = "corpus-{detector_id}"


@dataclass(frozen=True, slots=True)
class OfferedCandidates:
    """What one pass over a corpus put in front of a person, and what it skipped."""

    queued: tuple[AgentProposal, ...] = ()
    #: ``(detector_id, why)`` for each candidate that was not offered. Named
    #: rather than dropped: "already refused in March" is the answer to "why is
    #: this check still not running", and a silent skip is where that answer
    #: goes to be lost.
    skipped: tuple[tuple[str, str], ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable record a scheduled run logs."""
        return {
            "queued": [proposal.proposal_id for proposal in self.queued],
            "skipped": [{"detector_id": name, "reason": why} for name, why in self.skipped],
        }


@dataclass(slots=True)
class DetectorProposals:
    """Puts a corpus run's candidates in the review queue, once each."""

    queue: ProposalQueue
    #: The node the detectors would run at. The queue's own team: a corpus is
    #: read for a team and its checks belong to that team's estate.
    node_id: str

    async def offer(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        run_id: str,
    ) -> OfferedCandidates:
        """Queue each candidate nobody has answered yet, and say what was skipped.

        ``candidates`` are the plain settings mappings 056 produces, not its
        dataclass: this package proposes and knows nothing about how a document
        was parsed, which is what keeps the knowledge base free to change how it
        reads one.
        """
        answered = await self._answered()
        queued: list[AgentProposal] = []
        skipped: list[tuple[str, str]] = []

        for candidate in candidates:
            detector_id = str(candidate.get("detector_id", ""))
            if not detector_id:
                skipped.append(("", "the candidate names no detector"))
                continue
            correlation = CORRELATION.format(detector_id=detector_id)
            if correlation in answered:
                skipped.append((detector_id, "already in the queue or already answered"))
                continue
            try:
                queued.append(await self._offer(candidate, detector_id, run_id=run_id))
            except ProposalRefused as refusal:
                # Refused at the origin, which is where a sealed or unreviewable
                # proposal is supposed to stop. Recorded so the run says why the
                # check is not on the queue rather than leaving it unexplained.
                logger.info(
                    "proposal.corpus_candidate_refused",
                    detector=detector_id,
                    reason=refusal.reason,
                )
                skipped.append((detector_id, refusal.reason))

        return OfferedCandidates(queued=tuple(queued), skipped=tuple(skipped))

    async def _offer(
        self, candidate: Mapping[str, Any], detector_id: str, *, run_id: str
    ) -> AgentProposal:
        """Queue one candidate as a detector proposal."""
        origin = str(candidate.get("origin", ""))
        excerpt = str(candidate.get("origin_excerpt", "")).strip()
        return await self.queue.propose(
            AgentProposal(
                proposal_id=PROPOSAL_ID.format(detector_id=detector_id),
                proposal_type=ProposalType.DETECTOR,
                org_id=self.queue.scope.org_id,
                team_node_id=self.node_id,
                node_id=self.node_id,
                summary=f"Watch {candidate.get('signal', detector_id)}, as the corpus describes",
                payload=dict(candidate),
                rationale=(
                    f"{origin or 'A document in this corpus'} states this check and nothing "
                    f"in the deployment performs it. Enabling it is what turns a check "
                    f"somebody runs by hand into one that runs every interval."
                ),
                # The author's own sentence, quoted. A reviewer deciding whether
                # to page people on a threshold needs the reason beside it, and
                # the reason is in the document rather than in this module.
                evidence=tuple(item for item in (excerpt, origin) if item),
                run_id=run_id,
                correlation_id=CORRELATION.format(detector_id=detector_id),
            )
        )

    async def _answered(self) -> frozenset[str]:
        """Return the correlation keys this team has already been asked about."""
        pending = await self.queue.pending()
        decided = await self.queue.decided()
        return frozenset(
            proposal.correlation_id for proposal in (*pending, *decided) if proposal.correlation_id
        )


__all__ = ["CORRELATION", "PROPOSAL_ID", "DetectorProposals", "OfferedCandidates"]
