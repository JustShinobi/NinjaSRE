"""Proxmox Backup Server's API, over the proxy, holding no credential.

Four readings, and the order below is the order they answer "is this backup
actually going to restore".

**Datastore usage.** How full the store is, which is the only one of the four
most deployments watch.

**Snapshots.** What is retained per backup group, so "there is a backup" can be
replaced by "there is a backup of *this* guest from *this* time".

**Verification.** Backup Server can re-read a snapshot's chunks and confirm they
are intact. An unverified snapshot is a file; a verified one is a restore. A
store whose verification job has never run is the case worth reporting, because
it looks identical to a store whose verification passes.

**Garbage collection and pruning.** A store that has not garbage-collected is a
store whose usage figure is about chunks nothing references any more, and a
prune that is failing is a store that will fill up on a schedule.

Every method is a ``GET``. Pruning and garbage collection are operations, not
reads, and they are not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.pagination import EndpointPagination, PaginationStyle
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.proxmox_backup_server.schema import DEFAULT_HOST, INTEGRATION, base_url

#: How many snapshots one call returns. A datastore holding a year of nightly
#: backups for eighty guests holds more than anything should read at once, and
#: the recent ones are the ones that answer whether a restore is possible.
MAX_SNAPSHOTS: Final = 200

#: Backup Server answers its snapshot listing in full and takes a backup group
#: as the narrowing parameter rather than a cursor. Declared as offset so the
#: catalogue records that the narrowing exists and is bounded.
PAGINATION: Final[tuple[EndpointPagination, ...]] = (
    EndpointPagination(
        endpoint="snapshots",
        style=PaginationStyle.OFFSET,
        parameter="start",
        page_size_parameter="limit",
        page_size=MAX_SNAPSHOTS,
    ),
)


class ProxmoxBackupServerClient(IntegrationClient):
    """Proxmox Backup Server reads, reached through the credential proxy."""

    integration = INTEGRATION

    __slots__ = ("_host",)

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        host: str = DEFAULT_HOST,
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url(host),
            retry=retry,
        )
        self._host = host

    @property
    def host(self) -> str:
        """Return the Backup Server this client reads."""
        return self._host

    async def _read(self, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        """Return the ``data`` a Backup Server endpoint answered with."""
        answer = (await self.get(path, params=params)).json()
        if not isinstance(answer, dict) or "data" not in answer:
            raise IntegrationError(
                f"{INTEGRATION} answered {path} with a body that is not a Proxmox envelope",
                integration=INTEGRATION,
                reason=IntegrationErrorReason.UPSTREAM_ERROR,
            )
        return answer["data"]

    async def read_response(
        self, path: str, *, params: Mapping[str, str] | None = None
    ) -> ClientResponse:
        """Return one endpoint's answer without interpreting the envelope.

        What a permission probe wants. A probe asks whether the call is
        *permitted*, not what came back, and insisting on a well-formed Proxmox
        envelope would turn a successful authorisation check into a parse error
        the moment a deployment put a reverse proxy in front of its Backup Server.
        """
        return await self.get(path, params=params)

    async def ping(self) -> ClientResponse:
        """Read the version — the cheapest authenticated call the server offers."""
        return await self.get("/version")

    async def datastores(self) -> tuple[Mapping[str, Any], ...]:
        """Return every datastore this server holds, with its usage."""
        return _records(await self._read("/status/datastore-usage"))

    async def datastore_status(self, datastore: str) -> Mapping[str, Any]:
        """Return one datastore's own status, including its estimated full date."""
        return _record(await self._read(f"/admin/datastore/{datastore}/status"))

    async def snapshots(
        self, datastore: str, *, backup_type: str = "", backup_id: str = ""
    ) -> tuple[Mapping[str, Any], ...]:
        """Return the snapshots a datastore retains, newest first.

        Narrowed by backup group where one is given, because a store holding a
        year of nightly backups for eighty guests answers this with more than
        anything should read at once.
        """
        params: dict[str, str] = {}
        if backup_type:
            params["backup-type"] = backup_type
        if backup_id:
            params["backup-id"] = backup_id
        records = _records(
            await self._read(f"/admin/datastore/{datastore}/snapshots", params=params)
        )
        return records[:MAX_SNAPSHOTS]

    async def verification_state(self, datastore: str) -> tuple[Mapping[str, Any], ...]:
        """Return each snapshot's verification outcome.

        A snapshot with no verification record is not a snapshot that failed
        verification — it is one nobody has checked, which is a different and
        commonly worse answer.
        """
        return tuple(
            {
                "snapshot": f"{row.get('backup-type')}/{row.get('backup-id')}/{row.get('backup-time')}",
                "state": _record(row.get("verification")).get("state", "unverified"),
                "verified_at": _record(row.get("verification")).get("upid", ""),
            }
            for row in await self.snapshots(datastore)
        )

    async def garbage_collection(self, datastore: str) -> Mapping[str, Any]:
        """Return when this datastore last collected garbage, and what it freed."""
        return _record(await self._read(f"/admin/datastore/{datastore}/gc"))

    async def prune_state(self, datastore: str) -> tuple[Mapping[str, Any], ...]:
        """Return the retention this datastore prunes to, and what the last run kept."""
        return _records(await self._read("/config/prune", params={"store": datastore}))


def _records(payload: Any) -> tuple[Mapping[str, Any], ...]:
    """Return ``payload`` as a tuple of records, whatever shape it arrived in."""
    if isinstance(payload, list):
        return tuple(row for row in payload if isinstance(row, dict))
    if isinstance(payload, dict):
        return tuple(value for value in payload.values() if isinstance(value, dict))
    return ()


def _record(payload: Any) -> Mapping[str, Any]:
    """Return ``payload`` as one record, or an empty one."""
    return payload if isinstance(payload, dict) else {}


__all__ = ["MAX_SNAPSHOTS", "PAGINATION", "ProxmoxBackupServerClient"]
