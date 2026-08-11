"""The bounds on what an agent may propose, and how long a proposal waits.

A proposal is the one thing on this platform an agent writes that a human is
expected to act on, so the numbers here are about *review* rather than about
execution: how many a queue shows at once, how far back the rejection history is
read, and — the two that are not numbers — which parts of a configuration a
proposal may never name.

The sealed prefixes are the load-bearing entry. A system that can propose changes
to the rules constraining it is a system whose constraints are advisory, and the
refusal has to be structural rather than a review habit: it is enforced where the
proposal is made, so nothing sealed ever reaches a queue for somebody to approve
on a bad afternoon.
"""

from __future__ import annotations

from typing import Final

#: What every proposal's approval action ends in. The action is
#: ``<type>.proposal``, which is how a listing tells a proposal apart from a
#: remediation approval without a second column in the store.
PROPOSAL_ACTION_SUFFIX: Final = ".proposal"

#: How long a proposal of a configuration, context or detector change stays
#: answerable. Three days rather than the knowledge queue's week: these change
#: what the deployment *does*, and a decision taken long after the recurrence
#: that motivated it is a decision taken without the evidence.
PROPOSAL_DECISION_TTL_HOURS: Final[float] = 72.0

#: How many decided proposals the rejection recall and the acceptance figure
#: read. Bounded because both are rendered on a screen: a queue that pulled the
#: whole decided history to compute one percentage would get slower every month.
MAX_DECIDED_PROPOSAL_HISTORY: Final[int] = 200

#: How many prior rejections of the same recurring proposal are shown. Three is
#: the number the spec's own argument turns on — a proposal refused three times
#: is either a lesson nobody recorded or an operator who is wrong — and showing
#: more than five would bury it.
MAX_RECALLED_REJECTIONS: Final[int] = 5

#: Who the audit says made the change, when an approved proposal is applied.
#:
#: Both names, in one string, because the audit's actor is one field and the
#: acceptance is that both appear: the agent proposed it and a person let it
#: through, and a trail carrying only one of those answers the wrong half of
#: "why is today's configuration different from yesterday's". The kind is
#: ``AGENT`` alongside it, so a query for what the platform did to itself finds
#: these without parsing the string.
PROPOSAL_ACTOR: Final[str] = "agent ({proposal_id}), approved by {approved_by}"

#: The configuration a proposal may never name, whatever its type.
#:
#: These are the sections that decide what the agent is allowed to do:
#: masking, guardrail mode, what needs approval, and how much autonomy is
#: granted. A proposal touching any of them is refused where it is made, and the
#: refusal is returned to the agent rather than queued — an operator should never
#: be shown a change that would loosen the containment, because being shown it is
#: most of the way to approving it.
SEALED_CONFIG_PREFIXES: Final[tuple[str, ...]] = (
    "policies.approvals",
    "policies.autonomy",
    "policies.guardrails",
    "policies.masking",
)

#: The field names a proposal may never carry a value for, on top of whatever
#: the installed integrations declare secret. ``credential`` is *not* here: it
#: holds a reference to the vault, which is the field that exists so the secret
#: is somewhere else.
SEALED_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "api_token",
        "client_secret",
        "password",
        "private_key",
        "secret",
        "secret_key",
        "token",
        "webhook_secret",
    }
)

__all__ = [
    "MAX_DECIDED_PROPOSAL_HISTORY",
    "MAX_RECALLED_REJECTIONS",
    "PROPOSAL_ACTION_SUFFIX",
    "PROPOSAL_ACTOR",
    "PROPOSAL_DECISION_TTL_HOURS",
    "SEALED_CONFIG_PREFIXES",
    "SEALED_FIELD_NAMES",
]
