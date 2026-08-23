# Feature 014 — Identity, RBAC, SSO, and Audit

- **Wave:** 3 — Control Plane
- **Branch:** `feat/014-identity-rbac-sso-audit`
- **Status:** Draft
- **Depends on:** 006, 013
- **Blocks:** 015, 016, 017, 018, 020, 021, 022

## Summary

Who is acting, what they may do, and an immutable record of what they did. Users
authenticate through the operator's identity provider; machine clients use scoped,
expiring tokens; every privileged action is attributable to a principal and
recorded in an append-only audit log.

## User scenarios

### Primary story

An enterprise connects its OIDC provider. Engineers sign in with corporate SSO and
land in the teams their group membership maps to. A Slack bot authenticates with a
team-scoped token that expires in 90 days. Every configuration change, credential
write, and approved remediation names the human or token that caused it.

### Acceptance scenarios

1. **Given** an OIDC provider is configured, **when** a user signs in, **then**
   they are authenticated, their groups map to teams, and a session is issued.
2. **Given** a user with the `viewer` role, **when** they attempt a configuration
   write, **then** it is denied with a message naming the required permission.
3. **Given** a team-scoped token, **when** it is used, **then** it can act only
   within that team and only within its granted permissions.
4. **Given** a token past its expiry, **when** it is used, **then** the request is
   rejected and the attempt is audited.
5. **Given** an admin impersonating a team, **when** they act, **then** every
   action records both the real principal and the impersonated context.
6. **Given** any privileged action, **when** it completes, **then** an audit record
   is written that cannot subsequently be modified or deleted.
7. **Given** a token unused beyond the inactivity threshold, **when** the policy
   runs, **then** it is revoked automatically and the owner is notified.
8. **Given** a revoked token, **when** it is used, **then** the request is rejected
   immediately, without waiting for a cache to expire.
9. **Given** an SSO outage, **when** an admin needs access, **then** a documented
   break-glass path exists, is time-limited, and is audited prominently.

### Edge cases

- A user whose group membership changes between sessions.
- An OIDC provider returning no group claims.
- Concurrent sessions for the same user across surfaces.
- A token whose team is deleted.
- Clock skew affecting token expiry validation.
- An audit write failing while the audited action has already succeeded.
- The last admin removing their own admin role.

## Requirements

### Functional

**Authentication**

- **FR-001** Human authentication MUST support OIDC (Authorization Code with PKCE)
  against an operator-configured provider.
- **FR-002** A local admin account MUST exist for bootstrap and break-glass, with
  a documented, time-limited, prominently-audited procedure.
- **FR-003** Machine authentication MUST use scoped bearer tokens.
- **FR-004** Tokens MUST carry: org, team, permission set, expiry, and an
  optional description.
- **FR-005** Token values MUST be stored hashed; the plaintext is shown once at
  creation and never retrievable.
- **FR-006** Sessions MUST have an idle timeout and an absolute lifetime, both
  named constants.

**Authorisation**

- **FR-007** Roles MUST include at least: `owner`, `admin`, `operator`,
  `responder`, `viewer`, with documented permission sets.
- **FR-008** Permissions MUST be checked at the API boundary, not inside business
  logic, so no path can bypass them.
- **FR-009** Authorisation MUST be scoped by node: a permission granted at a node
  applies to that node and its descendants.
- **FR-010** A denial MUST name the required permission and the scope, so the
  user knows what to request.
- **FR-011** The system MUST refuse an operation that would leave an org with no
  owner.

**SSO and mapping**

- **FR-012** Group-to-team mapping MUST be configurable, including a default team
  for unmapped users.
- **FR-013** Group membership MUST be re-evaluated at each sign-in.
- **FR-014** A provider returning no group claims MUST fall back to the configured
  default, with the fallback recorded.
- **FR-015** SSO configuration MUST be testable before activation, so a
  misconfiguration cannot lock everyone out.

**Impersonation**

- **FR-016** An admin MUST be able to act in a team's context for support purposes.
- **FR-017** Impersonated actions MUST record both the real principal and the
  impersonated context, and MUST be visually distinct in the console.
- **FR-018** Impersonation MUST be time-limited and separately auditable.

**Token lifecycle**

- **FR-019** Tokens MUST support explicit revocation with immediate effect.
- **FR-020** Policy MUST support automatic revocation after an inactivity period.
- **FR-021** Expiry warnings MUST be issued a configurable period in advance.
- **FR-022** Bulk revocation MUST be available for incident response.

**Audit**

- **FR-023** The audit log MUST be append-only; the storage layer MUST reject
  updates and deletes.
- **FR-024** Every audit record MUST carry: principal, impersonation context if
  any, timestamp, action, target, outcome, and source address.
- **FR-025** Audited actions MUST include at minimum: authentication, token
  lifecycle, configuration changes, credential changes, approvals, remediation
  execution, impersonation, and permission changes.
- **FR-026** Audit records MUST be exempt from retention deletion.
- **FR-027** Audit MUST be exportable in a machine-readable format for external
  SIEM ingestion.
- **FR-028** An audit write failure MUST be treated as a serious error: the action
  is recorded to a durable fallback and an alert raised.

### Key entities

| Entity | Description |
|---|---|
| **Principal** | A human user or a machine token |
| **Role** | A named permission set |
| **Permission** | An atomic capability, checked at the API boundary |
| **Grant** | A role assigned to a principal at a node, inherited by descendants |
| **Token** | A hashed, scoped, expiring machine credential |
| **Session** | An authenticated human session with idle and absolute limits |
| **SsoConfig** | Provider settings and group-to-team mapping |
| **Impersonation** | A time-limited admin context switch |
| **AuditEvent** | An immutable record of a privileged action |

## Success criteria

- **SC-001** Every privileged API route has an explicit permission check —
  asserted by a test enumerating routes against a permission map, so a new route
  without a check fails CI.
- **SC-002** A revoked token is rejected immediately, with no cache window.
- **SC-003** Audit records cannot be modified or deleted through any code path,
  including direct repository access.
- **SC-004** Impersonated actions record both principals — asserted across every
  audited action type.
- **SC-005** An org can never be left without an owner.
- **SC-006** SSO configuration can be tested before activation without affecting
  live sign-in.
- **SC-007** Break-glass access works with SSO unavailable, is time-limited, and
  produces a prominent audit trail.
- **SC-008** Audit export produces valid, complete records ingestible by a standard
  SIEM.

## Out of scope

- Configuration semantics (feature 013)
- Approval workflow (feature 015)
- Login UI (feature 021)
- Credential values (feature 007)

## Clarifications

| Question | Resolution |
|---|---|
| Why check permissions at the API boundary rather than in business logic? | A check inside business logic is one that a new call path can bypass. At the boundary, SC-001's route enumeration makes an unchecked route a build failure. |
| Is a local admin account a weakness? | It is a deliberate break-glass path (FR-002). An SSO outage that locks an operator out of their own incident-response tool during an incident is a worse failure. It is time-limited and prominently audited. |
| Why append-only audit at the storage layer? | An audit log an admin can edit is not evidence. The delete guard lives in the database so no application bug can remove records. |
| What if the audit write fails? | FR-028: durable fallback plus an alert. Silently proceeding unaudited is the one outcome that is not acceptable. |
