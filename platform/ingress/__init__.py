"""What happens to a delivery after it has been verified: the ledger and the rules.

Tier 3, and deliberately not in ``gateway/``. Two callers need the same answers —
the webhook handler on the live path, and the simulate endpoint an operator uses
before saving a rule — and a matcher that lived beside one of them would be
copied to the other, which is the chat-routing lesson: matching lives in one
function, and the transports are callers.
"""

from __future__ import annotations

from platform.ingress.ledger import (
    delivery_key,
    masked_sample,
    record_delivery,
)
from platform.ingress.rules import (
    RoutingRule,
    RuleMatch,
    RuleSet,
    RuleSetInvalid,
    Signals,
    default_rule_set,
    evaluate,
)

__all__ = [
    "RoutingRule",
    "RuleMatch",
    "RuleSet",
    "RuleSetInvalid",
    "Signals",
    "default_rule_set",
    "delivery_key",
    "evaluate",
    "masked_sample",
    "record_delivery",
]
