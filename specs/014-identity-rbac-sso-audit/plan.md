# Plan — 014 Identity, RBAC, SSO, and Audit

## Summary

Adopt Swapnil's identity layer — RBAC, OIDC, impersonation, audit — and harden it
with boundary-enforced permission checks verified by route enumeration, an
append-only audit guard at the database level, and a tested break-glass path.

## Technical context

| Aspect | Choice |
|---|---|
| Human auth | OIDC Authorization Code with PKCE; provider configured per org |
| Session | Signed, short-lived cookie with idle and absolute limits; server-side revocation list |
| Machine auth | Bearer tokens, stored as a salted hash, prefixed for identification |
| Permission checks | FastAPI dependencies at the route boundary |
| Route enumeration | A test walking the router and asserting each privileged route declares a permission |
| Audit immutability | Database-level trigger rejecting `UPDATE` and `DELETE` on the audit table |
| Revocation | Short-TTL cache with an explicit invalidation broadcast on revoke |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | Audit records are the evidence trail for every privileged action |
| II | Session lifetimes, token expiry, inactivity thresholds, break-glass duration are named constants |
| III | Approvals (feature 017) are attributable to a principal because of this feature |
| IV | Token values are hashed; credential *access* is audited without exposing values |
| V | Runtime-agnostic |
| VI | No dependency on any external identity SaaS beyond the operator's own OIDC provider |
| VII | N/A |
| VIII | `platform/identity/` tier 3; routes in `gateway` tier 1 |
| IX | Capability execution carries the acting principal for audit |
| X | Identity data stays in the operator's database; OIDC talks only to their provider |
| XI | Access through `IdentityRepository` and `AuditRepository` |
| XII | Route-enumeration and audit-immutability tests written first |
| XIII | Provenance headers |

**Violations:** none.

## Project structure

```
platform/identity/
├── models.py            # Principal, Role, Permission, Grant, Token, Session
├── permissions.py       # the permission catalogue and role definitions
├── authorisation.py     # node-scoped permission resolution
├── tokens.py            # issue, hash, verify, revoke, expire, warn
├── sessions.py          # issue, validate, idle and absolute limits
├── oidc.py              # PKCE flow, claims, group mapping
├── sso_config.py        # provider settings, mapping, test-before-activate
├── impersonation.py     # time-limited admin context switch
├── break_glass.py       # local admin path, time-limited, prominently audited
└── audit/
    ├── recorder.py      # write path with durable fallback
    ├── export.py        # SIEM-ingestible export
    └── guard.py         # append-only enforcement

gateway/http/security/
├── dependencies.py      # boundary permission checks
└── route_permissions.py # the declared route → permission map

tests/security/
├── test_route_permissions.py    # SC-001
└── test_audit_immutability.py   # SC-003
```

## Role and permission model

| Role | Summary |
|---|---|
| `owner` | Everything, including org lifecycle and owner assignment. At least one required per org. |
| `admin` | Configuration, identity, credentials, approvals, impersonation. No org deletion. |
| `operator` | Configuration within scope, credentials, run investigations, approve remediation. |
| `responder` | Run investigations, approve remediation, read configuration. |
| `viewer` | Read investigations, reports, memory, and configuration. No writes. |

Permissions are atomic and node-scoped. A grant at a node applies to that node and
its descendants (FR-009), matching the configuration hierarchy so the two mental
models are the same.

## Boundary enforcement (FR-008, SC-001)

Every privileged route declares its permission through a dependency:

```python
@router.post("/config/{node_id}", dependencies=[requires(Permission.CONFIG_WRITE)])
```

`tests/security/test_route_permissions.py` walks the mounted router and asserts
every non-public route appears in `route_permissions.py` with a declared
permission. A new route without one fails CI — which is the only way a check of
this kind survives a growing codebase.

## Audit immutability (FR-023, SC-003)

Three layers:

1. `AuditRepository` exposes append and read only — no update or delete method.
2. A database trigger rejects `UPDATE` and `DELETE` on the audit table.
3. A test attempts modification through both the repository and raw SQL, and
   asserts both fail.

Retention policies exempt audit records (FR-026).

## Implementation phases

### Phase 1 — Model and enforcement contracts (test-first)
Permission catalogue, route-enumeration test, audit-immutability test,
last-owner-protection test. All red.

### Phase 2 — Principals and authorisation
Models, node-scoped permission resolution, boundary dependencies, denial messages
naming the required permission and scope.

### Phase 3 — Tokens
Issue with hashing and one-time display, verification, expiry, immediate
revocation, inactivity policy, expiry warnings, bulk revocation.

### Phase 4 — Sessions and OIDC
PKCE flow, claim extraction, group-to-team mapping with the no-claims fallback,
test-before-activate, idle and absolute limits.

### Phase 5 — Impersonation and break-glass
Time-limited impersonation recording both principals; local admin break-glass with
prominent auditing.

### Phase 6 — Audit
Recorder with durable fallback and alerting, the append-only guard, SIEM export.

### Phase 7 — Integration
Wire principals through the runtime so capability execution and approvals are
attributable; audit every action class in FR-025.

## Complexity tracking

| Item | Justification |
|---|---|
| Route enumeration test | A permission model is only as good as its weakest unguarded route. Enumeration turns "we should remember to add a check" into a build failure. |
| Database-level audit guard | Application-level immutability is one ORM call away from being bypassed. The trigger is what makes the audit log evidence rather than a log. |
| Break-glass local admin | An identity-provider outage during an incident, locking the operator out of their incident tool, is a realistic and severe failure. Time-limiting and prominent auditing bound the risk. |
| Node-scoped permissions mirroring the config hierarchy | Two different scoping models (one for config, one for permissions) would produce a permanent source of confusion. One tree, two uses. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Swapnil | `config_service/src/core/admin_rbac.py` | ADAPT → `permissions.py`, `authorisation.py` |
| Swapnil | `config_service/src/core/oidc.py` | ADOPT |
| Swapnil | `config_service/src/core/security.py` | ADAPT → `tokens.py`, `sessions.py` |
| Swapnil | `config_service/src/core/impersonation.py` | ADOPT |
| Swapnil | `config_service/src/core/audit_log.py` | ADAPT → `audit/recorder.py` with fallback and guard |
| Swapnil | `config_service/src/api/routes/{admin,auth_me,sso,security,team}.py` | ADAPT → boundary dependencies |
| Swapnil | Token audit, expiry, and bulk-revocation flows | ADOPT |
| Swapnil | `config_service/src/api/auth.py` | ADAPT |
| Tracer | `platform/auth/` JWT helpers | REFERENCE — superseded |
| Tracer | Clerk integration | REJECT — hosted SaaS dependency |

## Risks

| Risk | Mitigation |
|---|---|
| A new route ships without a permission check | SC-001 route enumeration fails CI |
| Revocation cache leaves a window | Short TTL plus explicit invalidation broadcast on revoke; SC-002 asserts immediacy |
| SSO misconfiguration locks everyone out | Test-before-activate (FR-015, SC-006) plus break-glass (FR-002, SC-007) |
| Audit volume overwhelms storage | Audit is exempt from deletion but exportable (FR-027); operators archive externally and the export is verified by SC-008 |
| Impersonation abused | Time-limited, separately audited, visually distinct in the console (FR-017, FR-018), and every action records both principals (SC-004) |
| Last owner removed | Explicit refusal (FR-011, SC-005) |
