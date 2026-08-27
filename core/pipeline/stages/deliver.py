"""Shipping the finished investigation to wherever the team is already looking.

One rule dominates the module: **a destination that fails does not stop the
others**. An investigation delivered to three of four places is a
delivered investigation, and letting the fourth raise would turn a broken
webhook into an incident nobody heard about. So every attempt is a value,
recorded with the destination it belongs to, and the outcome says which ones
arrived.

Formatting is per destination rather than done once here. A chat message, an
incident-tracker comment, and a webhook body are three renderings of the same
investigation, and pre-rendering a string in this stage would force all three
to be the same one. What the stage hands over is the state and the diagnosis;
what to make of them belongs to the transport.

Nothing here executes a remediation. The steps in a diagnosis are
recommendations for a human until the remediation feature gates them, and this
stage is the last place they pass through before somebody reads them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config.prompts.investigation import DELIVERY_FAILED_DETAIL
from core.domain.diagnosis.result import DeliveryAttempt, DeliveryOutcome, Diagnosis
from core.pipeline.ports import DeliveryDestination, DeliveryPayload
from core.state.agent_state import AgentState, StateUpdates
from core.state.types import InvestigationOutcome, OutcomeKind, StageName
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The headline recorded on a completed investigation.
DIAGNOSED_HEADLINE = "{category}: {root_cause}"

#: What the outcome says about where the report went.
DELIVERED_DETAIL = "Delivered to {delivered}."
DELIVERED_PARTIALLY = "Delivered to {delivered}; {failed} did not accept it."
DELIVERED_NOWHERE = (
    "No destination is configured for this team, so the report was produced and not "
    "shipped. It is in the investigation record."
)
DELIVERED_TO_NONE = "No destination accepted the report: {failed}."


@dataclass(frozen=True, slots=True)
class DeliverStage:
    """Format and ship the diagnosis, one destination's failure at a time."""

    destinations: tuple[DeliveryDestination, ...] = ()

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.DELIVER

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return where the report went, and the outcome the run ends on."""
        diagnosis = state.investigation.diagnosis
        payload = DeliveryPayload(state=state, diagnosis=diagnosis or Diagnosis())
        outcome = DeliveryOutcome(
            attempts=tuple(
                [await self._attempt(destination, payload) for destination in self.destinations]
            )
        )

        return StateUpdates(
            investigation=replace(
                state.investigation,
                delivery=outcome,
                outcome=_verdict(state.investigation.outcome, diagnosis, outcome),
            )
        )

    async def _attempt(
        self, destination: DeliveryDestination, payload: DeliveryPayload
    ) -> DeliveryAttempt:
        """Return what happened at one destination, failure included.

        Broad on purpose. A transport raises whatever its client library
        raises, and the set of those is not knowable here — what is knowable is
        that none of them should end an investigation that has already
        concluded.
        """
        try:
            reference = await destination.deliver(payload)
        except Exception as error:
            logger.warning(
                "pipeline.delivery_failed",
                run_id=payload.run_id,
                destination=destination.name,
                error=str(error),
            )
            return DeliveryAttempt(
                destination=destination.name,
                delivered=False,
                failure=f"{type(error).__name__}: {error}",
                detail=DELIVERY_FAILED_DETAIL.format(destination=destination.name, error=error),
            )
        return DeliveryAttempt(destination=destination.name, delivered=True, detail=str(reference))


def _verdict(
    reached: InvestigationOutcome | None,
    diagnosis: Diagnosis | None,
    delivery: DeliveryOutcome,
) -> InvestigationOutcome:
    """Return the outcome the run ends on, keeping one it already failed with.

    Gathering records ``FAILED`` when the runtime produced nothing usable, and
    that outcome deliberately does not halt: the remaining stages still say
    what little can be said, and the report is still shipped. What they must
    not do is overwrite the verdict. A caller reading the finished state — the
    serving path decides between "the run completed" and "the run failed" on
    exactly this — would otherwise be told an investigation that gathered
    nothing was diagnosed, and the reason the runtime gave would be gone with
    the outcome that carried it.
    """
    if reached is not None and reached.kind is OutcomeKind.FAILED:
        return reached
    return _outcome(diagnosis, delivery)


def _outcome(diagnosis: Diagnosis | None, delivery: DeliveryOutcome) -> InvestigationOutcome:
    """Return the outcome the run ends on, naming the cause and where it went."""
    headline = (
        DIAGNOSED_HEADLINE.format(
            category=diagnosis.root_cause_category.value,
            root_cause=diagnosis.root_cause or "no cause was established",
        )
        if diagnosis is not None
        else "No diagnosis was produced"
    )
    return InvestigationOutcome(
        kind=OutcomeKind.DIAGNOSED,
        headline=headline,
        detail=_delivery_detail(delivery),
        next_steps=diagnosis.remediation_steps if diagnosis is not None else (),
    )


def _delivery_detail(delivery: DeliveryOutcome) -> str:
    """Return one sentence saying where the report reached."""
    if not delivery.attempts:
        return DELIVERED_NOWHERE
    if delivery.complete:
        return DELIVERED_DETAIL.format(delivered=", ".join(delivery.delivered))
    if not delivery.delivered:
        return DELIVERED_TO_NONE.format(failed=", ".join(delivery.failed))
    return DELIVERED_PARTIALLY.format(
        delivered=", ".join(delivery.delivered), failed=", ".join(delivery.failed)
    )


__all__ = [
    "DELIVERED_DETAIL",
    "DELIVERED_NOWHERE",
    "DELIVERED_PARTIALLY",
    "DELIVERED_TO_NONE",
    "DIAGNOSED_HEADLINE",
    "DeliverStage",
]
