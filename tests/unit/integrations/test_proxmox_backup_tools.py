"""Phase 4: recovery, which is a different question from health.

Every reading here exists because the obvious count answers yes when the truth is
no.

**Coverage counted against enabled jobs only.** A job that exists and is switched
off satisfies every inventory of "is there a backup job for this guest". The
reference cluster's whole-node job is in exactly that state, and counting job
membership turns "fifty-five guests are unprotected" into "fifty-five guests are
protected".

**Depth beside coverage.** Two retained copies and thirty are materially
different positions and read identically as "covered".

**No replication jobs at all, reported as a finding.** Anything that iterates
over existing jobs finds nothing to say. With guests on node-local storage that
absence is the single most consequential fact about the cluster's data posture.

**Exposure rather than outcome.** A replication job whose last run succeeded and
whose last run was a week ago reports success. What matters is the week.

**Unverified is not backed up.** A Backup Server snapshot nobody has verified is
a file. A store whose verification job has never run looks exactly like one whose
verification passes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import pytest

from integrations._base.access import IntegrationAccess, bind, restore
from integrations.proxmox.tools.backup_coverage import proxmox_backup_coverage
from integrations.proxmox.tools.backup_failures import proxmox_backup_failures
from integrations.proxmox.tools.replication_lag import proxmox_replication_lag
from integrations.proxmox_backup_server.tools.datastore_health import (
    proxmox_backup_server_datastore_health,
)
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, investigating

pytestmark = pytest.mark.unit

#: One Backup Server datastore, recorded. Two snapshots, neither verified, and a
#: garbage collection that has never run — which is the state a store nobody has
#: finished setting up is in, and which reads as healthy by usage alone.
_PBS: dict[str, Any] = {
    "/status/datastore-usage": [
        {"store": "vault", "total": 8_001_000_000_000, "used": 4_100_000_000_000}
    ],
    "/admin/datastore/vault/status": {
        "total": 8_001_000_000_000,
        "used": 4_100_000_000_000,
        "estimated-full-date": 1_790_000_000,
    },
    "/admin/datastore/vault/snapshots": [
        {
            "backup-type": "ct",
            "backup-id": "100",
            "backup-time": 1_754_800_000,
            "size": 42_000_000_000,
        },
        {
            "backup-type": "vm",
            "backup-id": "9000",
            "backup-time": 1_754_700_000,
            "size": 68_000_000_000,
            "verification": {"state": "ok", "upid": "UPID:pbs:verify"},
        },
    ],
    "/admin/datastore/vault/gc": {},
    "/config/prune": [{"id": "vault-prune", "store": "vault", "keep-last": 2, "schedule": "daily"}],
}


@dataclass(slots=True)
class _RecordedBackupServer:
    """The recorded Backup Server behind the proxy transport."""

    responses: dict[str, Any] = field(default_factory=lambda: dict(_PBS))

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Answer ``request`` from the recording."""
        path = urlsplit(request.url).path.removeprefix("/api2/json")
        payload = self.responses.get(path)
        if payload is None:
            return OutboundResponse(404, {}, b"not recorded")
        body = json.dumps({"data": payload}).encode("utf-8")
        return OutboundResponse(200, {"content-type": "application/json"}, body)


def _backup_server(**overrides: Any) -> _RecordedBackupServer:
    """Return the recorded Backup Server with ``overrides`` applied."""
    return _RecordedBackupServer(responses={**_PBS, **overrides})


# --- Coverage -----------------------------------------------------------------


async def test_coverage_is_counted_against_enabled_jobs_only() -> None:
    """The disabled whole-node job names every guest and protects none of them."""
    with investigating():
        result = await proxmox_backup_coverage()

    uncovered = {entry["guest"] for entry in result.value["guests_without_an_enabled_job"]}
    assert 9000 in uncovered, "a guest covered only by a disabled job read as covered"
    assert 137 in uncovered
    assert 100 not in uncovered


async def test_a_disabled_job_is_reported_as_the_dangerous_shape_it_is() -> None:
    with investigating():
        result = await proxmox_backup_coverage()

    jobs = {job["id"]: job for job in result.value["jobs"]}
    assert not jobs["backup-7d831311"]["enabled"]
    assert jobs["backup-7d831311"]["covers_everything"]
    assert "disabled" in result.evidence[0].summary.lower()


async def test_retention_depth_is_reported_beside_coverage() -> None:
    """Two retained copies and thirty read the same without this."""
    with investigating():
        result = await proxmox_backup_coverage()

    jobs = {job["id"]: job for job in result.value["jobs"]}
    assert jobs["backup-33b5e58a"]["retention_depth"] == 2
    assert jobs["backup-7d831311"]["retention_depth"] == 30


async def test_a_guests_last_successful_backup_is_reported_with_its_age_and_size() -> None:
    with investigating():
        result = await proxmox_backup_coverage()

    covered = {entry["guest"]: entry for entry in result.value["last_successful"]}
    assert covered[100]["age_seconds"] > 0
    assert covered[100]["size_bytes"] == 42_000_000_000


async def test_a_job_with_no_retention_rule_at_all_is_reported_as_depth_unknown() -> None:
    with investigating(
        responses={
            "/cluster/backup": [
                {
                    "id": "backup-nothing",
                    "enabled": 1,
                    "all": 1,
                    "schedule": "03:00",
                    "storage": "remote-backup",
                    "node": SECONDARY,
                }
            ]
        }
    ):
        result = await proxmox_backup_coverage()

    job = result.value["jobs"][0]
    assert job["retention_depth"] is None
    assert "no retention" in job["retention"].lower()


# --- Failures -----------------------------------------------------------------


async def test_a_failed_backup_is_reported_with_the_vendors_own_error_text() -> None:
    with investigating():
        result = await proxmox_backup_failures()

    failures = {entry["guest"]: entry for entry in result.value["failures"]}
    assert 129 in failures
    assert failures[129]["error"] == "job errors"


async def test_a_guest_whose_every_attempt_failed_is_separated_from_one_with_an_old_backup() -> (
    None
):
    with investigating():
        result = await proxmox_backup_failures()

    assert 129 in result.value["guests_with_no_successful_backup"]
    assert 100 not in result.value["guests_with_no_successful_backup"]


# --- Replication --------------------------------------------------------------


async def test_no_replication_job_at_all_is_reported_as_a_finding_in_its_own_right() -> None:
    """The reference cluster's state, and invisible to anything iterating over jobs."""
    with investigating():
        result = await proxmox_replication_lag()

    assert result.value["jobs"] == []
    assert result.value["no_replication_configured"]
    assert result.value["guests_on_node_local_storage"]
    assert "unrecoverable" in result.evidence[0].summary.lower()


async def test_a_job_that_reports_success_but_has_not_run_for_a_week_is_read_by_exposure() -> None:
    with investigating(
        responses={
            f"/nodes/{SECONDARY}/replication": [
                {
                    "id": "100-0",
                    "source": SECONDARY,
                    "target": PRIMARY,
                    "guest": 100,
                    "last_sync": 1_754_200_000,
                    "duration": 42.0,
                    "fail_count": 0,
                }
            ]
        }
    ):
        result = await proxmox_replication_lag()

    job = result.value["jobs"][0]
    assert job["last_run_succeeded"]
    assert job["recovery_point_exposure_seconds"] > 6 * 86_400
    assert "day" in job["recovery_point_exposure"]
    assert job["stale"]


async def test_the_exposure_is_stated_in_time_rather_than_as_a_timestamp() -> None:
    with investigating(
        responses={
            f"/nodes/{SECONDARY}/replication": [
                {
                    "id": "115-0",
                    "source": SECONDARY,
                    "target": PRIMARY,
                    "guest": 115,
                    "last_sync": 1_754_802_000,
                    "duration": 3.0,
                    "fail_count": 0,
                }
            ]
        }
    ):
        result = await proxmox_replication_lag()

    assert result.value["jobs"][0]["recovery_point_exposure"]
    assert not result.value["no_replication_configured"]


async def test_a_cluster_with_one_node_needs_no_replication_and_says_so() -> None:
    with investigating(ClusterState.SINGLE_NODE):
        result = await proxmox_replication_lag()

    assert result.value["no_replication_configured"]
    assert not result.value["recoverable_elsewhere_matters"]


# --- Proxmox Backup Server ----------------------------------------------------


async def test_an_unverified_backup_is_reported_as_unproven_rather_than_as_a_backup() -> None:
    transport = _backup_server()
    previous = bind(IntegrationAccess(transport=transport, org_id="acme", team_id="homelab"))
    try:
        result = await proxmox_backup_server_datastore_health("vault")
    finally:
        restore(previous)

    assert "ct/100/1754800000" in result.value["unverified_snapshots"]
    assert result.value["proven_snapshot_count"] == 1
    assert result.value["snapshot_count"] == 2
    assert "unproven" in result.evidence[0].summary.lower()


async def test_the_prune_rule_the_store_actually_applies_is_reported() -> None:
    transport = _backup_server()
    previous = bind(IntegrationAccess(transport=transport, org_id="acme", team_id="homelab"))
    try:
        result = await proxmox_backup_server_datastore_health("vault")
    finally:
        restore(previous)

    assert result.value["prune_rules"]
    assert result.value["prune_rules"][0]["keep-last"] == 2


async def test_a_store_that_has_never_collected_garbage_says_its_usage_is_not_current() -> None:
    transport = _backup_server()
    previous = bind(IntegrationAccess(transport=transport, org_id="acme", team_id="homelab"))
    try:
        result = await proxmox_backup_server_datastore_health("vault")
    finally:
        restore(previous)

    assert result.value["garbage_collection_status"] == "never run"
    assert "garbage collection" in result.evidence[0].summary.lower()
