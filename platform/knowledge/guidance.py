"""Telling the agent both stores exist, without telling it what is in either.

The same decision episodic memory made, and it is worth restating because it is
counter-intuitive twice over. The obvious thing to do with a topology graph is to
put the affected service's neighbours in the opening prompt; the obvious thing to
do with a knowledge base is to retrieve on the alert and paste the best runbook.
Both are wrong for the same reason: the alert is a vague, vocabulary-heavy
document, and anything retrieved with it is retrieved on words rather than on the
failure. An agent handed a wrong precedent before it has looked at anything
reasons from it all the way to a conclusion.

So the prompt gets *guidance* and never *content*. Two paragraphs, appended once,
each gated on its own switch — because a deployment with a graph and no runbooks
should not be told to search a knowledge base that is empty, and an ablation run
with topology disabled must not carry a paragraph telling the agent to query a
graph it is not allowed to query.

Appended rather than prepended, and after memory's guidance. The system prompt a
caller supplied is what the investigation is framed as, and inserting ahead of it
would change the framing of every run to talk about topology first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.prompts.knowledge import KNOWLEDGE_GUIDANCE, TOPOLOGY_GUIDANCE
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from platform.knowledge.policy import KnowledgePolicy

#: The name the hook registers under, so an ablation can unregister exactly this
#: one and a trace can say which hook changed the prompt.
KNOWLEDGE_GUIDANCE_HOOK = "knowledge.guidance"

#: After memory's guidance, which is at 100. Both are framing rather than bounds,
#: and the order between them is the order an investigation uses them: what has
#: happened before, then what the estate looks like and what is written down.
HOOK_ORDER = 110


@dataclass(frozen=True, slots=True)
class KnowledgeGuidance:
    """Appends the topology and knowledge-base guidance, once, when each is on."""

    policy: KnowledgePolicy = field(default_factory=KnowledgePolicy)
    topology_text: str = TOPOLOGY_GUIDANCE
    knowledge_text: str = KNOWLEDGE_GUIDANCE

    def paragraphs(self) -> tuple[str, ...]:
        """Return the guidance this policy calls for, in order."""
        found: list[str] = []
        if self.policy.topology_enabled:
            found.append(self.topology_text)
        if self.policy.knowledge_enabled:
            found.append(self.knowledge_text)
        return tuple(found)

    async def on_run_start(self, session: Session) -> None:
        """Append whichever guidance applies to ``session``'s system prompt.

        Idempotent per paragraph. A resumed session already carries what its
        first start appended, and appending again would spend context on text the
        model has read — and, worse, make a resumed run's prompt differ from the
        fresh run it is meant to be comparable with.
        """
        additions = [text for text in self.paragraphs() if text not in session.system_prompt]
        if not additions:
            return
        session.system_prompt = "\n\n".join((session.system_prompt, *additions)).strip()
        session.touch()

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach the guidance hook to ``hooks`` and return it."""
        hooks.register(
            HookPoint.ON_RUN_START,
            self.on_run_start,
            name=KNOWLEDGE_GUIDANCE_HOOK,
            order=HOOK_ORDER,
        )
        return hooks


__all__ = [
    "HOOK_ORDER",
    "KNOWLEDGE_GUIDANCE_HOOK",
    "KnowledgeGuidance",
]
