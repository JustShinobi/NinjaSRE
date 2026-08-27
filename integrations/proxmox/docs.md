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

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `endpoint` | A node's address, port included — https://pve01.internal:8006. Any node will do: the API answers cluster-wide questions from whichever one is asked. | — | [Proxmox VE Administration Guide](https://pve.proxmox.com/pve-docs/) |
| `api_token` | Proxmox API token as one line, exactly as the header wants it: `user@realm!tokenid=secret` | Sys.Audit on `/`, VM.Audit on `/vms` and Datastore.Audit on `/storage` — granted together by the `PVEAuditor` role on `/` | [User Management](https://pve.proxmox.com/pve-docs/chapter-pveum.html) |
| `username` | Login name with its realm, such as `ninjasre@pve`. Only for deployments that cannot issue an API token. | — | [User Management](https://pve.proxmox.com/pve-docs/chapter-pveum.html) |
| `password` | Password for the ticket login. Exchanged for a two-hour ticket on the proxy side and never read here. | Same as `api_token`, for the login name this password authenticates | [User Management](https://pve.proxmox.com/pve-docs/chapter-pveum.html) |
| `ticket` | The short-lived ticket the proxy exchanged the password for. Written by the refresher, never by an operator. | The same access as the login (`username` and `password`) that was exchanged for it — session material the proxy writes, never a scope an operator sets | [User Management](https://pve.proxmox.com/pve-docs/chapter-pveum.html) |
| `csrf_token` | The CSRF prevention token that accompanies a ticket. Written by the refresher, never by an operator. | The same as `ticket` — session material, not an operator-set scope | [User Management](https://pve.proxmox.com/pve-docs/chapter-pveum.html) |

Sources: all six from Proxmox's own Administration Guide, current as of this
feature. `ticket` and `csrf_token` are session material Proxmox itself issues
at login rather than a value an operator requests, so their minimum permission
is the login that produced them, not an invented scope.

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
explicit, audited setting. A default Proxmox install is self-signed — that is
the ordinary case, not an eccentricity — so this is a decision almost every
deployment has to take, and the whole difficulty is that the insecure option is
also the convenient one.

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

#### Which form to pick

**A pinned fingerprint, for a single node and for any cluster reached by IP
address.** The pin *replaces* the identity check rather than adding to it, so it
is the form that works when the certificate names `pve01` and the integration is
pointed at `10.20.20.9`. A cluster declares one fingerprint per node in a single
declaration, because each node presents its own certificate.

**A supplied certificate, for a cluster reached by name.** Proxmox mints one
authority per cluster and issues each node a certificate from it, so one paste
covers every node — and chain building, expiry and hostname checking all stay
on, which is why it is the stronger of the two wherever it fits.

Try the fingerprint first. If you supply the authority for a cluster you address
by IP, the chain will validate and the name will not match, and the refusal says
exactly that.

#### Declaring it without editing code

The forms above are the vocabulary. A running deployment declares them through
the API, and the declaration lands in the configuration tree beside the address
the integration is pointed at:

```http
PUT /v1/integrations/proxmox/trust
```

```json
{ "fingerprints": ["AB:CD:…", "EF:01:…"] }
```

Colons are optional — both spellings a tool produces are accepted. The other two
forms are `{"certificate_pem": "<PEM-encoded certificate>"}` and
`{"unverified_reason": "…"}`. There is no field in that body that turns
verification off: the insecure form is reached by writing down *why*, and a
reason that is present and blank is refused naming the reason.

A private key pasted where the certificate goes is refused by name, and the
value is not stored anywhere — not in the document, not in the log, not in the
audit event.

**The proxy picks it up without a restart.** The declaration is applied at the
credential proxy's egress, which is where the TLS handshake happens, and the
same cycle that rebuilds the egress allow-list from the configuration tree
rebuilds this. It rebuilds rather than accumulates, so a declaration you remove
stops applying on the next cycle instead of outliving the decision that made it.

#### Which permission each form needs

| Form | Permission |
|---|---|
| Pinned fingerprint | `integration.manage` — the same one that writes the address |
| Supplied certificate | `integration.manage` |
| Not verifying | `integration.manage` **and** `integration.trust_unverified`, held by an administrator and above |

Pinning and supplying do not weaken anything: they point verification at a
narrower anchor than the system trust store, which is strictly stronger for a
host that issues its own certificate. Requiring an administrator for those would
push an operator towards the worse option precisely because the better one is
out of reach. Not verifying is the one operation that gives up a guarantee and
returns nothing but convenience, so it has a gate an audit review can tell apart
from editing configuration.

A request without the dedicated permission is refused naming it, and **nothing
is written** — the declaration is validated and authorised before the document
is touched.

#### What gets recorded

Writing a declaration appends one audit event: who, when, which integration,
which addresses, which form, the fingerprints when there are any, and the reason
when there is one. The identity is the authenticated principal and the instant
is the server's — a value sent in the request body for either is discarded
before anything is validated.

Every credential resolution afterwards carries two more fields: which form was
in force, and the fingerprint when the form is a pin. On a refusal the same line
records the fingerprint that was actually *presented*, which is the fact
somebody looking into it needs.

No certificate material reaches any of this. A fingerprint may — it is the
public half's digest, it is not a secret, and it is exactly what you compare
against what the node shows you.

#### Trust is scoped to an address, never to the vendor

A declaration authorises the addresses it names and no others. Move the
integration to a different address and the declaration made for the old one
stops applying; the new address is refused for its certificate until a decision
covers it. A supplied authority is the one thing that spreads, and only as far
as the certificates it signed — which for a cluster is the whole cluster, and is
a consequence of your having supplied that authority rather than an implicit
extension.

#### When the node's certificate changes

A reinstall, a renewal, or somebody in the middle of the path. If you pinned a
fingerprint, the call is **refused**, and the refusal carries both fingerprints
labelled as expected and observed.

Nothing else happens. There is no fall back to the system trust store, no fall
back to not verifying, and the new fingerprint is never adopted automatically —
a pin that updates itself when it does not match is a decorative field, and a
replaced certificate is the exact event it exists to catch. Compare the observed
fingerprint against what the node shows at Datacenter → <node> → System →
Certificates, and if the change was legitimate, declare the new value the same
way you declared the first: same permission, same audit record.

#### The three refusals, and the one that is not about certificates

A refused certificate is its own kind of failure, and it says which certificate:

- **not trusted** — nothing declared what to accept at this address; the message
  carries the fingerprint that was presented and where to declare it;
- **pin broken** — a fingerprint is declared and a different one arrived; the
  message carries both, labelled;
- **name does not match** — the chain validated against what you supplied and the
  certificate does not name the address you configured; the message carries the
  address and the names the certificate carries.

None of the three is the message for a host that did not answer, and that one is
unchanged and mentions no certificate. An operator sent to check a network
because of a certificate finds the network correct and concludes the product is
broken, which is half the cost of the original defect.

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
