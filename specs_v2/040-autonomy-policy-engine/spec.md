# Feature 040 — Autonomy Policy Engine

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/040-autonomy-policy-engine`
- **Status:** Draft
- **Depends on:** 013, 015, 017, 039

## Summary

How much the system may do without asking — decided per deployment, per team, per
resource kind, per individual resource, per action, and per time of day, by one
resolver that every actuator consults and none may bypass.

There are three defensible postures. Never act, only diagnose and propose. Act on
low-risk reversible things and ask for the rest. Act on anything with a rollback
plan and report afterwards. All three are correct — for different operators, for
different resources, on different days. A homelab owner may want full autonomy on
a test container and a strict approval gate on the datastore holding their
photographs, and neither choice is wrong.

So the posture is not chosen once. It is a resolvable value, and this feature is
the resolver: the schema that expresses it, the precedence that combines it, the
guards that bound it whatever it says, and the audit that records what it decided
and why.

## User scenarios

### Primary story

An operator sets the deployment default to "propose only". Then they relax it:
unlocking a stuck guest is autonomous everywhere, because it is reversible and
they are tired of doing it by hand. Restarting a container is autonomous for
anything labelled `env=lab` and requires approval elsewhere. Anything touching
the datastore that holds their backups requires approval, always, and is frozen
entirely between 01:00 and 04:00 while backups run.

Six weeks later something unlocks a guest at four in the morning and they read
about it over coffee — with the decision, the level that permitted it, the rule
that set that level, the verification that confirmed it worked, and the rollback
that was available if it had not.

### Acceptance scenarios

1. **Given** no policy configured, **when** any action is proposed, **then** it
   requires approval. The default MUST be the safe one.
2. **Given** policies at deployment, team, kind, resource and action scope,
   **when** a level is resolved, **then** the most specific applicable rule wins,
   and the resolution names every rule it considered.
3. **Given** a resolved level of "propose only", **when** an action is proposed,
   **then** nothing is executed and a proposal is recorded with the exact
   operation a human could run.
4. **Given** a resolved level of "act on low risk", **when** an action's risk
   class is at or below the configured bound, **then** it executes; **when** it is
   above, it goes to approval.
5. **Given** a resolved level of "act and report", **when** an action has a
   rollback plan, **then** it executes and notifies afterwards; **when** it has
   none, it goes to approval regardless of level.
6. **Given** a freeze window covering a resource, **when** any action on it is
   proposed during that window, **then** it is refused with the freeze named,
   whatever the level says.
7. **Given** the kill switch engaged, **when** any action is proposed, **then** it
   is refused, and no configuration can override it.
8. **Given** a budget of actions per resource per interval, **when** it is spent,
   **then** further actions require approval and the exhaustion is raised.
9. **Given** any resolution, **when** it completes, **then** it is written to the
   audit log with inputs, applicable rules, the winner, and the outcome — whether
   it permitted or refused.
10. **Given** a dry-run mode, **when** it is enabled at any scope, **then**
    actions in that scope are simulated and recorded, never executed, and the
    simulation says what would have happened.
11. **Given** a policy change, **when** it is saved, **then** it is previewable
    against recent history — "these eleven actions from last week would now be
    autonomous".
12. **Given** an action whose risk class is not declared, **when** it is proposed,
    **then** it is treated as the highest risk class, never as unclassified.

### Edge cases

- Two rules at the same specificity disagreeing.
- A resource matching a rule by label and a different rule by kind.
- A policy referencing a resource that no longer exists.
- A freeze window in a different timezone from the deployment.
- A level raised while an action is mid-flight.
- An action proposed by a sub-agent rather than the top-level run.
- An action whose target is a set of resources with different levels.
- A budget interval spanning a deployment restart.

## Requirements

### Functional

**Levels and risk**

- **FR-001** The autonomy level MUST be a closed, ordered set: `propose_only`,
  `act_on_low_risk`, `act_and_report`. No fourth level, no free text.
- **FR-002** Every action MUST carry a declared risk class from a closed, ordered
  set, declared on the capability, not inferred at call time.
- **FR-003** The risk class MUST account for reversibility, blast radius, and
  whether the action can cause data loss or loss of availability.
- **FR-004** An action with no declared risk class MUST be treated as the highest
  class.
- **FR-005** `act_on_low_risk` MUST take a configurable risk-class bound, so
  "low" is the operator's definition and not the system's.

**Scopes and resolution**

- **FR-006** A level MUST be settable at, at minimum: deployment, team node,
  resource kind, resource label selector, individual resource, capability, and
  capability × resource.
- **FR-007** Resolution MUST follow declared precedence, most specific winning,
  and MUST be deterministic when two rules tie.
- **FR-008** A resolution MUST return not only the level but the full explanation:
  every rule considered, which applied, which won, and why.
- **FR-009** The absence of any rule MUST resolve to `propose_only`.
- **FR-010** Policies MUST be expressed through the hierarchical config service,
  inheriting its merge, its locks, its required fields, and its approval gating.
- **FR-011** An action targeting several resources MUST resolve to the least
  permissive level among them.

**Bounds that no level overrides**

- **FR-012** A kill switch MUST refuse every action, and no configuration may
  override it. Engaging it MUST take effect immediately for in-flight decisions
  not yet executed.
- **FR-013** Freeze windows MUST refuse actions within them, scopeable by
  resource, kind, label and team, and MUST be timezone-explicit.
- **FR-014** An action budget per resource, per capability and per team, over a
  configurable interval, MUST downgrade to approval when spent, and MUST raise
  its own exhaustion.
- **FR-015** An action with no rollback plan MUST require approval at every level.
- **FR-016** These four bounds MUST be evaluated after the level, and a refusal
  by any of them MUST name which one refused.

**Modes**

- **FR-017** A dry-run mode MUST be settable at any scope, and MUST simulate and
  record without executing, describing what would have happened.
- **FR-018** A policy change MUST be previewable against recent action history,
  reporting what would have been decided differently.
- **FR-019** A time-bounded override MUST exist — raise autonomy for two hours
  during a maintenance session — expiring automatically and audibly.

**Enforcement**

- **FR-020** Every actuator MUST consult the resolver. There MUST be exactly one
  path from a proposed action to execution, and it MUST pass through this
  feature.
- **FR-021** The single path MUST be enforced structurally, by a test that fails
  when a new actuator bypasses it.
- **FR-022** Every decision MUST be audited, permitting and refusing alike, with
  its full explanation.
- **FR-023** The resolved level and its explanation MUST be visible in the console
  before an action is taken, on the resource and on the proposal.

### Non-functional

- **NFR-001** A resolution MUST complete within a declared budget with a thousand
  rules configured.
- **NFR-002** Resolution MUST be pure with respect to its inputs, so it is
  testable exhaustively and previewable against history.
- **NFR-003** The policy set MUST be exportable and importable as configuration,
  so a deployment's posture is reviewable as a document.
- **NFR-004** A malformed policy MUST fail at save time with a named error, never
  at decision time.

## Success criteria

- **SC-001** With no configuration, every action of every risk class requires
  approval.
- **SC-002** A matrix test over every level × every risk class × every scope
  combination produces the specified decision, exhaustively.
- **SC-003** The kill switch refuses everything, and no configuration overrides
  it, asserted against every level.
- **SC-004** A freeze window refuses inside it and permits outside it, across a
  timezone boundary and a daylight-saving change.
- **SC-005** A spent budget downgrades to approval and raises exhaustion.
- **SC-006** An action with no rollback plan requires approval at every level.
- **SC-007** A structural test fails when an actuator reaches execution without
  the resolver.
- **SC-008** Every decision, permitting and refusing, appears in the audit log
  with its explanation.
- **SC-009** A dry-run at any scope executes nothing, asserted by a fake actuator
  that records calls.
- **SC-010** A policy change previewed against a recorded week reports the
  differences correctly.
- **SC-011** Resolution within budget at a thousand rules.

## Out of scope

- Performing the actions — feature 041.
- The approval mechanism itself, which feature 015 already owns.
- Provider-specific risk classifications — features 046 declares Proxmox's.
