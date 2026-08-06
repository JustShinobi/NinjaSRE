"""One approval mechanism, and the organisation policy that decides what it gates.

Five kinds of change go through here — a configuration edit, a prompt change, a
capability toggle, an agent's knowledge proposal, and (when feature 017 lands) a
production remediation. They are one mechanism rather than five because they are
the same problem: somebody proposes something, somebody else decides, and the
record has to survive both of them leaving the company. Five mechanisms would
have drifted, and the one nobody looked at twice would be the weakest.

What a caller reaches for:

``ApprovalService``
    Queue, review, decide, re-review, expire. Every state transition in this
    package happens inside it, which is what makes "nothing applies without a
    decision" a property rather than a convention.
``SecurityPolicy``
    What needs approval, what is refused outright, and what a token's life looks
    like. Its constraints take no principal, because a ceiling an owner can
    quietly exceed is documentation.
``ChangeApplier``
    What a caller implements to put one kind of change into effect. The service
    calls it in exactly one place.
"""

from __future__ import annotations

from platform.approvals.blast_radius import BlastRadius
from platform.approvals.closure import ClosurePublisher, DecisionEvent, DecisionSubscriber
from platform.approvals.diff import (
    DiffEngine,
    DiffSummary,
    StructuredDiff,
    summarise,
)
from platform.approvals.errors import (
    ApprovalError,
    ChangeAlreadyDecided,
    ChangeConflicted,
    ChangeNotFound,
    IllegalTransition,
    PolicyLocked,
    PolicyViolation,
    ReviewerNotPermitted,
    SelfApprovalForbidden,
)
from platform.approvals.models import (
    ChangeState,
    ChangeTarget,
    ChangeType,
    Conflict,
    ConflictReason,
    Decision,
    PendingChange,
    ReviewerSet,
    fingerprint_of,
)
from platform.approvals.notification import (
    NotificationResult,
    ReviewerNotifier,
    ReviewRequest,
    ReviewSink,
)
from platform.approvals.policy import (
    DEFAULT_POLICY,
    PolicyChangeEffect,
    SecurityPolicy,
    TokenLifecycleDefaults,
)
from platform.approvals.routing import reviewers_for
from platform.approvals.service import ApprovalService, ChangeApplier, ChangeReview
from platform.approvals.state_machine import TRANSITIONS, is_permitted

__all__ = [
    "DEFAULT_POLICY",
    "TRANSITIONS",
    "ApprovalError",
    "ApprovalService",
    "BlastRadius",
    "ChangeAlreadyDecided",
    "ChangeApplier",
    "ChangeConflicted",
    "ChangeNotFound",
    "ChangeReview",
    "ChangeState",
    "ChangeTarget",
    "ChangeType",
    "ClosurePublisher",
    "Conflict",
    "ConflictReason",
    "Decision",
    "DecisionEvent",
    "DecisionSubscriber",
    "DiffEngine",
    "DiffSummary",
    "IllegalTransition",
    "NotificationResult",
    "PendingChange",
    "PolicyChangeEffect",
    "PolicyLocked",
    "PolicyViolation",
    "ReviewRequest",
    "ReviewSink",
    "ReviewerNotPermitted",
    "ReviewerNotifier",
    "ReviewerSet",
    "SecurityPolicy",
    "SelfApprovalForbidden",
    "StructuredDiff",
    "TokenLifecycleDefaults",
    "fingerprint_of",
    "is_permitted",
    "reviewers_for",
    "summarise",
]
