"""Proxmox Backup Server's agent-callable capability: is the backup a restore?

One tool, because there is one question. Everything a Backup Server reports —
usage, snapshots, verification, garbage collection, pruning — is an input to
"could this actually be restored", and splitting it into five capabilities would
make an investigation ask five questions to answer one.
"""

from __future__ import annotations

from integrations.proxmox_backup_server.tools.datastore_health import (
    proxmox_backup_server_datastore_health,
)

__all__ = ["proxmox_backup_server_datastore_health"]
