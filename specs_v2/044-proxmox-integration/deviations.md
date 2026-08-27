# Deviations — 044 Proxmox VE Integration

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. Tools and a methodology skill were shipped, and the spec calls them out of scope

**Planned.** "Out of scope — Investigation tools and skills: feature 045."

**Done.** `integrations/proxmox/tools/` ships three read capabilities —
`proxmox_cluster_health`, `proxmox_storage_pressure`, `proxmox_protection_gaps`
— plus `capabilities/skills/proxmox/SKILL.md`, and the Backup Server package
ships one capability and one skill of its own.

**Why.** The seven-artefact parity check is part of `make verify`, and two of
the seven are `tools/` and `SKILL.md`. `integrations/_catalogue/validation.py`
does not treat an empty `tools/` package as a tools package — deliberately,
because "counting it would let an integration reach parity while declaring
nothing the agent can call" — so a Proxmox package with no capability fails the
gate the day it lands. The definition of done requires `make verify` green.

There were three ways out and two of them are worse. Declaring Proxmox a
`_catalogue/gaps.py` entry would announce an integration that is *not* reachable
while shipping one that is. Relaxing the parity rule for one vendor would remove
the check that makes the other eighty-three complete. So the third: ship the
smallest set of capabilities that are honestly *this* feature's reads.

**What was kept out.** Each of the three answers a question this feature already
had to read for — quorum arithmetic, three-level storage fill, backup coverage —
and none of them is investigative methodology in the sense feature 045 means. No
tool here reads a guest's configuration, walks a task log, or sequences an
investigation; those, and the skills that direct them, remain 045's.

---

## 2. A permission's contract shape is not the same as a privilege's, so both exist

**Planned.** T-001 asks for "required privileges per capability"; T-036 and T-037
ask for privilege sufficiency reported for read and write separately, with a
missing privilege named alongside the path it was needed for.

**Done.** Two declarations rather than one. `privileges.py` holds
`READ_PRIVILEGES` and `WRITE_PRIVILEGES` as `RequiredPrivilege` values carrying a
Proxmox **path**, and `privilege_report` reads `/access/permissions` to produce
the read/write verdict. `verifier.py` separately declares three
`RequiredPermission` values, which is the framework's own type, and one probe
each.

**Why.** `RequiredPermission` has no path field, and the contract suite requires
every declared permission to be probed and to name capabilities that exist. A
path bolted into the permission's `name` string would satisfy the framework and
would leave nothing able to *compute* sufficiency — `_covers` needs the path as
data, because `Sys.Audit` on `/` legitimately satisfies a requirement on
`/nodes` and a string comparison would report a correctly-configured
administrator's token as insufficient.

The two are not redundant. The privilege listing explains a refusal; the probe
proves the call is permitted **through this deployment's proxy**, which is a
stronger statement and one the listing cannot make.

---

## 3. The ticket refresher is in `platform/`, not in `integrations/proxmox/`

**Planned.** The plan's constitution check says this integration "depends on
`integrations/_base/` and `config/` only". T-003 asks for ticket and CSRF
authentication with refresh before expiry.

**Done.** `platform/credentials/proxy/tickets.py` holds
`ProxmoxTicketRefresher`, with `tests/unit/platform/credentials/test_proxmox_ticket_refresh.py`
beside it. `integrations/proxmox/schema.py` declares `ticket_rule_for(...)` with
`refreshable=True` and the two injections the ticket path needs.

**Why.** Exchanging a username and password for a ticket is itself an
authenticated call, and the thing it authenticates with is the password. A
client that could perform the exchange would hold a credential *longer-lived*
than the two-hour ticket it obtained — the exact inversion Article IV exists to
prevent, and strictly worse than holding an API token.

`platform/credentials/proxy/signing/vendor.py` is the precedent: AWS SigV4,
Azure's shared key and Google's access token all live on the proxy side and all
name their vendor, for the same reason. The plan's "`_base/` and `config/` only"
describes the *client*; the schema module already imports
`platform.credentials.proxy.injection`, as every vendor's does.

---

## 4. The API token is one credential field, not two

**Planned.** Not specified. FR-001 requires token authentication supporting both
privilege-separated and non-separated tokens.

**Done.** One `api_token` field holding `user@realm!tokenid=secret`, validated
by a pattern, injected as `Authorization: PVEAPIToken={value}`.

**Why.** Proxmox's web interface shows the token id and secret separately, so two
fields is the more natural setup form — but a composite header built from two
fields needs an injection type `platform/credentials/proxy/injection.py` does
not have, and adding one is a change to the tier-3 authentication surface every
other integration shares. The single-field form is also exactly what Proxmox's
own documentation puts in the header, so an operator can compare what they pasted
against the vendor's own `curl` example.

`docs.md` shows the joined form with the separator called out, because that is
the one thing an operator can get wrong here. The Backup Server package makes the
same choice and warns about its different separator (`:` rather than `=`).

**A consequence worth stating.** The privilege-separation flag is not modelled as
a field, because it is not one: a separated token sends identically and simply
holds fewer privileges, and `/access/permissions` reports the *effective* set
either way. FR-001's "MUST support both" is therefore satisfied by there being
nothing to branch on.

---

## 5. The token pattern is written with positive character classes

**Planned.** Nothing about pattern syntax.

**Done.** `[A-Za-z0-9_.\-]+@[A-Za-z0-9_.\-]+![A-Za-z0-9_\-]+=[A-Za-z0-9\-]+`
rather than the tighter `[^@\s!]+@[^@\s!]+![^\s=]+=\S+`, and no `min_length`
beside it.

**Why.** `tests/harness/backends/base.py` generates a scenario credential *from
the declared pattern*, so that contributing a scenario for a new integration
means writing no credential. Its generator cannot satisfy a negated class — it
produced `'@@@! =a'` for the tighter pattern — and `min_length` then rejects the
short value it does produce.

The repository-wide harness is right and the pattern was the thing to change: a
declaration that only one consumer can read is a declaration that will break the
next consumer too. The positive form still rejects every mistake the tight one
did, including the common one of pasting the secret alone.

---

## 6. Three kinds are registered by the integration, and `service` is not emitted

**Planned.** FR-026 lists the kinds discovery produces: cluster, node, virtual
machine, container, datastore, storage pool, backup job, replication job, and
physical disk.

**Done.** Exactly those nine. `platform/estate/kinds.py` already declares six of
them; `integrations/proxmox/discovery.py` declares `storage_pool`,
`replication_job` and `physical_disk` as `PROXMOX_KINDS`, which a composition
root registers onto the core registry.

**Why.** A thin pool is not a universal concept and a core model that grew a
field per vendor would stop being a model. Registering from the integration is
the extensibility path the kind registry was built for, and the test that proves
it registers cleanly onto `core_registry()` is the one that would catch a name
colliding with a future core kind.

`service` is a core kind this integration deliberately does not emit. Proxmox
knows what a guest is; what runs *inside* a guest is somebody else's read, and
inventing a service per container from its hostname would populate the estate
with resources nothing can refresh.

---

## 7. The reference cluster's state is the test corpus, and it is not a fixture directory

**Planned.** T-040 asks for "recorded fixtures covering healthy, degraded,
no-quorum, node-down and single-node-no-cluster states".

**Done.** `tests/support/proxmox.py` — a module, not a tree of JSON files —
holding all five states, keyed by API path.

**Why.** Keyed by path rather than ordered as a queue, so that changing the order
a client makes its calls in does not require rewriting every fixture; and a
module rather than files because the five states share ninety per cent of their
content and the differences are the point. `recorded(ClusterState.DEGRADED)`
differs from `HEALTHY` in two values, and in a file tree that would be two
near-identical directories whose divergence nobody could see.

Every number in it is from the survey: two thin pools at 84.46% and 72.38% data,
a plex volume at 99.60%, `TeraChad` at 96%, a disabled backup job covering the
node that carries almost everything, and no replication jobs at all.

---

## 8. `supplementary.py` exists although this feature reads nothing through it

**Planned.** FR-013c through FR-013e require failed `systemd` units, bridge state
and thin-pool metadata to be observable, to arrive through feature 047's
observability bridge, and to be reported as **unavailable** where no exporter
publishes them.

**Done.** `integrations/proxmox/supplementary.py` takes whatever the bridge
published — a mapping, keyed by node — and returns three `Reading` values.
Feature 047 does not exist yet, so every deployment today gets three unavailable
readings naming the publisher that would supply them.

**Why not defer it to 047.** The requirement is not "read these"; it is "never
report these as healthy when nobody is looking". A feature that shipped the
Proxmox integration with the three readings simply *absent* would ship an estate
that answers "no failed units" for a node nothing watches — which is the exact
failure FR-013e was written to prevent, and which would be invisible until 047
landed. The shape is here, the absence is explicit, and 047 fills the mapping.

`health_verdict()` returns `UNKNOWN` rather than `HEALTHY` when nothing is
published, and a structural test asserts that no module in this package can reach
a shell (FR-013d).

---

## 9. Five modules the plan's phases do not name

The plan lists eight phases and no file tree. These exist and are worth naming:

| Module | Why |
|---|---|
| `models.py` | The parsed readings. In `client.py` they would make one 1,400-line file out of two concerns — what Proxmox answers, and what the answer means. `Reading[T]` in particular is the type that keeps "no ZFS here", "the node did not answer" and "nothing publishes this" apart, and it is used by four other modules. |
| `endpoints.py` | Multi-endpoint failover (T-005). It is a state machine with one rule that matters — only reachability fails over — and it deserved a module rather than three methods on the client. |
| `identity.py` | FR-027. Eight identity functions and the creation-time discriminator. Written apart from discovery because the rename/migration/reuse properties are testable without a cluster and are the ones most likely to be broken by a later change. |
| `redaction.py` | NFR-003. Guest configuration masking, over the deployment's own ruleset plus the Proxmox keys that are secret by name whatever their value looks like. |
| `privileges.py` | See deviation 2. |

None of these changes what is built; they are where it lives.

---

## 10. `docs/` regenerated files changed

`docs/integrations-catalogue.md`, `docs/capabilities.md` and four pages under
`docs/site/` are generated from the declarations and are checked by
`make check-integration-docs` and `make check-docs`. Adding two integrations and
four capabilities changes them. They were regenerated with
`python -m tools.generate_integration_docs`, `python -m tools.generate_capability_docs`
and `python -m tools.generate_docs`, not edited.

---

## Not deviations, recorded because they look like they might be

- **`await_task` sleeps between polls.** T-006 forbids a Proxmox-specific retry
  implementation and the structural test enforces it — but waiting between polls
  of a long-running task is not retry. It is what "report a task still running
  rather than waiting indefinitely" is made of. The banned list is a second
  backoff schedule, a second retryable set and a second pagination walk; the test
  says so.
- **`cluster_status()` treats a lost quorum as a successful read.** That is the
  plan's own decision — "quorum state is a fact, not an error" — and the read
  path is unchanged from every other read. Only what is *reported* differs.
- **Discovery reads each guest's configuration.** Fifty extra calls per sweep,
  which the plan's risk section anticipated: "mitigated by including a
  creation-time discriminator in the identity, tested explicitly". The declared
  budget accounts for it (`MAX_SWEEP_CALLS = 150`, measured at 66 for the
  reference shape) and the benchmark fails on a change that adds a second
  per-guest read.
- **A datastore visible from two nodes is two resources.** Deliberate, and the
  spec's edge case list asks for it. One record would have to choose which
  node's view of a share to believe, and on the reference cluster the two views
  disagree — that is what an `unknown` datastore on one node and `available` on
  another means.
- **`InventorySource` declares `max_provider_calls=1` while making none.** A
  source declaring zero would be a source the sweep cannot budget for, and the
  declaration's floor is one.
