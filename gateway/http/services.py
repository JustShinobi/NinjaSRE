"""What the REST surface needs from a running investigation, as a seam.

``InvestigationRunner`` is a protocol rather than a concrete composition root,
for the same reason ``surfaces/cli/client.py``'s ``LocalServices`` is one:
composing a runtime — the LLM client, the capability catalogue, the credential
proxy — is a deployment concern (feature 030). This is the seam a deployment
profile fills in, and it is what lets this whole surface be driven in a test by
a fake that records what it was asked to do.

Everything that does *not* need a live runtime — runs, replay, streaming,
configuration, schedules, memory, capabilities, health — is wired directly to
the tier-3 ports in the route handlers, because those already work without a
model attached.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.agent.interaction.models import Interaction


@dataclass(frozen=True, slots=True)
class InvestigationStart:
    """One investigation, as the API states it.

    ``run_id`` is already reserved — ``RunRecorder.start_run`` has already
    written the row — by the time a runner sees this, which is what lets the
    route respond with the run's identity before this ever executes.

    ``incident_id``, ``alert_labels`` and ``credential_name`` are all
    optional and all empty by default: an operator-triggered investigation
    has no incident to attach a receipt to and no delivery to name, and a
    runner that was not composed with somewhere to record one ignores them
    regardless. A runner that *can* record and *is* given these writes the
    investigation's receipt onto the named incident's timeline before it
    starts reasoning.
    """

    run_id: str
    objective: str
    team_node_id: str
    principal_id: str
    #: The organisation this run belongs to. Alongside ``team_node_id`` because
    #: a runner that can record needs a full tenant scope to open its own units
    #: of work with — the team alone is not a scope the persistence layer opens.
    org_id: str = ""
    alert_source: str = ""
    context: Mapping[str, str] = field(default_factory=dict)
    incident_id: str = ""
    alert_labels: Mapping[str, str] = field(default_factory=dict)
    #: The delivery credential's *display* name — never its value.
    credential_name: str = ""


@runtime_checkable
class InvestigationRunner(Protocol):
    """What the API asks of a running platform to start and steer an investigation."""

    async def investigate(self, request: InvestigationStart) -> str:
        """Run the investigation to completion and return its summary.

        Called from a background task; the route that triggered it has already
        responded with ``request.run_id``. Never awaited by the request itself.
        """

    async def cancel(self, run_id: str) -> None:
        """Ask ``run_id`` to stop at its next safe point."""

    async def take_over(self, run_id: str, *, principal: str) -> None:
        """Suspend ``run_id`` at its next safe point so a person can drive it.

        Distinct from ``cancel`` in the state it leaves behind and in nothing
        else about how it stops: a taken-over run is suspended and resumable
        with its evidence intact, and a cancelled one is over. Both stop between
        iterations rather than mid-call, because a capability result that
        happened and was never written down is the one thing a resumable run
        cannot survive.
        """

    async def resume(self, run_id: str) -> None:
        """Hand ``run_id`` back to the agent, with what the person did in context."""

    async def queue_message(self, run_id: str, text: str) -> None:
        """Queue ``text`` for delivery on the run's next turn."""

    async def pending_interactions(self, run_id: str) -> tuple[Interaction, ...]:
        """Return the run's open questions and approvals, longest-waiting first."""

    async def find_interaction(self, interaction_id: str) -> Interaction | None:
        """Return one interaction wherever it is, or ``None``.

        Read before ``answer_interaction`` mutates anything, so a route can
        check the interaction's run against the caller's team first — an
        interaction belongs to a run, and a run belongs to a team, and that
        chain is what makes cross-team access to somebody else's pending
        question unreachable (FR-003, SC-006).
        """

    async def answer_interaction(
        self,
        interaction_id: str,
        *,
        text: str,
        principal: str,
        selected_option: str = "",
    ) -> Interaction:
        """Answer one interaction and return it, closed.

        Approving and rejecting are answers too: ``selected_option`` carries
        ``"approve"`` or ``"reject"`` for an approval interaction, so the route
        layer needs no second vocabulary for what closing one means.
        """


__all__ = ["InvestigationRunner", "InvestigationStart"]
