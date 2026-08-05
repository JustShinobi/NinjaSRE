---
name: remediation
display_name: Remediation discipline
description: What must be true before acting, and what the action must carry with it.
domain: remediation
applies_when:
  tags: [remediation, restart, rollback, scale, mitigation]
directs_tools:
  - restart_workload
  - rollback_release
  - scale_workload
use_cases:
  - a cause is established and the question is what to do about it
  - choosing between mitigating now and continuing to investigate
anti_examples:
  - an investigation with no established cause
---

# Acting

Remediation is the part of an incident where a mistake compounds. Everything
before it costs time; this costs availability, data, or the ability to find out
what happened.

## The sequence

1. **Diagnose.** The cause is established, or you are deliberately mitigating
   without one. Those are different, and which one you are doing changes
   everything after this step.
2. **Propose.** State the action, the target, the reason, and the risk, in that
   order and before doing anything.
3. **Read the plan.** Every tool here generates the rollback plan before the
   action is approved. Read it. It is the thing that says whether this can be
   walked back.
4. **Get approval.** A human approves the specific action on the specific
   target. Approval does not generalise to the next one, or to the same action
   an hour later.
5. **Act.** One action. Not two.
6. **Verify.** With the same measurement that established the symptom.

## Three things must be true before acting

**The cause is established, or the action is a deliberate mitigation.** A
mitigation buys time and the investigation continues; a fix ends the incident.
Acting without knowing which you meant produces an incident that appears
resolved and recurs.

**The action is the smallest one that addresses the cause.** Restarting one
instance beats restarting the workload. Rolling back one service beats rolling
back a release train. The smallest action has the smallest blast radius and,
just as importantly, the clearest signal: if the symptom moves, you know what
moved it.

**The evidence has been captured.** Restarting destroys process state, logs
roll off, and metric resolution degrades with age. Once the action is taken,
the investigation is working from whatever was gathered beforehand — so gather
it beforehand.

## Choosing the action

| Situation | Action | Why this one |
|---|---|---|
| A change correlates with the onset and the mechanism connects them | `rollback_release` | Highest confidence available, and the most reversible |
| A resource that can be added has run out, and the demand is real | `scale_workload` | Addresses the cause rather than the symptom — but scaling into a retry storm makes it worse |
| Process state is corrupt and the cause is understood | `restart_workload` | Last resort. It most often *appears* to work, because it clears the state that would have explained the problem |

Restart is last for a reason worth stating plainly: it is the action with the
highest ratio of apparent success to actual success. The symptom goes away, the
cause does not, and the evidence that would have found the cause is gone.

## The rollback plan is not paperwork

Every tool here generates the plan that undoes the action before the action is
approved. The plan exists at that moment specifically because the person who
needs it will be someone reading it under pressure, possibly not the person who
approved it, possibly at a worse hour.

A plan that says "scale it back" is useless. The generated plans name the
workload, the environment, and the value to restore, and they record the
current value *first* — because after the action, the number you needed is
gone.

If the plan says the action is not reversible — a restart's says so — then
approving it is accepting that this cannot be walked back. That is a decision
worth making consciously rather than discovering afterwards.

## Proposing an action

Put this in front of the human who has to approve it:

```
Action:     restart, rollback, or scale
Target:     the workload and the environment, named exactly
Reason:     the mechanism this addresses, not the symptom it hides
Risk:       what else this touches, and what it destroys
Rollback:   the generated plan, quoted, including whether it is reversible
Verify:     the measurement that will say whether it worked
```

A proposal missing the risk line is a proposal that has not been thought
through. The risk is the part the approver cannot reconstruct on their own.

## After acting

Confirm the symptom moved, using the same measurement that established it.
"Looks better" is not a measurement, and an action credited with a recovery it
did not cause is a false lesson that the system will keep applying.

If the symptom did not move, **do not stack a second action on the first**. Two
untested changes make the next investigation harder than the current one, and
you can no longer attribute a recovery to either.
