# platform/remediation/ — where the system is permitted to change production

**Tier 3.** May import: `config`, `core`, and the rest of `platform`. Must never
import `capabilities`, `integrations`, `gateway`, or `surfaces`.

Read-only is the default. A write needs an explicit human approval *and* a
rollback plan recorded before execution. Autonomy is opt-in per action type,
scoped per team, conditional, and killable in one action.

## The ordering is the specification

Everything in this package follows from one sequence, and a change that reorders
it is a change to what the system guarantees rather than to how it is written:

```
kill switch → closed-loop guards → allow-list or policy → approval
            → plan persisted → conditions re-evaluated
            → execute (sandboxed, proxied, serialised) → verify → audit
            → settle period → read the signals back → verdict
            → resolve, escalate, or roll back → record effectiveness
```

Each step is where it is for a reason worth knowing before moving it.

- **The kill switch is first** because it overrides an approval that has already
  been granted. The person who approved an action thirty seconds ago did so
  before whatever made an operator reach for the switch.
- **The plan is persisted before execution** because a plan produced afterwards
  is a description of what happened, not a reversal the approver evaluated — and
  its absence is itself a signal the action is riskier than it looked.
- **Conditions are re-evaluated at execution time** because an approval can sit
  pending while the system changes. A blast radius that was two services when a
  human looked at it may be twenty now.
- **Verification reads the target back** because "the API returned 200" and "the
  change took effect" are different claims, and conflating them turns a silent
  partial failure into a reported fix.
- **The settle period comes after the run ends**, not inside it. A verification
  that waited would hold a run past its wall-clock ceiling and would be lost
  when the process restarted. It is a durable row with a due time, claimed with
  a lease, and the run ends without it.
- **The verdict is recorded before anything acts on it.** A worker that died
  between the two leaves a verdict and no rollback, which is recoverable and
  visible; the other order leaves a rollback nobody can explain.

## What lives where

| Module | Owns |
|---|---|
| `models.py` | The six values a change is made of, and the two snapshots a plan carries |
| `components.py` | The five things every remediation capability provides, and the map of them |
| `declaration.py` | Which signals an effect appears in, how long to wait, and the honest verdict |
| `obligations.py` | The durable "find out whether this worked", claimed and settled |
| `aftermath.py` | What each of the five verdicts causes, and why only one undoes anything |
| `suspension.py` | Stopping autonomy on one resource, and the two rows that record it |
| `recurrence.py` | The fourth time is a pattern, not a fourth incident |
| `history.py` | What has worked here before, and the route into episodic memory |
| `guards.py` | The three things the loop knows that send the next action to a human |
| `closed_loop.py` | The sweep: claim what is due, settle it, deal with the answer |
| `timeline.py` | Every step on the incident's timeline, with its actor and its cause |
| `gating.py` | The `pre_tool_use` binding — the single place a write is stopped |
| `request.py` | What a human is shown: state, blast radius, plan, evidence, conflicts |
| `rollback/` | Derived before, checked before applying, loud when it fails |
| `execution.py` | Isolation, per-target serialisation, per-sub-target results |
| `verification.py` | Intended versus actual, reported and never repaired |
| `autonomy/` | Allow-list, conditions, and the switch above both |
| `audit.py` | The trail, identical whether a human approved or nobody did |

## Things that have already been got wrong here

- **A rollback plan carries two snapshots, not one.** `recorded_state` is where
  the undo goes; `applied_state` is what the undo expects to find. Checking a
  rollback against the first refuses every legitimate undo, because the action's
  whole effect is that the target no longer looks like that. The code reads
  plausibly either way, which is what makes it worth stating.
- **An unreadable target is not an empty one.** `StateSnapshot.unreadable` is a
  distinct value and `known` is checked everywhere, because an empty snapshot
  fingerprints to a real value and would compare equal to another empty one —
  which is how a rollback proceeds against a target nobody could read.
- **An unknown blast radius must fail a ceiling, not pass it.** The gate feeds a
  deliberately enormous number to the evaluator when the graph could not answer.
  The alternative is an allow-list that widens itself the day the graph goes
  down.
- **The gate executes; it does not permit.** A `pre_tool_use` hook may refuse a
  call or rewrite it and may not perform one, so a permitted action comes back
  as a denial carrying its own outcome. Returning `Allow` would run the change
  twice: once here with a plan and a verification, and once unmediated.
- **`inconclusive` is not a soft `effective`.** The single most damaging
  simplification available here is treating "the signal did not clearly get
  worse" as success. It produces a high reported success rate and an operator
  who has stopped believing it, so a move smaller than the noise floor never
  reaches `effective` — and `ineffective` is only reachable when the capability
  declared a clearing value, because without one nothing is actually known.
- **Only `worsened` rolls anything back.** An action that did nothing is left in
  place and escalated: undoing it would be a second unattended write with no
  evidence that it helps. An action that made things worse is undone, because
  the state it replaced is known to have been better.
- **A failed rollback suspends autonomy on the resource, and only a person
  clears it.** At that point the deployment has changed something, failed to
  undo it, and does not know what state the resource is in. There is no timeout,
  deliberately: a suspension that lapsed on its own would resume unattended
  action on a resource nobody had looked at.
- **`RemediationApplier.apply` does nothing, deliberately.** For the other four
  change types, approval *is* the change. For a production remediation, three
  steps stand between the decision and the action, and collapsing them into the
  approval call would lose all three.

## Wiring a deployment

```python
registry = capabilities.tools.remediation.registry()
gate = RemediationGate(
    requests=RequestBuilder(registry=registry, plans=PlanFactory(registry=registry), ...),
    executor=RemediationExecutor(registry=registry, isolation=..., verification=...),
    kill_switch=KillSwitch(),
    evaluator=ConditionEvaluator(allow_list=AllowList()),
    waiter=...,          # how this deployment suspends a run until a human answers
    run=RunContext(requester=..., team_node_id=...),
)
gate.register(hooks)
```

The approval service needs `ChangeType.REMEDIATION` in its applier map, and the
entry is `RemediationApplier(registry=registry)`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../../AGENTS.md).
