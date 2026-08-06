"""The audit trail: writing it, guarding it, and getting it out.

Three modules, and the split is by guarantee rather than by convenience.
``recorder`` is the only way a record is written, so attribution cannot come
from a caller. ``guard`` is the executable form of "nothing may change one",
run at startup. ``export`` is how history leaves without any of it being
deleted, which is what makes an append-only table with no retention window
survivable.
"""

from __future__ import annotations

from platform.identity.audit.export import AuditExport
from platform.identity.audit.guard import assert_append_only, mutating_methods
from platform.identity.audit.recorder import (
    AUDITED_ACTIONS,
    AuditContext,
    AuditFallback,
    AuditRecorder,
    as_record,
)

__all__ = [
    "AUDITED_ACTIONS",
    "AuditContext",
    "AuditExport",
    "AuditFallback",
    "AuditRecorder",
    "as_record",
    "assert_append_only",
    "mutating_methods",
]
