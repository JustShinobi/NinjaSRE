"""Telling the agent that memory exists, without telling it what is in memory.

This is the feature's central design decision expressed as thirty lines of code.
The obvious alternative — search memory on the alert and put the best matches
into the opening prompt — was tried upstream and abandoned, for a reason that
holds here too: an alert is a vague, vocabulary-heavy document, similarity search
over one returns episodes that share words rather than causes, and an agent
handed a wrong precedent before it has looked at anything reasons from it all the
way to a conclusion. The cost of being wrong is asymmetric and large.

So the prompt gets *guidance* and never *content*. The agent is told memory
exists, told to search it once it holds concrete evidence, and told to search on
the evidence rather than on the alert. Whether to search, and on what, is then a
decision it makes with something to make it from.

The guidance is appended rather than prepended, and appended once. The system
prompt a caller supplied is what the investigation is framed as, and inserting
ahead of it would change the framing of every run to talk about memory first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.prompts.memory import MEMORY_RECALL_GUIDANCE
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from platform.memory.policy import MemoryPolicy

#: The name the hook registers under, so an ablation can unregister exactly this
#: one and a trace can say which hook changed the prompt.
MEMORY_GUIDANCE_HOOK = "memory.guidance"

#: Late. Guidance is framing rather than a bound, and anything that shortens or
#: rewrites the prompt should have run before this appends to it.
HOOK_ORDER = 100


@dataclass(frozen=True, slots=True)
class MemoryGuidance:
    """Appends the recall guidance to the root prompt, once, when reading is on."""

    policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    text: str = MEMORY_RECALL_GUIDANCE

    async def on_run_start(self, session: Session) -> None:
        """Append the guidance to ``session``'s system prompt.

        Idempotent. A resumed session already carries the guidance from its first
        start, and appending it again would spend context on a paragraph the
        model has already read — and, worse, make a resumed run's prompt differ
        from the fresh run it is meant to be comparable with.
        """
        if not self.policy.read_enabled or self.text in session.system_prompt:
            return
        session.system_prompt = f"{session.system_prompt}\n\n{self.text}".strip()
        session.touch()

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach the guidance hook to ``hooks`` and return it."""
        hooks.register(
            HookPoint.ON_RUN_START,
            self.on_run_start,
            name=MEMORY_GUIDANCE_HOOK,
            order=HOOK_ORDER,
        )
        return hooks


__all__ = [
    "HOOK_ORDER",
    "MEMORY_GUIDANCE_HOOK",
    "MemoryGuidance",
]
