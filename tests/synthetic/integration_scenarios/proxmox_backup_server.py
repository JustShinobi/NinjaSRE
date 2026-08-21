"""Proxmox Backup Server, end to end: capability, client, proxy, token, server.

One scenario, carrying the thing that is easiest to lose: a store full of
snapshots that **nobody has verified**. Every layer between the API and the
finding could report "twelve snapshots" and stop, and twelve unverified snapshots
is a different answer from twelve verified ones — the first is twelve files and
the second is twelve restores.

The garbage-collection record is absent from the response on purpose. A store
that has never collected reports a usage figure about chunks nothing references
any more, and the honest reading of a missing record is "never run" rather than
"fine".
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

CREDENTIAL: Final[dict[str, str]] = {
    "api_token": "ninjasre@pbs!ninjasre:1a2b3c4d-5e6f-7890-abcd-ef1234567890",
}


def _envelope(payload: object) -> object:
    """Return ``payload`` wrapped the way every Proxmox endpoint answers."""
    return {"data": payload}


DATASTORE_HEALTH: Final = IntegrationScenario(
    key="proxmox-backup-server-datastore-health",
    integration="proxmox_backup_server",
    capability="proxmox_backup_server_datastore_health",
    arguments={"datastore": "remote-backup"},
    responses=(
        json_response(
            _envelope(
                {
                    "total": 8_001_000_000_000,
                    "used": 4_812_000_000_000,
                    "estimated-full-date": 1_790_000_000,
                }
            )
        ),
        json_response(
            _envelope(
                [
                    {
                        "backup-type": "ct",
                        "backup-id": "100",
                        "backup-time": 1_754_800_000,
                        "size": 96_000_000_000,
                    },
                    {
                        "backup-type": "ct",
                        "backup-id": "115",
                        "backup-time": 1_754_800_600,
                        "size": 6_100_000_000,
                    },
                ]
            )
        ),
        json_response(
            _envelope(
                [
                    {
                        "backup-type": "ct",
                        "backup-id": "100",
                        "backup-time": 1_754_800_000,
                    },
                    {
                        "backup-type": "ct",
                        "backup-id": "115",
                        "backup-time": 1_754_800_600,
                    },
                ]
            )
        ),
        json_response(_envelope({})),
        # The retention this store actually applies. A hypervisor job asking for
        # thirty copies on a store pruning to two keeps two, and only this
        # endpoint says which number wins.
        json_response(
            _envelope([{"id": "vault-prune", "store": "vault", "keep-last": 2}]),
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="unverified",
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (DATASTORE_HEALTH,)

__all__ = ["CREDENTIAL", "DATASTORE_HEALTH", "SCENARIOS"]
