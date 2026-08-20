"""The seam between a running investigation and its incident's timeline.

``InvestigationRecorder`` wraps one incident's :class:`IncidentLifecycle` and
writes the five kinds of reasoning entry an investigation produces, in the
order the product promises a person reading the timeline: receipt, then
hypotheses, then evidence, then a diagnosis (or the hypothesis it falls back
to with nothing to support it), then the report going out.

Every method here takes explicit, already-decided input — the labels that
arrived, the hypotheses considered, one evidence entry's query and result,
the diagnosis sentence and the evidence it rests on, the destinations a
report reached — the same shape every other ``IncidentLifecycle`` method
already takes. This module does not attempt to derive any of that from a raw
investigation transcript: ``core.agent.react_loop``'s recorded turns and
evidence carry what a model asked and what came back, not a labelled
"hypothesis" or a citation a screen could point at, and guessing a mapping
here would be presenting a guess as the record. Deciding how a live
investigation produces these values — a dedicated capability the model calls,
a planning stage, or something else — is a separate, later decision; this is
the seam whatever makes that decision calls into.

**The order is enforced, not merely documented.** Recording hypotheses after
evidence has already been recorded raises, so "hypotheses before the first
query" is a property of using this object rather than a rule a caller has to
remember to respect. Not every step is mandatory — an incident opened by a
person has no delivery to record a receipt for, and a degraded investigation
may stop after evidence with nothing to diagnose — so what is enforced is
relative order among the steps a caller actually takes, not that all five
occur.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from platform.incidents.lifecycle import IncidentLifecycle
from platform.persistence.ports.incident_store import TimelineEntry

#: The five steps' relative order. Values, not an enum, because the only
#: operation this module needs on them is "not smaller than the last one
#: reached" — a plain comparison, not a case analysis.
_STAGE_RECEIPT = 0
_STAGE_HYPOTHESES = 1
_STAGE_EVIDENCE = 2
_STAGE_DIAGNOSIS = 3
_STAGE_REPORT = 4

_STAGE_NAME = {
    _STAGE_RECEIPT: "receipt",
    _STAGE_HYPOTHESES: "hypotheses",
    _STAGE_EVIDENCE: "evidence",
    _STAGE_DIAGNOSIS: "diagnosis",
    _STAGE_REPORT: "report delivery",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RecordedOutOfOrder(RuntimeError):
    """A recording step was asked for after a later step already happened.

    Raised instead of silently accepting it, because a timeline that records
    a diagnosis and only afterwards "considered" a hypothesis is a timeline
    that misrepresents the order the investigation actually reasoned in.
    """

    def __init__(self, *, attempted: int, already_at: int) -> None:
        super().__init__(
            f"cannot record {_STAGE_NAME[attempted]} after {_STAGE_NAME[already_at]} "
            "already happened on this investigation"
        )


@dataclass(slots=True)
class InvestigationRecorder:
    """Records one investigation's reasoning onto one incident's timeline, in order.

    One instance per investigation, the same way ``ReActInvestigationRunner``
    composes one ``ReActLoop`` per investigation: the stage this object
    tracks is this investigation's alone.
    """

    lifecycle: IncidentLifecycle
    incident_id: str
    clock: Callable[[], datetime] = _utc_now
    _stage: int = field(default=_STAGE_RECEIPT, repr=False)

    async def receipt(self, *, labels: Mapping[str, str], credential_name: str) -> TimelineEntry:
        """Record what arrived: the alert's labels and the delivery's identity."""
        self._advance(_STAGE_RECEIPT)
        return await self.lifecycle.record_alert_received(
            self.incident_id,
            labels=labels,
            credential_name=credential_name,
            now=self.clock(),
        )

    async def hypotheses(self, items: Sequence[str]) -> TimelineEntry:
        """Record what was considered, before any evidence entry exists."""
        self._advance(_STAGE_HYPOTHESES)
        return await self.lifecycle.record_hypotheses(
            self.incident_id, hypotheses=items, now=self.clock()
        )

    async def evidence(self, *, query: str, result: str, conclusion: str = "") -> TimelineEntry:
        """Record one piece of evidence. Safe to call more than once, in a row."""
        self._advance(_STAGE_EVIDENCE)
        return await self.lifecycle.record_evidence(
            self.incident_id,
            query=query,
            result=result,
            conclusion=conclusion,
            now=self.clock(),
        )

    async def diagnosis(
        self, sentence: str, *, supporting_evidence_ids: Sequence[str] = ()
    ) -> TimelineEntry:
        """Record the conclusion, or the hypothesis it falls back to with no evidence."""
        self._advance(_STAGE_DIAGNOSIS)
        return await self.lifecycle.record_diagnosis(
            self.incident_id,
            sentence=sentence,
            supporting_evidence_ids=supporting_evidence_ids,
            now=self.clock(),
        )

    async def report_delivered(self, destinations: Sequence[str]) -> TimelineEntry:
        """Record that the report went out, and to where."""
        self._advance(_STAGE_REPORT)
        return await self.lifecycle.record_report_delivered(
            self.incident_id, destinations=destinations, now=self.clock()
        )

    def _advance(self, stage: int) -> None:
        """Move to ``stage``, or raise if that would move backwards."""
        if stage < self._stage:
            raise RecordedOutOfOrder(attempted=stage, already_at=self._stage)
        self._stage = max(self._stage, stage)


__all__ = ["InvestigationRecorder", "RecordedOutOfOrder"]
