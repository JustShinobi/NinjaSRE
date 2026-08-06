# Runs, traces, and scheduling

Every investigation NinjaSRE performs is written down while it happens, watchable
while it is happening, and replayable afterwards. Recurring investigations are
started by a scheduler that runs each firing exactly once however many replicas
you deploy.

This page is for the person operating that: what is stored, how long it is kept,
how to configure a schedule, and which knobs exist when the defaults are wrong.

## What a run records

| Record | What it holds |
|---|---|
| **Run** | Identity, team, trigger, principal, start and end, status, outcome summary |
| **Turn** | Model, prompt and completion tokens, cost, duration, and why those capabilities were offered |
| **Capability call** | Name, arguments, result, duration, outcome, evidence produced, error class |
| **Evidence** | One observation, citable in a conclusion |
| **Trace event** | The ordered log: guardrail actions, masking, budget evictions, sub-agent dispatches, lifecycle |

A sub-agent dispatch is a **nested run** with its own turns and calls, linked to
its parent. It does not appear in the run history as a second investigation
unless you ask for it, because it is part of one.

### Statuses

`running`, `suspended`, `completed`, `cancelled`, `failed`, and `interrupted`.

The last is the one worth knowing. **`interrupted` means nobody knows how far
this got** — the replica running it vanished, and something else noticed
afterwards. It is not `failed`: recording it as a failure would put a conclusion
in your history that nothing established. An interrupted run keeps whatever it
managed to record and is fully replayable.

## Payload limits and truncation

Trace payloads are bounded, and **nothing is ever cut silently**.

| Bound | Default | What it limits |
|---|---|---|
| `MAX_TRACE_PAYLOAD_BYTES` | 64 KiB | One tool result, argument set, or event payload |
| `MAX_TRACE_STRING_LENGTH` | 8,192 | One string inside a payload |
| `MAX_TRACE_SEQUENCE_ITEMS` | 200 | Entries kept from one list |
| `MAX_TRACE_PAYLOAD_DEPTH` | 12 | Nesting kept before a branch is replaced |

A truncated value ends in `…[truncated]` and the payload gains a `_truncated`
key recording how many strings, list entries, branches, and fields went, and how
many bytes. If you are seeing that key often, the capability producing it should
be storing a reference and a summary rather than its whole output.

Guardrails run over every string in a payload **before** it is stored. A trace
is a durable store nobody audits on the way in, so a credential that reached one
would sit there for the whole retention window.

## Watching a run live

A client subscribes with a **cursor** — `run-id:position` — and receives every
event after it. The event log is the source of truth; the live fan-out is a
delivery optimisation over it.

That is what makes reconnection exact. A client that drops its connection
reconnects with the last cursor it acknowledged and receives everything it
missed, once. A client that falls more than `MAX_STREAM_BUFFER_EVENTS` (512)
behind is disconnected rather than buffered — it reconnects with its cursor and
still misses nothing.

Across replicas, configure a stream bridge so a client attached to one replica
sees events another recorded. Without one, a single-process deployment works
completely and a multi-replica one serves live events only from the replica that
happens to be recording.

## Retention

Two different operations, and the difference matters.

**Trace retention** (`RETENTION_DAYS_RUN_TRACES`, default 90) strips turns,
calls, evidence, and the event log, and **keeps the run** — its status, its
timings, and what it concluded. Your history, your reports, and your cost
aggregation are unaffected. This is what you want.

**The persistence sweeper's `run_traces` class** deletes runs whole. Use it when
you want the storage back and not the history.

The **audit trail is never deleted by either**, at any configuration. It has no
deletion path in the port, in the repository, or in the database.

A run that is still `running` or `suspended` is never stripped, whatever its
start time says.

## Configuring a schedule

A schedule needs an expression, a timezone, a team, a principal, and an
objective.

```
0 2 * * *          every day at 02:00
30 1 * * mon       Mondays at 01:30
0 */4 * * *        every four hours
0 0 1 * *          the first of the month
```

Five fields — minute, hour, day of month, month, day of week — with ranges,
lists, steps, and three-letter names. No seconds field, no `@reboot`, no
`L`/`W`/`#`. **A day-of-month and a day-of-week are OR-ed** when both are
restricted, as in every crontab: `0 3 1 * mon` means the 1st *and* every Monday.

A malformed expression is refused when you create the schedule, not on the night
it was meant to run.

### The principal

A schedule carries one, and it is not optional. Runs it starts attribute to it,
and an approval raised inside one attributes to it. **A schedule is not a way to
act without anybody being responsible for it** — scheduled runs are gated by
exactly the same approvals interactive ones are.

### Timezones and daylight saving

Configure an IANA name (`Europe/London`), not an offset. A `0 2 * * *` schedule
stays at 02:00 local across a transition, which is the point.

The two nights a year:

| Transition | What happens |
|---|---|
| **Spring forward** — the local time does not exist | Fires **once**, at the instant it would have fired anyway. A 01:30 GMT schedule fires at 02:30 BST, and the firing is marked shifted. |
| **Fall back** — the local time happens twice | Fires **once**, on the first occurrence. The claim key makes the second unreachable even if a replica evaluated it. |

Neither a double fire nor a silent skip, and both are tested explicitly.

### Misfire policy

What to do about firings that came due while nothing was running.

| Policy | Behaviour | Use it for |
|---|---|---|
| `skip` | Forget them; resume at the next firing | A health sweep — yesterday's answer is worthless |
| `run_once` (default) | Run the **most recent** missed firing | A nightly report — one is owed, not seven |
| `run_all` | Replay each missed firing, capped at 10 | A task that accumulates per firing |

A firing that is merely *late* — inside `SCHEDULER_MISFIRE_GRACE_SECONDS`,
default 300 — is not a misfire and runs whatever the policy says. That is the
case where a concurrency limit delayed it by ninety seconds, and you want it to
run.

## Concurrency

| Limit | Default | What it bounds |
|---|---|---|
| `SCHEDULER_GLOBAL_CONCURRENCY` | 8 | Scheduled runs at once, per worker process |
| `SCHEDULER_TEAM_CONCURRENCY` | 2 | Scheduled runs at once for one team |

Work beyond a limit **queues**; it is never dropped. A scheduler that dropped a
firing because the platform was busy would turn a capacity problem into a missed
disaster-recovery validation, and you would find out about the second one much
later.

The per-team limit is what stops one team's forty midnight sweeps filling every
slot in the deployment. Raise the global one before the team one; a team limit
above the global limit is refused, because the global one binds first anyway.

These are per process. A deployment's effective ceiling is the limit times the
replica count.

## Exactly-once, and what happens when a replica dies

Two layers, and no lock service to install.

**A lease.** Each due job is claimed by one worker and no other, for
`JOB_CLAIM_LEASE_SECONDS` (default 300), renewed every
`SCHEDULER_HEARTBEAT_SECONDS` (60) while the job runs.

**A derived run id.** The run id is `job-id@fire-time`. Two workers that both
decided a firing was theirs derive the same id, and the store refuses the second
one.

When a worker dies holding a claim:

1. Its lease expires — at most `JOB_CLAIM_LEASE_SECONDS` later.
2. The reaper releases the lease and marks the abandoned run `interrupted`.
3. The job's schedule is left where it was, so it is claimable again.

**Run the reaper on a timer** in every deployment. Without it, leases still
expire when the next claim asks, but abandoned runs stay marked `running` and
your history acquires investigations that look live forever.

## When a team is deleted

Its schedules are **disabled with a recorded reason**, never dropped. The
definition survives to be read and, if the team comes back, re-enabled. Call
`ScheduleService.disable_orphans` with your live team list after a hierarchy
change; what it disabled is what it returns, so you can tell somebody.

## Run history

One history over every investigation. A scheduled run and an interactive one
differ in their trigger and their principal and in nothing else, so there is no
second list to reconcile.

Filter by team, status, trigger, job, and time range. Cost and usage aggregate
per run, per team, and per period, summed from the turns rather than stored on
the run — and a model whose pricing the deployment does not hold is reported as
an unpriced run rather than quietly counted as free.

---

Constants live in `config/constants/runs.py` and `config/constants/persistence.py`.
Conventions for contributors are in [`platform/AGENTS.md`](../platform/AGENTS.md).
