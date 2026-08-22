# Proxmox VE

Reads a Proxmox Virtual Environment cluster whole: quorum, nodes, containers,
virtual machines, datastores, thin pools, backup jobs and replication.

**Reading and writing are separate clients, on purpose.** `ProxmoxClient` is
read-only and every method on it is a `GET`; `ProxmoxWriteClient` is the subclass
that adds the writes, and the only things that call it are remediation
capabilities running behind an approval gate with a rollback plan. A write
sitting among eighty reads is one typo away from being called by something that
thought it was reading, and the split is what stops that.

**Tested against Proxmox VE 8.4 and 9.2.** The paths this client uses are
identical across the 8 and 9 major series. The single statement of that lives in
`integrations/proxmox/schema.py` as `TESTED_VERSIONS`, and everything that reports
it reads that tuple.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `endpoint` | A node's address, port included — https://pve01.internal:8006 | no | yes |
| `api_token` | Proxmox API token as one line: user@realm!tokenid=secret | yes | yes (or `username`+`password`) |
| `username` | Login name with its realm, for the ticket path | no | no |
| `password` | Password for the ticket login | yes | no (or `api_token`) |

`endpoint` goes to the configuration tree rather than the vault — it is where
the credential proxy reads its egress allow-list from. The port, `8006`, is
part of the address rather than a separate setting, and the client appends
`/api2/json` itself, so the address to declare is the node's `https://` root
and nothing more.

### 1. Create an API token

In the Proxmox web interface: **Datacenter → Permissions → API Tokens → Add**.

- **User** — a dedicated user, not `root@pam`. Create one at
  **Datacenter → Permissions → Users** in the `pve` realm.
- **Token ID** — anything; `ninjasre` is a reasonable choice.
- **Privilege Separation** — leave it **checked**. A separated token holds only
  what is granted to the token itself, which is what makes step 2 meaningful.

Proxmox shows the secret exactly once. Paste it into NinjaSRE's `api_token`
field as **one line**:

```
ninjasre@pve!ninjasre=1a2b3c4d-5e6f-7890-abcd-ef1234567890
```

That is the format Proxmox's own `Authorization` header takes. Pasting the secret
alone is the commonest setup mistake and produces a 401 that reads like a revoked
token.

### 2. Grant the read privileges

**Datacenter → Permissions → Add → API Token Permission**, three times:

| Path | Role | Without it |
|---|---|---|
| `/` | `PVEAuditor` (or a role with `Sys.Audit`) | no cluster status, quorum, corosync configuration or cluster log |
| `/vms` | `PVEAuditor` (or a role with `VM.Audit`) | no guest status, configuration, snapshots or task history |
| `/storage` | `PVEAuditor` (or a role with `Datastore.Audit`) | no datastore status, contents or thin pools |

`PVEAuditor` on `/` covers all three by inheritance and is the simplest correct
grant. The table lists them separately because a deployment that wants the
narrowest possible token can grant exactly these.

**These are read-only privileges.** A token holding only them can enumerate the
whole estate and change nothing, which is the configuration this integration is
designed to be run with. Verification reports read and write sufficiency
separately, so a read-only token verifies as *sufficient* rather than as a
warning.

**A token that may also remediate needs more, and needs it deliberately.** The
write privileges are listed in `WRITE_PRIVILEGES` and reported by verification as
a separate answer, so granting them is a decision an operator makes having seen
what the token would then be able to do:

| Path | Privilege | What it allows |
|---|---|---|
| `/vms` | `VM.PowerMgmt` | start, stop, shut down, reboot, suspend and resume guests |
| `/vms` | `VM.Config.Options` | edit a guest's configuration, which is how an orphaned lock is cleared |
| `/vms` | `VM.Migrate` | move a guest to another node |
| `/vms` | `VM.Backup` | take a backup outside its schedule |
| `/storage` | `Datastore.AllocateSpace` | write that backup onto a datastore |
| `/storage` | `Datastore.Allocate` | remove a volume from a datastore |
| `/` | `Sys.Console` | change a high-availability resource, and run a replication job now |

Granting none of them leaves the deployment able to investigate and unable to
act, which is a supported posture and the default one.

### 3. Declare the endpoints

A Proxmox cluster is reachable through any of its nodes, and a configuration that
names one node becomes unreachable exactly when that node is the one that died.
Declare **every** node's address:

```python
from integrations.proxmox import rule_for, regions_for

rule = rule_for("pve01.lan.example", "pve02.lan.example")
regions = regions_for(hal9000="pve01.lan.example")
```

The addresses in the injection rule are also the egress allow-list: the proxy
will not let this integration reach a host that is not in it.

### 4. Decide about the certificate

Certificate verification is **on by default** and disabling it requires an
explicit, audited setting. Homelab Proxmox is almost always self-signed, so pick
one of the first two:

```python
from integrations.proxmox import CertificateTrust

# The node's certificate, copied from Datacenter → <node> → Certificates.
CertificateTrust.with_certificate(pem)

# Or its SHA-256 fingerprint, which the same screen shows.
CertificateTrust.pinned("AB:CD:…")

# Or, with a reason and a name attached to it, and an audit record produced:
CertificateTrust.unverified(reason="…", accepted_by="…")
```

There is no boolean that turns verification off. The management plane of a
hypervisor is the last place to teach an operator that certificate warnings are
noise: anything that can impersonate it can read every guest's configuration and
start, stop and reconfigure all of them.

### Ticket authentication, for deployments that cannot issue a token

Supply `username` and `password` instead of `api_token`, and use
`ticket_rule_for(...)` in place of `rule_for(...)`. The password is exchanged for
a two-hour ticket **on the proxy side**, and the rule declares itself refreshable
so the proxy renews it before expiry. No Proxmox code sees either the password or
the ticket.

Prefer a token where one can be issued. The ticket path exists because some
deployments genuinely cannot.

## What this reads

**Cluster** — status with quorum state, expected and current votes and per-node
membership; the cluster-wide resource list; corosync node and totem configuration;
the cluster log; high-availability resources, groups, manager status and fencing
state; cluster-wide backup job definitions.

**Nodes** — uptime, load, CPU, memory, swap, root filesystem, kernel and Proxmox
version; the storage list and per-datastore status and content; physical disks
with their SMART verdict; LVM-thin pools with **data and metadata percentages
reported separately**; each guest's own thin volume fill; ZFS pools where ZFS is
present; task history and one task's status and log; replication jobs; certificate
expiry; pending package updates; network interface configuration; time
synchronisation.

**Guests** — status, configuration, resource usage, lock state, HA membership,
snapshots and pending configuration changes, for containers and virtual machines
as **distinct kinds**; each guest's task history; and, where a QEMU guest agent
answers, the guest's own view of its filesystems.

**Backups** — backup task outcomes, retained contents per datastore, and each
guest's most recent successful backup.

## Limitations

**Three readings are not in the Proxmox API at all**: a node's failed `systemd`
units, whether its bridges are up, and an LVM thin pool's metadata percentage as
the node sees it. They are one SSH command away, and this integration is
deliberately forbidden a shell — a hypervisor client that could run arbitrary
commands on every node would hold more authority than every remediation
capability combined. They arrive instead as metrics the node publishes about
itself, through a node exporter with a textfile collector, and **where nothing
publishes them they are reported as unavailable rather than as healthy**.

**Ceph is not covered.** A two-node cluster cannot sensibly run it, and no
capability here depends on it.

**Nothing here decides to write.** Starting, stopping, migrating, backing up and
unlocking a guest are remediations with approval gates, declared risk classes and
rollback plans, and the decisions all live above this package. What is here is
the client that performs one once something else has decided — and every method
on it returns the Proxmox task identifier rather than a result, because the API
answering `200` means the task was accepted and not that it worked.

**Four things no write may ever do**, asserted over the whole write surface
rather than over a list of capability names: fence a node, force quorum, alter
corosync configuration, or restart `pveproxy`, `pvedaemon`, `pve-cluster` or
`corosync`. In a two-node cluster nothing available here distinguishes a dead
node from an unreachable one, and both wrong answers cost data.

**A declarative control plane's paths are never touched.** Where an operator runs
a GitOps control plane over `/etc/network/interfaces`, bridges or guest
configuration, those are read-only to this system. A second writer is how drift
becomes an outage.

## Rate limits and budgets

A Proxmox node's API is a Perl daemon on somebody's own hardware rather than a
cloud endpoint, so the declared rate limit is **120 calls a minute** and discovery
sweeps every **five minutes**. One full sweep of a two-node cluster with fifty
guests costs about 66 calls — two cluster-wide, six cluster detail, four per node
and one per guest — against a declared ceiling of 150.

The per-guest call is what reads each guest's creation time, which is what stops a
reused VMID inheriting the history of the guest that previously held that number.

## The operator's own inventory

Where an operator already maintains a schema-validated inventory declaring each
node's role and each guest's expected state, it can be registered as a **second
source** for the same resources. The two are reconciled to one record, both values
are retained where they disagree, and the disagreement becomes a signal — which is
exactly what a drift detector needs and what neither source can produce alone.
