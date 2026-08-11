"""Putting the team's own facts into the prompt of every session that investigates.

The assembly half of ``agents.operating_context``. The configuration side
renders the text (``schema/agents.py``); this is what gets it in front of a
model, and it is a ``on_run_start`` hook for three reasons rather than one.

**Because it is where the prompt is finally assembled.** ``ReActLoop`` builds
every provider request from ``session.system_prompt``, so a hook that appends
there reaches the model by the same path a caller's own prompt does — and by
exactly one path, which is what lets the console claim its preview is the text
the model receives.

**Because a specialist is a session too.** A sub-agent runs in its own session,
built from ``SUBAGENT_SYSTEM_PROMPT`` rather than from the investigator's
prompt, and driven through the same registry. Appending at composition time
would have reached the investigator and left every specialist reasoning about a
different estate than its parent.

**Because Article VII wants the contribution isolable.** The hook registers
under a name, so an ablation unregisters exactly this one and the trace can say
which hook changed the prompt. The configuration switch (``enabled``) is the
operator's version of the same lever, and both end in an empty ``text``.

Appended rather than prepended, and after memory's and knowledge's guidance: the
system prompt is what the investigation is framed as, and an estate description
in front of it would reframe every run to be about the estate.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from platform.config_service.schema.agents import AgentsConfig, with_operating_context

#: The name the hook registers under, so an ablation can unregister exactly this
#: one and a trace can say which hook changed the prompt.
OPERATING_CONTEXT_HOOK = "config.operating_context"

#: After knowledge's guidance, which is at 110, which is after memory's at 100.
#: Those two tell the agent what it may *ask*; this tells it what is true of the
#: estate it is asking about, and reading the question before the answer is the
#: order an investigation uses them in.
HOOK_ORDER = 120


@dataclass(frozen=True, slots=True)
class OperatingContextGuidance:
    """Appends a team's operating context to a session's system prompt, once."""

    #: The rendered block, already framed. Empty for a deployment that wrote no
    #: context and for one that switched it off — the two are the same thing
    #: from here, which is what makes the ablation a configuration change rather
    #: than a different build.
    text: str = ""

    @classmethod
    def of(cls, agents: AgentsConfig) -> OperatingContextGuidance:
        """Return the guidance ``agents`` declares, empty when it declares none."""
        return cls(text=agents.operating_context.render())

    @property
    def active(self) -> bool:
        """Return whether this guidance would change any prompt at all."""
        return bool(self.text.strip())

    async def on_run_start(self, session: Session) -> None:
        """Append the context to ``session``'s system prompt.

        Idempotent. A resumed session already carries what its first start
        appended, and appending again would spend context on text the model has
        read — and make a resumed run's prompt differ from the fresh run it is
        meant to be comparable with.
        """
        if not self.active or self.text in session.system_prompt:
            return
        session.system_prompt = with_operating_context(session.system_prompt, self.text)
        session.touch()

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach the guidance hook to ``hooks`` and return it."""
        hooks.register(
            HookPoint.ON_RUN_START,
            self.on_run_start,
            name=OPERATING_CONTEXT_HOOK,
            order=HOOK_ORDER,
        )
        return hooks


__all__ = [
    "HOOK_ORDER",
    "OPERATING_CONTEXT_HOOK",
    "OperatingContextGuidance",
]
