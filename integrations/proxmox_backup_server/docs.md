# Proxmox Backup Server

Reads a Proxmox Backup Server's datastores: usage, snapshots, verification
outcomes, garbage-collection state and prune configuration. Nothing here writes.

**Tested against Proxmox Backup Server 3.4 and 4.0.** The single statement of that
lives in `integrations/proxmox_backup_server/schema.py` as `TESTED_VERSIONS`.

## Why this is a separate integration

Backup Server is usually a different machine, and it is the machine that has to
survive the cluster. A deployment that reached it with the hypervisor's credential
would have a backup server that stops being readable at exactly the moment the
cluster does. So it has its own host, its own token, its own egress allow-list and
its own verification — one more setup step, one fewer shared fate.

## Setup

### 1. Create an API token

**Configuration → Access Control → API Tokens → Add**, on a dedicated user rather
than `root@pam`.

Paste it into NinjaSRE's `api_token` field as one line:

```
ninjasre@pbs!ninjasre:1a2b3c4d-5e6f-7890-abcd-ef1234567890
```

**Note the colon.** Proxmox VE joins the token id and secret with `=`; Backup
Server joins them with `:`. A token pasted into the wrong integration
authenticates against neither, and the error each gives looks like a revoked
token rather than a format mistake.

### 2. Grant the permission

**Configuration → Access Control → Permissions → Add**, granting `Datastore.Audit`
on `/datastore`.

Backup Server grants `Datastore.Audit` **per datastore path**, so a token granted
on `/datastore/nightly` reads that store and reports nothing at all about the one
beside it. Granting on `/datastore` covers all of them; granting per store is
narrower and needs one entry each.

### 3. Declare the endpoint

```python
from integrations.proxmox_backup_server import rule_for

rule = rule_for("backup.lan.example")
```

The API listens on port 8007. The allow-list holds host names without ports,
because a port is not a security boundary.

## What this reads

- **Datastore usage** — how full each store is and when it is projected to fill.
- **Snapshots** — what is retained, per backup group, newest first and bounded.
- **Verification** — each snapshot's verification state. A snapshot with no
  verification record has not failed verification; nobody has checked it, which is
  a different and usually worse answer.
- **Garbage collection** — when it last ran and what it freed. A store that has
  not collected reports usage about chunks nothing references any more.
- **Prune configuration** — the retention each store prunes to.

## Limitations

- **Nothing is written.** Pruning, garbage collection and restore are operations
  with their own consequences and are not reads.
- **Tape is not covered.** No capability here depends on it.
- **A snapshot's contents are not read.** Listing what is inside a backup is a
  restore, not a read, and it costs what a restore costs.
