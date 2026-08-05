"""Where an investigation's state comes from before the first stage runs.

One function, because the alternative is every surface building state slightly
differently and the differences only showing up as a scenario that behaves
unlike production. The CLI, the webhook route, the chat bot, and the synthetic
harness all start here.

Nothing is inferred. The raw input is carried verbatim and the alert stays
``None`` until intake has looked at it — a factory that pre-normalised the alert
would mean the run had a parsed alert before the stage that is supposed to
produce one, and the noise short-circuit would be deciding about a value
somebody else computed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from core.domain.alerts.normalisation import RawAlert
from core.state.agent_state import AgentState
from core.state.slices import ChatSlice
from core.state.types import ChatMessage, TeamContext

#: What a message from the person or system that started the run is recorded as.
ORIGIN_AUTHOR = "origin"


def new_run_id() -> str:
    """Return an identifier for one investigation."""
    return f"run-{uuid.uuid4().hex[:16]}"


def initial_state(
    raw: RawAlert,
    team: TeamContext,
    *,
    run_id: str = "",
    channel: str = "",
    thread_id: str = "",
    history: Sequence[ChatMessage] = (),
    started_at: datetime | None = None,
) -> AgentState:
    """Return the state one investigation starts from.

    ``history`` is the conversation that was already in progress when the run
    started — the messages above the one that triggered it. Intake reads them,
    because "deploy going out in five minutes" three messages earlier is the
    difference between a mysterious error rate and a deployment regression.
    """
    at = started_at if started_at is not None else raw.at()
    messages = tuple(history)
    if raw.text.strip():
        messages = (*messages, ChatMessage(author=ORIGIN_AUTHOR, text=raw.text.strip(), at=at))

    return AgentState(
        run_id=run_id.strip() or new_run_id(),
        team=team,
        raw=raw,
        started_at=at,
        chat=ChatSlice(messages=messages, channel=channel, thread_id=thread_id),
    )


def state_from_text(
    text: str,
    team: TeamContext | None = None,
    *,
    source_hint: str = "",
    run_id: str = "",
) -> AgentState:
    """Return the state a plain-text investigation starts from.

    The convenience the REPL and the tests want, expressed in terms of the
    general one so there is no second construction path to keep in step.
    """
    return initial_state(
        RawAlert(text=text, source_hint=source_hint, received_at=datetime.now(UTC)),
        team if team is not None else TeamContext(),
        run_id=run_id,
    )


__all__ = [
    "ORIGIN_AUTHOR",
    "initial_state",
    "new_run_id",
    "state_from_text",
]
