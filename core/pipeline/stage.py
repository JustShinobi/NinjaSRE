"""What a stage is, and what happens when one raises.

A stage is ``async (state) -> updates``. It reads whatever it likes and it
writes nothing: the updates it returns are merged by ``apply_state_updates``,
which is the only thing in the pipeline that changes state. That is what makes
"did this stage stay inside its slice" a question a test can answer.

The failure contract is the other half, and it is deliberately blunt. A stage
that raises has its exception annotated with which stage it was and re-raised
unchanged. Not wrapped — a caller that knows how to handle a
``TimeoutError`` should still see a ``TimeoutError`` — and not swallowed, because
a result that never entered the trace did not happen, and a stage that returned
empty updates after failing looks exactly like a stage that had nothing to say.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.state.agent_state import AgentState, StateUpdates
from core.state.types import StageName

#: How a stage's identity is attached to an exception on its way out. PEP 678
#: notes travel with the exception through every ``raise`` that follows, so the
#: stage is named in the traceback a caller prints without the exception type
#: having to change.
STAGE_FAILURE_NOTE = "raised inside the {stage} stage of investigation {run_id}"


@runtime_checkable
class Stage(Protocol):
    """One step of the pipeline: a pure function from state to updates."""

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return what this stage established, as whole slices."""


def annotate_failure(error: BaseException, *, stage: StageName, run_id: str) -> BaseException:
    """Return ``error`` carrying the identity of the stage it came out of.

    Annotating rather than wrapping. The exception a caller catches is the one
    the stage raised, so a handler that knows what to do with a provider
    timeout still recognises it, and the trace still says where it happened.
    """
    error.add_note(STAGE_FAILURE_NOTE.format(stage=stage.value, run_id=run_id))
    return error


__all__ = [
    "STAGE_FAILURE_NOTE",
    "Stage",
    "annotate_failure",
]
