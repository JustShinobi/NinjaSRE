"""Writing the record: who, as whom, from where, and what happened.

Two decisions shape this module.

**Attribution comes from the context, never from the caller.** ``record`` takes
an ``AuditContext`` and a payload, and the context wins every key they share. A
record whose ``real_principal_id`` came out of a request body is a record an
attacker writes, and the only way to make that impossible is for the caller to
have no say.

**A failed audit write is a serious error, not a logged warning**. The
action being audited has usually already happened — the configuration is
changed, the remediation has run — so silently proceeding would leave a system
that did something with no record that it did. Instead the event goes to a
durable file, an alert is raised, and the caller is told. All three: the file so
the record survives, the alert so somebody knows, the exception so the caller
does not report success it cannot substantiate.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from config.constants.config_service import (
    CONFIG_AUDIT_ACTION_CLEAR,
    CONFIG_AUDIT_ACTION_POLICY,
    CONFIG_AUDIT_ACTION_SET,
    CONFIG_AUDIT_ACTION_TEMPLATE,
)
from config.constants.security import (
    AUDIT_DETAIL_BREAK_GLASS,
    AUDIT_DETAIL_IMPERSONATED_NODE,
    AUDIT_DETAIL_IMPERSONATED_PRINCIPAL,
    AUDIT_DETAIL_REAL_PRINCIPAL,
    AUDIT_DETAIL_SOURCE_ADDRESS,
    AUDIT_FALLBACK_FILENAME,
    AUTH_AUDIT_ACTION_DENIED,
    AUTH_AUDIT_ACTION_SIGN_IN,
    AUTH_AUDIT_ACTION_SIGN_OUT,
    BREAK_GLASS_AUDIT_ACTION,
    CREDENTIAL_RESOLUTION_AUDIT_ACTION,
    IMPERSONATION_AUDIT_ACTION_END,
    IMPERSONATION_AUDIT_ACTION_START,
    NINJASRE_AUDIT_FALLBACK_PATH_ENV,
    PERMISSION_AUDIT_ACTION_DENIED,
    PERMISSION_AUDIT_ACTION_GRANT,
    PERMISSION_AUDIT_ACTION_REVOKE,
    SSO_AUDIT_ACTION_ACTIVATE,
    SSO_AUDIT_ACTION_GROUP_FALLBACK,
    SSO_AUDIT_ACTION_TEST,
    TOKEN_AUDIT_ACTION_EXPIRY_WARNING,
    TOKEN_AUDIT_ACTION_ISSUE,
    TOKEN_AUDIT_ACTION_REJECT,
    TOKEN_AUDIT_ACTION_REVOKE,
)
from platform.identity.errors import AuditWriteFailed
from platform.identity.impersonation import Impersonation
from platform.observability.logging import get_logger
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)

_LOG = get_logger(__name__)

#: Approvals and remediation land in features 015 and 017. Their action names are
#: reserved here so the vocabulary is complete on the day this feature ships:
#: the security suite asserts the dual-principal property *across every action
#: class*, and a class that only appears later would be a class nothing had
#: asserted about.
APPROVAL_AUDIT_ACTION_REQUEST: Final = "approval.request"
APPROVAL_AUDIT_ACTION_DECIDE: Final = "approval.decide"
REMEDIATION_AUDIT_ACTION_EXECUTE: Final = "remediation.execute"
REMEDIATION_AUDIT_ACTION_ROLLBACK: Final = "remediation.rollback"
CREDENTIAL_AUDIT_ACTION_WRITE: Final = "credential.write"
CREDENTIAL_AUDIT_ACTION_ROTATE: Final = "credential.rotate"

#: Every class of action that must be audited. A tuple rather than a
#: comment, because the security suite iterates it: a new class added without a
#: dual-principal path fails there rather than in a review nobody scheduled.
AUDITED_ACTIONS: Final[tuple[str, ...]] = (
    AUTH_AUDIT_ACTION_SIGN_IN,
    AUTH_AUDIT_ACTION_SIGN_OUT,
    AUTH_AUDIT_ACTION_DENIED,
    TOKEN_AUDIT_ACTION_ISSUE,
    TOKEN_AUDIT_ACTION_REVOKE,
    TOKEN_AUDIT_ACTION_REJECT,
    TOKEN_AUDIT_ACTION_EXPIRY_WARNING,
    CONFIG_AUDIT_ACTION_SET,
    CONFIG_AUDIT_ACTION_CLEAR,
    CONFIG_AUDIT_ACTION_POLICY,
    CONFIG_AUDIT_ACTION_TEMPLATE,
    CREDENTIAL_AUDIT_ACTION_WRITE,
    CREDENTIAL_AUDIT_ACTION_ROTATE,
    CREDENTIAL_RESOLUTION_AUDIT_ACTION,
    APPROVAL_AUDIT_ACTION_REQUEST,
    APPROVAL_AUDIT_ACTION_DECIDE,
    REMEDIATION_AUDIT_ACTION_EXECUTE,
    REMEDIATION_AUDIT_ACTION_ROLLBACK,
    IMPERSONATION_AUDIT_ACTION_START,
    IMPERSONATION_AUDIT_ACTION_END,
    BREAK_GLASS_AUDIT_ACTION,
    PERMISSION_AUDIT_ACTION_GRANT,
    PERMISSION_AUDIT_ACTION_REVOKE,
    PERMISSION_AUDIT_ACTION_DENIED,
    SSO_AUDIT_ACTION_TEST,
    SSO_AUDIT_ACTION_ACTIVATE,
    SSO_AUDIT_ACTION_GROUP_FALLBACK,
)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Who is acting, under what context switch, from where.

    Assembled once when a request is authenticated and carried down, rather than
    reconstructed at each write. Reconstructing it is how the impersonation half
    gets lost on the one path that mattered.
    """

    actor_kind: ActorKind
    actor_id: str
    impersonation: Impersonation | None = None
    break_glass: bool = False
    source_address: str | None = None

    def attribution(self) -> dict[str, Any]:
        """Return the detail keys that say who this was.

        The impersonation keys are absent rather than null when there is none.
        A reviewer's query for "everything done under impersonation" is then a
        key test, and an unimpersonated record is not padded with nulls somebody
        has to remember to exclude.
        """
        detail: dict[str, Any] = {AUDIT_DETAIL_REAL_PRINCIPAL: self.actor_id}
        if self.source_address is not None:
            detail[AUDIT_DETAIL_SOURCE_ADDRESS] = self.source_address
        if self.break_glass:
            detail[AUDIT_DETAIL_BREAK_GLASS] = True
        if self.impersonation is not None:
            detail[AUDIT_DETAIL_IMPERSONATED_NODE] = self.impersonation.node_id
            detail[AUDIT_DETAIL_IMPERSONATED_PRINCIPAL] = (
                self.impersonation.subject_principal_id or self.impersonation.node_id
            )
        return detail

    @property
    def is_impersonating(self) -> bool:
        """Return whether these actions carry a second principal."""
        return self.impersonation is not None


@dataclass(slots=True)
class AuditFallback:
    """Where an audit record goes when the database will not take it.

    A file, and newline-delimited JSON, for one reason each. A file because the
    fallback has to work in exactly the situation the datastore does not, and
    anything cleverer shares a failure mode with the thing it is backing up.
    NDJSON because a half-written file is still readable up to the truncation,
    which is the state this file is most likely to be found in.
    """

    path: Path

    @classmethod
    def from_environment(cls, *, default_directory: Path | None = None) -> AuditFallback:
        """Return the fallback an operator configured, or the default beside the app."""
        configured = os.environ.get(NINJASRE_AUDIT_FALLBACK_PATH_ENV)
        if configured:
            return cls(path=Path(configured))
        base = default_directory if default_directory is not None else Path.cwd()
        return cls(path=base / AUDIT_FALLBACK_FILENAME)

    def write(self, org_id: str, event: AuditEvent) -> None:
        """Append ``event`` to the fallback file.

        Failure here is logged and swallowed — and only here. This is the last
        line: raising would replace a recorded failure with an unrecorded one.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(as_record(org_id, event), sort_keys=True) + "\n")
        except OSError as failure:
            _LOG.error(
                "audit.fallback_unwritable",
                path=str(self.path),
                event_id=event.event_id,
                error=str(failure),
            )


@dataclass(slots=True)
class AuditRecorder:
    """Builds audit events from an acting context, and stores them.

    ``event`` and ``record`` are separate on purpose. Callers that need the
    record inside a transaction they already own build it and append it
    themselves; callers that just want it written use ``record``, which opens a
    transaction of its own — a write that was refused must still leave the
    record of why, and sharing a unit of work with the audited action means a
    rollback takes the record with it.
    """

    gateway: PersistenceGateway
    fallback: AuditFallback | None = None
    clock: Callable[[], datetime] = _utc_now
    #: Called when a write fails, after the fallback has been written. Raising an
    #: alert is a deployment concern; what this module guarantees is that
    #: something is called and that it is called with everything needed to act.
    on_failure: Callable[[str, AuditEvent, Exception], None] | None = None

    def event(
        self,
        context: AuditContext,
        *,
        action: str,
        resource_kind: str,
        resource_id: str,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        detail: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Return the event ``context`` would record for this action.

        The context's attribution is applied *after* the caller's detail, so a
        caller cannot overwrite who they are by putting a key in the payload.
        """
        payload: dict[str, Any] = dict(detail or {})
        payload.update(context.attribution())
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=self.clock(),
            actor_kind=context.actor_kind,
            actor_id=context.actor_id,
            action=action,
            resource_kind=resource_kind,
            resource_id=resource_id,
            outcome=outcome,
            detail=payload,
        )

    async def record(
        self,
        scope: TenantScope,
        context: AuditContext,
        *,
        action: str,
        resource_kind: str,
        resource_id: str,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        detail: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Build the event, store it, and return it as stored."""
        built = self.event(
            context,
            action=action,
            resource_kind=resource_kind,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail,
        )
        await self.append(scope, (built,))
        return built

    async def append(self, scope: TenantScope, events: Sequence[AuditEvent]) -> None:
        """Store ``events``, or fall back durably and raise."""
        if not events:
            return
        try:
            async with self.gateway.begin(scope) as uow:
                for event in events:
                    await uow.audit.append(event)
        except Exception as failure:
            self._fail(scope, events, failure)
            raise AuditWriteFailed(
                events[0].action,
                fallback_path=str(self.fallback.path) if self.fallback else None,
            ) from failure

    def _fail(self, scope: TenantScope, events: Sequence[AuditEvent], failure: Exception) -> None:
        """Write the fallback and raise the alert, in that order.

        The file first. An alert nobody is awake for is a notification; the file
        is the record, and it is the half that has to survive the process.
        """
        for event in events:
            if self.fallback is not None:
                self.fallback.write(scope.org_id, event)
            _LOG.error(
                "audit.write_failed",
                org_id=scope.org_id,
                event_id=event.event_id,
                action=event.action,
                error=str(failure),
            )
            if self.on_failure is not None:
                self.on_failure(scope.org_id, event, failure)


def as_record(org_id: str, event: AuditEvent) -> dict[str, Any]:
    """Return ``event`` as the flat mapping the fallback and the export both write.

    One function, so a record recovered from the fallback file is the same shape
    as one that came out of the export. An operator reconciling the two after an
    outage is doing enough work already.
    """
    return {
        "org_id": org_id,
        "event_id": event.event_id,
        "occurred_at": event.occurred_at.isoformat(),
        "actor_kind": event.actor_kind.value,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_kind": event.resource_kind,
        "resource_id": event.resource_id,
        "outcome": event.outcome.value,
        "detail": dict(event.detail),
    }


__all__ = [
    "AUDITED_ACTIONS",
    "AuditContext",
    "AuditFallback",
    "AuditRecorder",
    "as_record",
]
