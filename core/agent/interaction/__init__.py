"""One abstraction for "the run is waiting on a human", and everything that follows.

A question the agent raised and a change somebody has to approve are the same
situation, and this package is where that stops being an observation and starts
being the reason there is one implementation of cross-surface closure, one of
persistence, one of concurrency resolution, and one of attention state.

Five modules, split by what they are responsible for rather than by what they
are about:

- ``models`` — the interaction, its two kinds, and the answer that closes one;
- ``registry`` — the pending set of one run, and the only place state changes;
- ``closure`` — the event every surface subscribes to, published once;
- ``persistence`` — interactions travelling inside the session record;
- ``attention`` — what a run listing shows about a run nobody is unblocking;
- ``progress`` — the timer and the cooldown that keep a long run from going dark.
"""

from __future__ import annotations

from core.agent.interaction.attention import (
    RUN_ATTENTION_KEY,
    RUN_ATTENTION_SINCE_KEY,
    Attention,
    attention_of,
    attention_over,
)
from core.agent.interaction.closure import (
    InteractionClosure,
    InteractionEvent,
    InteractionSurface,
    Propagation,
)
from core.agent.interaction.models import (
    NO_SURFACE,
    Answer,
    ApprovalInteraction,
    AttentionState,
    Interaction,
    InteractionKind,
    InteractionState,
    Question,
    Resolution,
    ScreenedText,
    question,
)
from core.agent.interaction.persistence import (
    INTERACTIONS_KEY,
    from_records,
    restore_registry,
    to_records,
)
from core.agent.interaction.progress import (
    ProgressNotifier,
    ProgressOutcome,
    ProgressReport,
    ProgressSink,
)
from core.agent.interaction.registry import InteractionRegistry, UnknownInteraction

__all__ = [
    "INTERACTIONS_KEY",
    "NO_SURFACE",
    "RUN_ATTENTION_KEY",
    "RUN_ATTENTION_SINCE_KEY",
    "Answer",
    "ApprovalInteraction",
    "Attention",
    "AttentionState",
    "Interaction",
    "InteractionClosure",
    "InteractionEvent",
    "InteractionKind",
    "InteractionRegistry",
    "InteractionState",
    "InteractionSurface",
    "ProgressNotifier",
    "ProgressOutcome",
    "ProgressReport",
    "ProgressSink",
    "Propagation",
    "Question",
    "Resolution",
    "ScreenedText",
    "UnknownInteraction",
    "attention_of",
    "attention_over",
    "from_records",
    "question",
    "restore_registry",
    "to_records",
]
