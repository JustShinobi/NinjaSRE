"""An investigation's conversation, two ways: as turns, and as a threaded reconstruction.

``/turns`` is the raw record. ``/threads`` reuses ``platform.runs.replay`` — the
same function ``/v1/runs/{run_id}/replay`` calls — to attach each turn's calls,
which is what makes it read as a conversation rather than a table.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.tenancy import visible
from gateway.http.state import GatewayState
from platform.persistence.ports.run_trace_store import TurnRecord
from platform.runs.replay import ReplayedTurn, replay_trace

router = APIRouter(prefix="/v1/investigations/{run_id}", tags=["investigations"])


class TurnView(BaseModel):
    turn_id: str
    index: int
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0


class TurnList(BaseModel):
    turns: list[TurnView]


class ThreadCallView(BaseModel):
    call_id: str
    name: str
    status: str
    duration_ms: int = 0
    error: str | None = None


class ThreadTurnView(BaseModel):
    turn_id: str
    index: int
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: ``None`` when the provider publishes no price for this turn — never a
    #: fabricated ``0.0`` standing in for "unknown".
    cost: float | None = None
    selection_rationale: str = ""
    #: What the model said on this turn, as it said it. Beside the selection
    #: rationale rather than in place of it: one is the agent's reasoning and
    #: the other is the deployment's note about what the agent was offered, and
    #: a reader asking why a capability was missing wants the second.
    model_rationale: str = ""
    calls: list[ThreadCallView]


class ThreadView(BaseModel):
    run_id: str
    turns: list[ThreadTurnView]


def _turn_view(turn: TurnRecord) -> TurnView:
    return TurnView(
        turn_id=turn.turn_id,
        index=turn.index,
        model=str(turn.usage.get("model", "")),
        prompt_tokens=int(turn.usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(turn.usage.get("completion_tokens", 0) or 0),
        cost=float(turn.usage.get("cost", 0.0) or 0.0),
    )


def thread_turn_view(turn: ReplayedTurn) -> ThreadTurnView:
    return ThreadTurnView(
        turn_id=turn.turn_id,
        index=turn.index,
        model=turn.model,
        prompt_tokens=turn.prompt_tokens,
        completion_tokens=turn.completion_tokens,
        cost=turn.cost,
        selection_rationale=turn.selection_rationale,
        model_rationale=turn.model_rationale,
        calls=[
            ThreadCallView(
                call_id=call.call_id,
                name=call.name,
                status=call.status.value,
                duration_ms=call.duration_ms,
                error=call.error,
            )
            for call in turn.calls
        ],
    )


@router.get("/turns", response_model=TurnList)
async def get_turns(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> TurnList:
    """Return one investigation's turns, in order."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no investigation {run_id!r}")
        turns = await uow.run_traces.turns_for_run(run_id)
    return TurnList(turns=[_turn_view(turn) for turn in turns])


@router.get("/threads", response_model=ThreadView)
async def get_thread(
    run_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ThreadView:
    """Return the investigation reconstructed as a thread: turns with their calls."""
    async with state.gateway.begin(auth.scope) as uow:
        run = await uow.run_traces.get_run(run_id)
        if run is None or not visible(run, auth):
            raise not_found(f"no investigation {run_id!r}")
        trace = await uow.run_traces.replay(run_id)
    replayed = replay_trace(trace)
    return ThreadView(run_id=run_id, turns=[thread_turn_view(turn) for turn in replayed.turns])


__all__ = ["router"]
