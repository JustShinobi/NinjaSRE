"""What the queue refuses, and why the refusal goes back to whoever proposed it.

One error, deliberately. A proposal is refused for one of two reasons — it is
missing something a reviewer needs, or it names something nothing may propose —
and both end the same way: nothing is stored, and the caller is told in a
sentence it can act on.

The refusal is *returned to the agent* rather than logged and swallowed. An
agent that believes its proposal is queued will cite it, wait for it, or propose
it again; an agent told "this named a credential field" will not propose the
same thing next week.
"""

from __future__ import annotations


class ProposalRefused(Exception):
    """A proposal that never entered the queue, and the sentence saying why.

    ``reason`` never quotes a value. A refusal that echoed the credential it
    found would be the first place that credential was written down, which is
    the opposite of what the refusal is for.
    """

    __slots__ = ("proposal_id", "reason")

    def __init__(self, proposal_id: str, reason: str) -> None:
        self.proposal_id = proposal_id
        self.reason = reason
        super().__init__(f"{proposal_id}: {reason}")


__all__ = ["ProposalRefused"]
