# ADR 0006 — Read-only by default, with approval and rollback for writes

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article III

## Context

An agent that can only read is safe and half-useful. An agent that can act closes
incidents but can also cause them. The two prior systems sit at different points:

**The pipeline design** classifies capabilities with a `side_effect_level` and supports
`requires_approval`, `approval_reason`, and `approval_expiry_seconds`, with inline
approval flows in the Slack and Discord gateways.

**The memory design** ships remediation capabilities (restart pod, rollback deployment,
scale deployment) and a console workflow for reviewing remediations with a
rollback action, plus organisation-level policies (`require_approval_for_prompts`,
`require_approval_for_tools`).

Neither combines declarative classification with a mandatory recorded rollback
plan.

The cost asymmetry is the whole argument. A missed investigation costs minutes of
human triage. An unapproved `scale --replicas=0` on the wrong deployment at 03:00
costs an outage — caused by the tool that was meant to prevent one.

## Decision

**Read-only by default. Every write requires explicit human approval and a stored
rollback plan.**

1. Every capability declares a `side_effect_level`. **Absence of a declaration is
   treated as write**, not read — the fail-safe direction.
2. Any capability above read level requires explicit human approval before
   execution, presented at the surface the human is already using (chat, console,
   or REPL).
3. An approved action records its rollback plan **before** it executes. An action
   with no rollback path is rejected unless the operator explicitly waives it, and
   the waiver is recorded in the audit log.
4. Approval is per-action and per-session. It never generalises forward.
5. Autonomous execution allow-lists may exist but are opt-in per action type,
   revocable instantly by a kill switch, and fully audited.

## Rationale

**Default-deny beats default-allow at this cost asymmetry.** Treating an
unclassified capability as read-only would mean a contributor who forgets the
metadata ships an unguarded production write. Treating it as write means they ship
an unnecessary approval prompt. The second failure is recoverable.

**Rollback-before-execute makes the plan real.** A rollback plan produced after a
failure is written by someone under pressure with incomplete information. Produced
before execution, it is a design artefact the approver can evaluate — and its
absence is itself useful signal that the action is riskier than it looks.

**Approval belongs where the human already is.** An approval that requires opening
a console during an incident will be worked around. Inline approval in the Slack
thread where the incident is being discussed will not.

**Autonomy is a graduation, not a setting.** Teams earn confidence in specific
action types over time. An allow-list scoped per action type, with a kill switch,
lets that confidence be expressed precisely instead of as a global toggle.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Read-only, no writes at all in the MVP | Forfeits real value — restart, rollback, and scale are the actions teams most want automated — and the governance machinery has to be built eventually anyway |
| Approval with a configurable global autonomous mode | A single switch that turns off all safety is the switch that gets turned on during an incident and left on |
| Approval without a rollback requirement | Approvers cannot evaluate an action whose reversibility is unknown, and post-hoc rollback under pressure is unreliable |

## Consequences

**Positive**

- The system cannot silently change production
- Approvers see the action, its blast radius, and its reversal before deciding
- Every action is attributable to a named human in the audit log
- Teams can widen autonomy incrementally with precision

**Negative**

- Remediation is slower than fully autonomous alternatives
- Every write capability must author and maintain a rollback plan generator
- Approval fatigue is a real risk if classification is too coarse
- Surfaces must implement approval rendering, not just report rendering

**Mitigations**

- `side_effect_level` is granular (read / read-sensitive / write-reversible /
  write-irreversible / destructive) so approval friction matches actual risk
- Approval requests carry the full context — target, current state, proposed
  change, blast radius from the topology graph, and the rollback plan — so the
  decision takes seconds
- Allow-listing lets teams remove friction for low-risk, high-frequency actions
- Approval timeout policy is configurable, with expiry defaulting to deny
