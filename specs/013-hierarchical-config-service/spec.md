# Feature 013 — Hierarchical Configuration Service

- **Wave:** 3 — Control Plane
- **Branch:** `feat/013-hierarchical-config-service`
- **Status:** Draft
- **Depends on:** 003, 006
- **Blocks:** 014, 015, 016, 021, 025

## Summary

The control plane. Configuration lives in an org → team tree with deep merge, so a
platform team sets defaults once and each team overrides only what differs.
Fields can be locked, required, or approval-gated. Everything the runtime reads —
prompts, models, sub-agent topology, enabled capabilities, integration
configuration, policy switches — resolves from here.

## User scenarios

### Primary story

A platform team sets the org default model, the investigation system prompt, and
the masking policy. The payments team overrides the model for cost reasons and
adds two integrations. The security team locks the masking policy so no child may
weaken it. Each team's agent resolves a merged, validated configuration at
investigation start.

### Acceptance scenarios

1. **Given** an org config and a team config, **when** effective config is
   computed, **then** dicts merge recursively and lists replace entirely.
2. **Given** a field locked at org level, **when** a team attempts to override it,
   **then** the write is rejected naming the field and the locking node.
3. **Given** a required field with no value anywhere in the chain, **when**
   effective config is computed, **then** validation fails naming the field.
4. **Given** a field marked approval-gated, **when** a team changes it, **then**
   the change enters the approval queue rather than taking effect.
5. **Given** a config change, **when** it is written, **then** an audit record
   captures who, when, which node, the previous value, and the new value.
6. **Given** an invalid configuration, **when** it is submitted, **then** it is
   rejected with a field-level error before persistence.
7. **Given** an investigation starting, **when** it resolves configuration,
   **then** the merged result is cached and the cache is invalidated on any
   ancestor change.
8. **Given** a deep hierarchy (org → division → team → squad), **when** effective
   config is computed, **then** merge proceeds root-to-leaf with each level
   overriding its ancestors.
9. **Given** a capability disabled at team level, **when** the catalogue resolves,
   **then** that capability is unavailable to that team's investigations.

### Edge cases

- A node deleted while a child still inherits from it.
- Two concurrent writes to the same node.
- A config referencing a capability or integration that no longer exists.
- A lock added after a child already overrode the field.
- A very deep hierarchy causing expensive merges on every investigation.
- Secret-shaped values submitted into config rather than the credential vault.

## Requirements

### Functional

**Hierarchy and merge**

- **FR-001** Configuration MUST live in a tree with an org root and arbitrary
  intermediate nodes down to teams.
- **FR-002** Effective config MUST be computed root-to-leaf by deep merge: dicts
  merge recursively, lists and scalars replace entirely.
- **FR-003** The merge MUST be deterministic and free of control keys — no
  `_inherit`, `_append`, or similar directives.
- **FR-004** Deleting a node MUST be rejected while descendants exist, or MUST
  require explicit reparenting.

**Field behaviours**

- **FR-005** A field MUST be markable **locked** at a node: no descendant may
  override it.
- **FR-006** A field MUST be markable **required**: effective config missing it
  fails validation.
- **FR-007** A field MUST be markable **approval-gated**: changes enter the
  approval queue (feature 015) rather than applying directly.
- **FR-008** A field MUST support **allowed values** and **maximum values**
  constraints enforced at write.
- **FR-009** Adding a lock where a descendant already overrides MUST report the
  conflict and require explicit resolution.

**Schema and validation**

- **FR-010** Configuration MUST have a declared schema covering: agent prompts,
  agent topology (sub-agents), model selection per role, enabled capabilities,
  integration configuration references, memory and knowledge policies, masking
  policy, guardrail rule set, approval policy, and surface settings.
- **FR-011** Validation MUST run before persistence and MUST produce field-level
  errors.
- **FR-012** A reference to a non-existent capability or integration MUST be a
  validation error, not a runtime surprise.
- **FR-013** Secret-shaped values MUST be rejected with a message directing the
  operator to the credential vault.

**Resolution and caching**

- **FR-014** The runtime MUST resolve effective config once per investigation.
- **FR-015** Resolved config MUST be cached with invalidation on any ancestor
  change.
- **FR-016** Resolution MUST be traceable: the result MUST record which node
  supplied each value.

**Catalogue exposure**

- **FR-017** The service MUST expose the capability catalogue (feature 003) so the
  console can render what is available, enabled, and why something is unavailable.
- **FR-018** It MUST expose integration schemas (feature 007) so the console can
  render credential forms without hard-coding vendor fields.

**Templates**

- **FR-019** Configuration templates MUST be applicable to a node, producing a
  reviewable diff before application.
- **FR-020** Shipped golden templates MUST cover common use cases: incident triage,
  CI failure investigation, cost investigation, postmortem authoring, alert-fatigue
  reduction, DR validation, and observability advisory.

**Audit**

- **FR-021** Every change MUST be audited with actor, timestamp, node, field,
  previous value, and new value.
- **FR-022** Audited values MUST pass the guardrail engine so a mistakenly-entered
  secret is not preserved in the audit trail in plaintext.

### Key entities

| Entity | Description |
|---|---|
| **ConfigNode** | A position in the hierarchy holding partial configuration |
| **EffectiveConfig** | The merged result for a node, with per-value provenance |
| **FieldPolicy** | Locked, required, approval-gated, allowed values, max values |
| **ConfigSchema** | The declared shape and validation rules |
| **ConfigTemplate** | A reusable configuration bundle applicable to a node |
| **ConfigAudit** | The change record |

## Success criteria

- **SC-001** Deep merge is correct across a four-level hierarchy — a golden test
  pins dict-merge and list-replace behaviour.
- **SC-002** A locked field cannot be overridden by any descendant, at any depth.
- **SC-003** Effective config resolution stays within its latency budget on a
  four-level hierarchy with a large configuration.
- **SC-004** A reference to a non-existent capability fails validation at write,
  not at investigation time.
- **SC-005** Every value in an effective config can name the node that supplied it.
- **SC-006** Cache invalidation is correct: changing an org value changes every
  descendant's next resolution.
- **SC-007** A secret-shaped value is rejected with a pointer to the vault.
- **SC-008** Applying a golden template produces a reviewable diff and, once
  applied, a working configuration.

## Out of scope

- Identity and RBAC (feature 014)
- Approval workflow machinery (feature 015)
- Configuration UI (feature 021)
- Credential values (feature 007 — config holds references, never secrets)

## Clarifications

| Question | Resolution |
|---|---|
| Why do lists replace rather than merge? | Adopted from Swapnil deliberately. List merging requires identity semantics per list, which means control keys, which means a configuration language. Replacement is predictable and explains itself. |
| Where do prompts live — config or code? | Prompt *defaults* are code constants in `config/prompts/`; prompt *overrides* are configuration. That way a fresh deployment works with no configuration, and customisation is a config change rather than a fork. |
| Can a team see its parent's configuration? | It sees its own effective config with provenance (FR-016). Whether it may read sibling or ancestor raw config is an RBAC question, resolved in feature 014. |
| What stops config from becoming a second codebase? | The declared schema (FR-010). Configuration is a closed set of typed fields, not arbitrary key-value storage. |
