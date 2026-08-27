# Plan — 013 Hierarchical Configuration Service

## Summary

Adopt Swapnil's hierarchical config core — deep merge, locked and required fields,
effective-config computation — and add a declared schema, per-value provenance,
capability and integration reference validation, and secret rejection.

## Technical context

| Aspect | Choice |
|---|---|
| Storage | `ConfigRepository` over Postgres with JSONB payloads per node |
| Merge | Pure function, root-to-leaf, dicts recurse and everything else replaces |
| Schema | Pydantic models per config section, composed into one root schema |
| Provenance | Merge records the source node per leaf value |
| Cache | Keyed on node plus a hierarchy version bumped by any ancestor write |
| Validation | Two passes: schema shape, then cross-reference against the live catalogue |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | FR-016 — every effective value names its source node |
| II | Config supplies the tunable bounds; defaults remain named constants in code so a missing config never means an unbounded loop |
| III | FR-007 — approval-gated fields route through the same approval machinery as production writes |
| IV | FR-013 — config never holds secrets; it holds references resolved by the vault |
| V | Runtime reads config through one resolution path regardless of runtime |
| VI | Model selection per role is config, so provider choice is an operator decision |
| VII | Memory, strategy, topology, and knowledge ablation switches are config fields |
| VIII | `platform/config_service/` tier 3; HTTP routes in `gateway` tier 1 |
| IX | FR-012, FR-017 — capability references validated against the real catalogue |
| X | Configuration lives in the operator's database |
| XI | Access through `ConfigRepository` only |
| XII | Merge goldens and lock-enforcement tests written first |
| XIII | Provenance headers; adopted from Swapnil with attribution |

**Violations:** none.

## Project structure

```
platform/config_service/
├── hierarchy.py          # tree operations, ancestry, reparenting
├── merge.py              # deep merge with per-value provenance
├── effective.py          # effective-config computation + cache
├── schema/
│   ├── root.py           # the composed configuration schema
│   ├── agents.py         # prompts, topology, model per role
│   ├── capabilities.py   # enable/disable, overrides
│   ├── integrations.py   # references (never secrets)
│   ├── policies.py       # memory, knowledge, masking, guardrails, approvals
│   └── surfaces.py
├── field_policy.py       # locked, required, approval-gated, allowed, max
├── validation.py         # shape + cross-reference + secret rejection
├── catalogue.py          # capability and integration schema exposure
├── templates/
│   ├── engine.py         # apply with diff preview
│   └── golden/           # shipped use-case templates
└── audit.py
```

## Merge semantics (FR-002, FR-003)

```
merge(base, override):
    for each key in override:
        if key absent in base            -> take override
        elif both values are dicts       -> merge recursively
        else                             -> take override (lists, scalars, type mismatch)
```

No control keys. A four-level hierarchy merges as
`merge(merge(merge(org, division), team), squad)`. SC-001 pins this with a golden
fixture covering nested dicts, list replacement, type mismatch, and null handling.

## Configuration schema (FR-010)

| Section | Contents |
|---|---|
| `agents` | System prompts per agent role, sub-agent topology, iteration budgets |
| `models` | Provider and model per role: investigator, sub-agents, intake, diagnose, extraction, embedding |
| `capabilities` | Enable/disable per capability or tag; per-capability parameter overrides |
| `integrations` | Which integrations are active; references to vault entries; non-secret settings (region, site, base URL) |
| `policies.memory` | Episodic memory read/write switches |
| `policies.strategy` | Strategy synthesis switches |
| `policies.knowledge` | Topology and knowledge base switches |
| `policies.masking` | Level and custom patterns |
| `policies.guardrails` | Active rule set |
| `policies.approvals` | Which side-effect levels require approval; autonomous allow-list |
| `surfaces` | Per-surface settings: channels, report destinations, notification sinks |

Each section is a Pydantic model. Adding a field is a schema change with a
migration for defaults, not free-form key addition.

## Golden templates (FR-020)

| Template | Configures |
|---|---|
| `incident-triage-slack` | Slack surface, triage prompts, PagerDuty and observability integrations |
| `ci-failure-investigation` | VCS and CI integrations, code-historian sub-agent, PR-comment reporting |
| `cost-investigation` | Cloud billing integrations, cost-focused prompts, scheduled runs |
| `postmortem-authoring` | Knowledge base write proposals, document sync, postmortem template |
| `alert-fatigue-reduction` | Aggressive noise triage, deduplication window, alert-source analytics |
| `dr-validation` | Scheduled validation runs, topology checks, read-only enforcement |
| `observability-advisory` | Metric and log coverage analysis, recommendation-only prompts |

Each ships as a template plus a smoke test proving it produces a working
configuration (SC-008).

## Implementation phases

### Phase 1 — Merge and hierarchy (test-first)
Merge goldens, lock enforcement, deep-hierarchy cases. `hierarchy.py`, `merge.py`.

### Phase 2 — Schema
Section models, root composition, defaults sourced from code constants.

### Phase 3 — Field policies
Locked, required, approval-gated, allowed values, max values; the
lock-after-override conflict path.

### Phase 4 — Validation
Shape validation, cross-reference against the live catalogue, secret rejection.

### Phase 5 — Effective config
Root-to-leaf computation with per-value provenance, caching keyed on hierarchy
version, invalidation on ancestor write.

### Phase 6 — Catalogue and templates
Capability and integration schema exposure, template engine with diff preview, the
seven golden templates.

### Phase 7 — Audit and integration
Change auditing with guardrail filtering, runtime resolution wiring, latency
validation.

## Complexity tracking

| Item | Justification |
|---|---|
| Declared schema rather than free-form JSON | Free-form config becomes an untyped second codebase that nothing validates and nobody can document. A closed schema is what makes FR-012 (reference validation) and the console's form rendering possible. |
| Per-value provenance | Without it, "why is this team using that model?" requires manually walking the tree. With a four-level hierarchy that question is asked constantly. |
| Prompt defaults in code, overrides in config | A fresh deployment must work with zero configuration. Putting defaults in config means a bootstrap problem and a migration for every prompt improvement. |
| Approval-gated fields | Prompts and capability enablement change agent behaviour in production. Treating them as ordinary config would let one team member silently change how incidents are investigated. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Swapnil | `config_service/src/core/hierarchical_config.py` | ADOPT |
| Swapnil | `config_service/src/core/merge.py` | ADOPT |
| Swapnil | `config_service/src/core/config_models.py` | ADAPT → typed section schemas |
| Swapnil | `config_service/src/core/default_prompts.py` | ADAPT → defaults move to `config/prompts/` |
| Swapnil | `config_service/src/core/{config_cache,cache}.py` | ADAPT |
| Swapnil | `config_service/src/core/{skills_catalog,tools_catalog}.py` | ADAPT → `catalogue.py` |
| Swapnil | `config_service/src/core/integration_config.py` | ADAPT → integration references |
| Swapnil | `config_service/src/core/{yaml_config,yaml_validator,yaml_seeder}.py` | ADAPT → template engine |
| Swapnil | `config_service/golden_templates/` (10 templates) | ADOPT → seven consolidated |
| Swapnil | `config_service/src/core/audit_log.py` | ADAPT → `audit.py` |
| Swapnil | `config_service/src/core/dependency_validator.py` | ADAPT → cross-reference validation |

## Risks

| Risk | Mitigation |
|---|---|
| Resolution latency on deep hierarchies | Cached on hierarchy version (FR-015); SC-003 validates the budget on a four-level tree with a large config |
| Schema rigidity blocks legitimate customisation | Sections are extensible by adding typed fields; the constraint is deliberate, and the alternative (free-form) is unmaintainable |
| Config drift between environments | Templates with diff preview (FR-019) make environment configuration reproducible and reviewable |
| Locks used to freeze teams out of legitimate changes | Locks are audited and visible with their locking node in the provenance output, so the constraint is explainable rather than mysterious |
| Secrets entered into config by mistake | FR-013 rejects at write, and FR-022 filters the audit trail so a rejected attempt is not preserved in plaintext |
