"""What an operator may add to the agent's prompt, and what it is allowed to cost.

The operating context is unlike every other configuration field in one respect
that decides all the bounds here: it is paid for on **every model call of every
investigation**, forever, by every team that inherits it. A budget field an
operator sets once and a prompt suffix an operator sets once look the same in a
form and cost differently by three orders of magnitude.

So the ceiling is a token count rather than a character count, and it is
enforced at *write* time. Truncating at run time is what the evidence budget
does (``core/agent/context_budget.py``) and it is right there, because evidence
arrives during a run and something has to go. Configuration does not arrive
during a run: it was written by a person who can be told the document is too
long while they still have it in front of them, and configuration that silently
shrinks is configuration nobody can reason about.
"""

from __future__ import annotations

from typing import Final

#: What the whole rendered operating context may cost, in tokens, at one node.
#:
#: Twelve hundred is about two pages of prose. The number came from what the
#: facts worth writing actually are — what runs here, how the network is
#: divided, what criticality means, where the metrics live, who is called — each
#: of which is a short paragraph, and none of which is a runbook. Past this the
#: field has stopped being context and become documentation, which belongs in
#: the knowledge corpus where it is retrieved when relevant rather than paid for
#: on every call.
OPERATING_CONTEXT_TOKEN_BUDGET: Final[int] = 1_200

#: The roles whose system prompt the operating context is appended to.
#:
#: The two that *investigate*. Intake classifies an alert and diagnosis
#: structures a conclusion; neither reasons about the estate, and both run on
#: every alert including the ones that never become an investigation — so
#: including them would pay the whole context on the alerts that cost the least
#: to be wrong about.
OPERATING_CONTEXT_ROLES: Final[tuple[str, ...]] = ("investigator", "subagent")

#: How many named sections one node may declare. A bound rather than a
#: preference: sections are the unit of inheritance, and a chain of four nodes
#: each adding a dozen is a prompt nobody wrote and nobody can read.
MAX_OPERATING_CONTEXT_SECTIONS: Final[int] = 12

#: How long a section's name may be. It is a heading in a prompt and a path
#: segment in the provenance table, and both stop working as a name grows into
#: a sentence.
MAX_OPERATING_CONTEXT_NAME_CHARS: Final[int] = 60


__all__ = [
    "MAX_OPERATING_CONTEXT_NAME_CHARS",
    "MAX_OPERATING_CONTEXT_SECTIONS",
    "OPERATING_CONTEXT_ROLES",
    "OPERATING_CONTEXT_TOKEN_BUDGET",
]
