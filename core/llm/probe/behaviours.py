"""The behaviours the runtime depends on, and which of them are not optional.

``preflight`` next door asks whether a *provider* is configured correctly. This
asks what a *model* can do, one model at a time, and it asks by making the model
do it rather than by reading a flag off a registry row.

The distinction is the whole point. "Supports tools" in a model card frequently
means "was trained on some", and an advertised context window is frequently not
the window a four-bit quantisation can use. Both of those failures show up forty
seconds into an investigation, as an inscrutable error, on the operator's worst
day. Measuring them at setup turns each one into a sentence at setup instead.
"""

from __future__ import annotations

from enum import StrEnum


class Behaviour(StrEnum):
    """One thing the runtime needs a model to do."""

    #: Emit a structured tool call when given a tool and told to call it.
    TOOL_CALLING = "tool_calling"
    #: Produce a document that satisfies a supplied schema, by any mechanism.
    SCHEMA_ADHERENCE = "schema_adherence"
    #: Ask for more than one tool in a single turn.
    MULTI_TOOL_TURN = "multi_tool_turn"
    #: Carry a generation over an event stream.
    STREAMING = "streaming"
    #: Accept a prompt approaching its advertised context window.
    USABLE_CONTEXT = "usable_context"


class BehaviourStatus(StrEnum):
    """How one behaviour came out when the model was asked to perform it.

    ``DEGRADED`` is a real answer and not a soft failure. A model reaching
    structured output through a prompt-and-parse shim does the job, slower; a
    model that serialises a two-tool turn into two one-tool turns does the job,
    slower. Refusing either would rule out most self-hosted models, so both are
    accepted and both are said out loud.
    """

    PASSED = "passed"
    DEGRADED = "degraded"
    FAILED = "failed"
    #: Not probed, because a prior failure made the answer meaningless.
    SKIPPED = "skipped"


#: The behaviours an investigation cannot run without. Multi-tool turns and
#: streaming are absent deliberately: the loop serialises calls perfectly well
#: and never streams, so demanding either would exclude usable models for the
#: sake of a nicety.
REQUIRED_FOR_INVESTIGATION: frozenset[Behaviour] = frozenset(
    {Behaviour.TOOL_CALLING, Behaviour.SCHEMA_ADHERENCE, Behaviour.USABLE_CONTEXT}
)


__all__ = [
    "REQUIRED_FOR_INVESTIGATION",
    "Behaviour",
    "BehaviourStatus",
]
