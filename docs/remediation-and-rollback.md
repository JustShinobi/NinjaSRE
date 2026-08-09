# Remediation and rollback

Everything NinjaSRE can change about production, and every mechanism that stops
it from doing so by accident.

The short version: **read-only is the default**. A capability that changes
anything needs an explicit human approval *and* a rollback plan recorded before
the change runs. Autonomy is something a team opts into, per action type, under
conditions, with a switch above it that stops everything in one action.

If you read nothing else, read [The kill switch](#the-kill-switch).

## Side-effect levels

Every capability declares what one invocation does to the world. The declaration
is not documentation — it is what decides whether a human is asked.

| Level | Meaning | Gated by default |
|---|---|---|
| `read` | Returns information and changes nothing | No |
| `read_sensitive` | Returns information that is itself sensitive | No |
| `write_reversible` | Changes something that can be put back | **Yes** |
| `write_irreversible` | Changes something that cannot be put back | **Yes** |
| `destructive` | Destroys data or capacity | **Yes** |

Three things follow from this table and are worth knowing:

- **A capability with no declared level cannot be built.** It is not defaulted to
  `read`; the build fails. A capability arriving from outside the repository
  with no declaration at all — a bridged protocol tool, say — is treated as a
  write.
- **An organisation can add to what it gates and cannot subtract.** Naming
  `read_sensitive` in your policy gates it as well; leaving `destructive` off
  your list does not un-gate it.
- **A deployment that has configured nothing gates every write.** Silence is not
  permission.

## What an approval shows

An approval prompt that says "restart checkout-api?" is a prompt people learn to
click, and approval fatigue is how this control fails in practice rather than in
theory. So a remediation request carries five things:

1. **The target and its current observed state**, read at the moment the request
   is raised. This is also what the request is fingerprinted against, so a
   change approved against a cluster that has since recovered is caught rather
   than applied.
2. **The blast radius** from the topology graph — what depends on this target,
   within three hops. If the graph cannot answer, the request says the scope is
   *unknown*, never that it is small.
3. **The rollback plan**, in full, beside the action rather than behind a link.
4. **The evidence** the agent based the proposal on.
5. **Any other change already pending on the same target**, so the second
   approver is not deciding blind.

**Remediation approvals expire in fifteen minutes**, not the three days a
configuration change gets, and they expire to *denied*. An approval that arrives
forty minutes into an incident applies to a system that has already moved.

## The rollback plan

**The plan is written before the action, always.** A plan produced afterwards is
a description of what happened, not a reversal somebody evaluated — and it is
written by whoever is already in trouble.

A plan names the specifics. "Scale it back" is not a plan; "scale checkout-api
in staging from 12 back to 4 replicas" is, and the difference is what an
engineer at 3am can act on.

Each plan carries two snapshots of the target: the state to return it to, and
the state it expects to find when it is applied. Before any step runs, the
second is compared against reality. If somebody else has moved the target since,
**the rollback refuses** rather than applying a plan written for a different
system.

Rollback is available from every surface for **one hour** after the change.
After that, undoing it is a new change: it goes through a fresh approval against
fresh state, which is a better path than a stale handle that still works.

### When there is no plan

Some actions have no inverse. Clearing a cache does not put the entries back.

Such an action is **refused**, not run with a note. An operator who still wants
it waives the requirement explicitly, gives a reason, and the waiver is audited
with their name on it. `clear_cache` ships in the standard set precisely so this
path is exercised rather than theoretical.

### When a rollback fails

It reports, loudly, and stops. There is no automatic retry: the second attempt
would run against a system that is now in a state nobody planned. Which steps
completed is recorded, because that is the difference between a safe retry and a
second incident.

## Execution

An approved action runs:

- **inside the deployment's sandbox profile**, provisioned for the action and
  released afterwards even when the action fails;
- **through the credential proxy** — nothing in this path can hold a credential,
  only a handle that names one;
- **holding an advisory lock on the target**, so two mitigations for one
  workload during an incident do not interleave. The wait is bounded; a caller
  that cannot get the lock is told who has it.

Afterwards the target is **read back** and compared against what the action
intended. Divergence is reported and never repaired: a verifier that noticed a
shortfall and re-applied the change would be taking an unapproved second action,
and the one it would take has already failed once.

Partial success is a first-class outcome. Three of five instances restarted is
recorded as three results, an outcome of `partial`, and **a rollback plan
covering three** — never five.

## Autonomy

A team may opt one action type out of the approval requirement. An entry names:

| Condition | Example |
|---|---|
| Target pattern | only workloads matching `staging-*` |
| Time window | only outside business hours (18:00–08:00 UTC) |
| Maximum blast radius | only when fewer than five services depend on the target |
| Rate limit | at most three per hour, per team, per action type |
| Environment | which environments this covers |

Four properties make this an exception rather than a hole:

- **Conditions are conjunctive.** All of them hold, or a human is asked.
- **Production is excluded unless the entry names it.** An entry that declares no
  environment gets one that refuses production.
- **Conditions are re-evaluated when the action runs**, not only when it is
  proposed. A blast radius that was two services while an approval waited may be
  twenty by the time it executes.
- **An unknown blast radius fails a ceiling.** If the topology graph cannot
  answer, the condition is not met. Autonomy is never granted on the strength of
  an extension nobody installed.

Every autonomous execution is **audited identically to an approved one** — same
action name, same fields — and the team is **notified**. Autonomy nobody hears
about is autonomy nobody can withdraw.

## The kill switch

One action stops every automated write.

```
switch.engage(engaged_by="grace", reason="the cluster is unstable")
```

It is checked before everything else, and it **overrides an approval that has
already been granted**. That is the case it exists for: during a bad incident,
an operator has neither the time nor the confidence to unwind allow-lists entry
by entry and cancel pending approvals one at a time.

- **Scopes nest and the wider one wins.** An organisation switch stops a team
  whether or not that team has one of its own.
- **Releasing one scope does not release another.** Each was engaged by somebody
  for a reason.
- **State is never cached.** The window in which a cached switch would still let
  a write through is measured in exactly the seconds that matter.

Both engaging and releasing are audited. The release is the more sensitive of
the two — it is the moment automated writes become possible again.

## The standard capability set

Seven cross-vendor capabilities, all gated, each providing four components: a
state reader, an applier, a rollback generator, and a post-execution verifier.
The hypervisor set below adds thirteen more on the same four components and the
same gate.

| Capability | Level | Rollback |
|---|---|---|
| `restart_workload` | `write_irreversible` | None — the plan records the recovery instead |
| `rollback_deployment` | `write_reversible` | Deploy the revision recorded before the change |
| `scale_workload` | `write_reversible` | Restore the recorded replica count |
| `cordon_drain_node` | `write_reversible` | Uncordon; drained workloads stay where they rescheduled |
| `update_resource_limits` | `write_reversible` | Restore every request and limit, not only the edited one |
| `toggle_feature_flag` | `write_reversible` | Restore both the value and the rollout percentage |
| `clear_cache` | `write_irreversible` | None derivable — requires an explicit waiver |

**Calling one of these functions directly does nothing.** They refuse, by name,
and point at the gate. A capability that could be invoked directly would be one
that could run with no approval, no plan, and no sandbox.

Reaching a control plane needs one bound in the deployment. With none bound,
every remediation capability reports itself unavailable rather than pretending.

## The hypervisor capability set

Thirteen writes against a Proxmox cluster, on the same four components, the same
approval gate and the same autonomy resolver — there is no hypervisor-specific
autonomy path. Three things about them are worth knowing before they are enabled.

**The risk table is one artefact and it is asserted.** Every action's class, and
the reversibility, data-loss, availability and blast-radius reasoning behind it,
is declared in one module and checked against the registry by a test. The
document an operator reads is therefore the one the system obeys. Its shape:

| Class | Actions |
|---|---|
| `trivial` | clear an orphaned guest lock |
| `low` | start a guest; resume a suspended one |
| `moderate` | graceful shutdown; reboot; suspend; online migration; backup retry; replication resync |
| `high` | relocate a high-availability resource |
| `critical` | hard-stop a guest; reclaim named datastore items; remove an orphaned volume |

**Data loss fixes the class.** Anything that can destroy something with no other
copy is `critical` regardless of how small the change is — a hundred-megabyte
snapshot that is the only recent recovery point outranks a fifty-gigabyte
orphaned disk. The two deletions declare *no* rollback and take the waiver path,
which means an operator has to accept the absence explicitly and the acceptance
is audited.

**There is a deliberate hole.** No capability may fence a node, force quorum,
alter corosync configuration, restart `pveproxy`, `pvedaemon`, `pve-cluster` or
`corosync`, write a node's network configuration, or extend a thin or ZFS pool.
In a two-node cluster nothing available to this system distinguishes a dead node
from an unreachable one, and both wrong answers cost data — so the ambiguity is
reported and escalated rather than resolved. The hole is asserted over the whole
write surface rather than over a list of names, so a capability added in a
prohibited category fails the build.

Every one of the thirteen re-reads its target immediately before acting. A guest
that migrated after the proposal, a lock taken by live work, a cluster that has
lost quorum, or a two-node cluster whose peer has gone silent are each a refusal
rather than a proceed — and the refusal names every precondition that failed, not
the first.

## Configuring it

Everything below is a named constant, changed in one place:

| Setting | Default | What it bounds |
|---|---|---|
| Approval expiry | 15 minutes | How long a remediation stays answerable |
| Rollback window | 1 hour | How long one-click rollback is offered |
| Blast-radius depth | 3 hops | How far the topology traversal goes |
| Target lock timeout | 30 seconds | How long a second action waits for a first |
| Autonomy rate limit | 3 per hour | Per team, per action type |
| Autonomy blast radius | 5 services | The default ceiling on an entry |

## Where to look when something went wrong

| Question | Where |
|---|---|
| Did anything change production? | Audit trail, action `remediation.execute` |
| Did anything change it without being asked? | Audit trail, action `remediation.autonomous` |
| Who stopped or restarted writes? | Audit trail, action `remediation.kill_switch` |
| Who accepted an action that cannot be undone? | Audit trail, action `remediation.waiver` |
| Did the change take effect? | The execution record's verification report |
| What would undo it? | The stored rollback plan for the approval |
