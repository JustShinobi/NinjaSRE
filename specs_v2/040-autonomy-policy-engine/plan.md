# Plan — 039 Autonomy Policy Engine

## Technical context

| Concern | Choice |
|---|---|
| Tier | `platform/autonomy/` — tier 3, beside `platform/remediation/` |
| Policy storage | The hierarchical config service, so merge, locks, required fields and approval gating are inherited rather than rebuilt |
| Risk classes | Declared on the capability, in the capability catalogue, validated at registration |
| Bounds | Kill switch and freeze in `platform/trust_controls.py`'s existing shape; budgets in Postgres |
| Resolution | A pure function of (action, subjects, policy set, clock) so it is exhaustively testable |
| Audit | The existing immutable audit log |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| II — Bounded autonomy | This feature *is* Article II's mechanism. | Every bound the article names — ceilings, kill switch, human gates — is expressed here, and FR-012 makes the kill switch unoverridable by configuration. |
| III — Read-only by default | The default posture. | FR-009: the absence of a rule resolves to `propose_only`. A deployment that configures nothing acts on nothing. |
| XV *(governance)* — auditability | Autonomy without a record is indistinguishable from a fault. | FR-022 audits every decision including refusals, with the full explanation. |
| VIII — Layered architecture | A new platform module every actuator depends on. | `platform/autonomy/` depends on `config/`, `platform/config_service/`, `platform/persistence/`. Actuators depend on it, never the reverse. |
| XII — Test-first | The decision matrix must be exhaustive. | Purity (NFR-002) makes SC-002's full matrix a unit test rather than a sampling. |

## Architecture decisions

**Three levels, and no fourth.** The temptation is a rule language. Resisted: an
expression engine for autonomy is a place to write a bug that executes something
at four in the morning. Three ordered levels, a risk-class bound, and scoped
rules cover every posture in the primary story, and anything they cannot express
is a case for an approval, not for more grammar.

**Risk is declared on the capability, not judged at the call.** The capability
author knows whether restarting a guest is reversible. The decision point does
not, and an LLM proposing the action certainly does not. Declaring it at
registration means the classification is reviewed once, in code, rather than
inferred every time.

**Unclassified is maximally risky.** FR-004 is the difference between a new
capability defaulting to "safe to run unattended" and defaulting to "ask". Only
one of those is survivable when somebody adds a capability and forgets a field.

**Bounds are evaluated after the level and cannot be overridden by it.** The kill
switch, freeze windows, budgets and the rollback requirement are not high levels
of the same scale — they are a second gate. Expressing them as levels would mean
some configuration, somewhere, could set a level that passes them.

**One path to execution, enforced structurally.** The whole feature is worth
nothing if an actuator can call a provider directly. SC-007 is a test over the
call graph, not a review convention, and it is written before the resolver.

**Policy lives in the config service.** Hierarchy, deep merge, locked fields,
approval-gated fields and provenance already exist there and are already tested.
A second configuration mechanism for the most safety-critical setting in the
system would be the wrong place to save effort.

**Resolution explains itself.** Returning a bare level would make every "why did
it do that" question an archaeology exercise. The explanation — rules considered,
applied, winner, reason — is part of the return value, is audited, and is shown
in the console before the action.

## Phases

1. **Risk classes.** The closed ordered set, declaration on capabilities,
   validation at registration, the unclassified-is-highest rule, and a sweep
   classifying every capability that exists today.
2. **Policy schema.** Levels, scopes, selectors, precedence; expressed in the
   config service; save-time validation; export and import.
3. **Resolution.** The pure resolver, precedence, tie-breaking, least-permissive
   for multi-subject actions, the explanation, and the exhaustive matrix test.
4. **Bounds.** Kill switch, freeze windows with explicit timezones, budgets with
   exhaustion raising, the rollback-plan requirement, and refusal attribution.
5. **Modes.** Dry-run at any scope, time-bounded overrides with automatic
   expiry, and policy-change preview against recorded history.
6. **Enforcement.** The single path from proposal to execution; the structural
   test; migration of every existing actuator onto it.
7. **Surfaces.** Gateway endpoints for policy read, write, preview, dry-run,
   kill switch and freeze; CLI; console views showing the resolved level and its
   explanation on resources and proposals.

## Risks

- **The matrix grows beyond exhaustive testing.** Mitigated by keeping levels and
  risk classes small and closed. Three levels × five risk classes × seven scope
  kinds is enumerable; a rule language is not.
- **Operators configure themselves into an unsafe posture.** Mitigated by FR-018's
  preview against history, which turns an abstract policy change into a concrete
  list of actions that would now happen unattended.
- **The single path is bypassed by a well-meaning contributor.** Mitigated by
  SC-007 running in CI, and by writing it before the resolver so it fails loudly
  on day one.
