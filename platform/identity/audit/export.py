"""Getting the audit trail out, in a shape a SIEM ingests without being told about us.

Audit records are exempt from every retention sweep, which means the table only
grows. That is the correct trade — an audit log with a delete path is not
evidence — but it is only survivable if an operator can move history somewhere
cheaper, and "somewhere cheaper" is almost always the SIEM they already run.

Newline-delimited JSON, one flat object per record. No envelope, no batching
wrapper, no vendor schema: Splunk, Elastic, Loki, and a shell pipeline all read
it, a partially written file is still valid up to the last newline, and it
streams — which matters, because the export this exists for covers months and
the machine running it should never hold that in memory.

The record shape is ``recorder.as_record``, shared with the durable fallback, so
what an operator recovers after an outage merges with what they exported before
it instead of being a second format they have to reconcile.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO

from config.constants.security import AUDIT_EXPORT_CONTENT_TYPE, AUDIT_EXPORT_PAGE_SIZE
from platform.identity.audit.recorder import as_record
from platform.persistence.ports import AuditEvent, PersistenceGateway, TenantScope

#: The finest interval two records can be apart. The cursor steps by this so the
#: exclusive upper bound of one page includes the instant the previous page
#: ended on, which is what stops a record sharing that instant being skipped.
_TIMESTAMP_RESOLUTION = timedelta(microseconds=1)

#: What an HTTP surface labels the response. Named here rather than at the route,
#: because the format is a property of the export and not of one transport.
CONTENT_TYPE = AUDIT_EXPORT_CONTENT_TYPE


@dataclass(frozen=True, slots=True)
class AuditExport:
    """Streams a tenant's audit trail as newline-delimited JSON.

    Paged, and the paging is by time rather than by offset. An offset walk over
    a table that is being appended to skips records: rows arriving between two
    pages shift every subsequent offset by one, and the ones that shift past the
    boundary are never read. Walking backwards through ``occurred_at`` cannot
    skip a record, because a record's timestamp does not change after it is
    written — which is a guarantee this table has and most do not.

    The one bound worth stating: more than ``page_size`` records sharing a single
    microsecond would end the walk early. Timestamps here come from the
    recorder's clock at microsecond resolution, so that is a hundred audited
    actions in the same tick; the alternative — a keyset cursor over
    ``(occurred_at, event_id)`` — is a port method this export does not justify.
    """

    gateway: PersistenceGateway
    page_size: int = AUDIT_EXPORT_PAGE_SIZE

    async def events(
        self,
        scope: TenantScope,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> AsyncIterator[AuditEvent]:
        """Yield every event in the window, most recent first."""
        cursor = until
        seen: set[str] = set()
        while True:
            async with self.gateway.begin(scope) as uow:
                page = await uow.audit.query(since=since, until=cursor, limit=self.page_size)
            fresh = [event for event in page if event.event_id not in seen]
            if not fresh:
                return
            for event in fresh:
                seen.add(event.event_id)
                yield event
            # The window is half-open, so the next page's upper bound is the
            # oldest instant seen *plus one tick* — that keeps the boundary
            # instant in range, and ``seen`` is what stops the records on it
            # being emitted twice.
            cursor = fresh[-1].occurred_at + _TIMESTAMP_RESOLUTION

    async def write(
        self,
        scope: TenantScope,
        destination: IO[str],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Write the window to ``destination`` and return how many records it held."""
        written = 0
        async for event in self.events(scope, since=since, until=until):
            destination.write(_line(scope.org_id, event))
            written += 1
        return written

    async def lines(
        self,
        scope: TenantScope,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> AsyncIterator[str]:
        """Yield the export a line at a time, for a streaming HTTP response."""
        async for event in self.events(scope, since=since, until=until):
            yield _line(scope.org_id, event)


def _line(org_id: str, event: AuditEvent) -> str:
    """Return one record as a JSON object followed by a newline.

    Keys sorted, because a diff between two exports of the same window should be
    empty rather than a reordering nobody made.
    """
    return json.dumps(as_record(org_id, event), sort_keys=True) + "\n"


__all__ = ["CONTENT_TYPE", "AuditExport"]
