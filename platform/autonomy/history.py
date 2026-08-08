"""Reading back what the deployment actually decided, so a change can be previewed.

The audit trail is the history. Every decision this package makes is already
written there with the whole action on it, so "what did we do last week" is a
query rather than a second table — and, more importantly, the preview and the
record cannot disagree about what happened, because they are the same rows.

**A row that cannot be read back is skipped, not raised on.** The trail is
append-only and spans schema changes by design: a record written before a field
existed is a record about something that really happened, and refusing to
preview because one of two hundred rows is old would be refusing the whole
feature over the oldest thing in it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.constants.autonomy import (
    AUTONOMY_AUDIT_ACTION_DECISION,
    AUTONOMY_AUDIT_RESOURCE_KIND,
    AUTONOMY_DETAIL_ACTION,
    MAX_AUTONOMY_PREVIEW_ACTIONS,
)
from platform.autonomy.preview import RecordedAction
from platform.autonomy.risk import risk_class_of
from platform.autonomy.subjects import ProposedAction, Subject
from platform.observability.logging import get_logger
from platform.persistence.ports import AuditEvent, PersistenceGateway, TenantScope

_LOG = get_logger(__name__)


@dataclass(slots=True)
class DecisionHistory:
    """The decisions this deployment has recorded, most recent first."""

    gateway: PersistenceGateway
    scope: TenantScope

    async def recent(
        self,
        *,
        since: datetime | None = None,
        limit: int = MAX_AUTONOMY_PREVIEW_ACTIONS,
    ) -> tuple[RecordedAction, ...]:
        """Return the actions decided since ``since``, most recent first."""
        async with self.gateway.begin(self.scope) as uow:
            events = await uow.audit.query(
                action=AUTONOMY_AUDIT_ACTION_DECISION,
                resource_kind=AUTONOMY_AUDIT_RESOURCE_KIND,
                since=since,
                limit=limit,
            )
        return recorded_actions(events)


def recorded_actions(events: Sequence[AuditEvent]) -> tuple[RecordedAction, ...]:
    """Return the actions ``events`` describe, dropping any that cannot be read."""
    found: list[RecordedAction] = []
    for event in events:
        action = action_of(event.detail)
        if action is None:
            _LOG.info("autonomy.history_row_skipped", event_id=event.event_id)
            continue
        found.append(RecordedAction(action=action, at=event.occurred_at))
    return tuple(found)


def action_of(detail: Mapping[str, Any]) -> ProposedAction | None:
    """Return the action a decision's audit detail describes, or ``None``."""
    record = detail.get(AUTONOMY_DETAIL_ACTION)
    if not isinstance(record, Mapping):
        return None
    subjects = tuple(
        Subject(
            resource_id=str(entry.get("resource_id", "")),
            kind=str(entry.get("kind", "")),
            labels={str(name): str(value) for name, value in (entry.get("labels") or {}).items()},
            team_node_id=str(entry.get("team_node_id", "")),
        )
        for entry in record.get("subjects", ())
        if isinstance(entry, Mapping) and entry.get("resource_id")
    )
    if not subjects:
        return None
    try:
        return ProposedAction(
            action_id=str(record.get("action_id", "")),
            capability=str(record.get("capability", "")),
            subjects=subjects,
            risk_class=risk_class_of(str(record.get("risk_class", ""))),
            has_rollback_plan=bool(record.get("has_rollback_plan", False)),
            requester=str(record.get("requester", "")),
            intent=str(record.get("intent", "")),
            run_id=str(record.get("run_id", "")),
            team_node_id=str(record.get("team_node_id", "")),
            operation=str(record.get("operation", "")),
        )
    except ValueError:
        return None


__all__ = [
    "DecisionHistory",
    "action_of",
    "recorded_actions",
]
