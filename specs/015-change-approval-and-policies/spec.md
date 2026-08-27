# Feature 015 — Change Approval and Security Policies

- **Wave:** 3 — Control Plane
- **Branch:** `feat/015-change-approval-and-policies`
- **Status:** Draft
- **Depends on:** 013, 014
- **Blocks:** 012, 017, 018, 021

## Summary

One approval mechanism serving every gated change in the system — configuration
edits, prompt changes, capability enablement, agent-proposed knowledge, and (in
feature 017) production remediation. Plus the organisation-level security policies
that decide what requires approval in the first place.

## User scenarios

### Primary story

A security lead sets an org policy: prompt changes and capability enablement
require approval. A team engineer edits the investigation prompt; the change enters
a queue rather than taking effect. A reviewer sees a diff, the requester's
rationale, and the blast radius, and approves. The change applies and is audited.

### Acceptance scenarios

1. **Given** a policy requiring approval for prompt changes, **when** an engineer
   edits a prompt, **then** the change is queued and the current value stays in
   effect.
2. **Given** a queued change, **when** a reviewer opens it, **then** they see a
   diff, the requester, the rationale, and which teams the change would affect.
3. **Given** a reviewer approves, **when** the decision is recorded, **then** the
   change applies atomically and is audited with both requester and approver.
4. **Given** a reviewer rejects, **when** the decision is recorded, **then** the
   change is discarded with the reason preserved and visible to the requester.
5. **Given** the requester is also the only available reviewer, **when** policy
   forbids self-approval, **then** the change cannot be approved by them.
6. **Given** a queued change that has expired, **when** the expiry policy runs,
   **then** the change is closed as expired and the requester is notified.
7. **Given** a change queued against a value that has since changed, **when**
   approval is attempted, **then** the conflict is detected and the reviewer must
   re-review against current state.
8. **Given** an org policy setting a maximum value for a field, **when** any team
   attempts to exceed it, **then** the write is rejected regardless of role.
9. **Given** multiple queued changes to the same target, **when** one is approved,
   **then** the others are marked conflicted and re-reviewed rather than applied
   blindly.

### Edge cases

- A change whose target node is deleted while it is queued.
- An approver who loses the required permission between queuing and decision.
- A very large diff that must remain reviewable.
- Two reviewers deciding concurrently.
- A policy change that would retroactively require approval for queued changes.
- An approval arriving at a surface (chat) after the requester left the channel.

## Requirements

### Functional

**Approval workflow**

- **FR-001** A single approval mechanism MUST serve all gated change types:
  configuration, prompts, capability enablement, knowledge proposals, and
  remediation.
- **FR-002** A pending change MUST record: type, target, proposed value, current
  value, requester, rationale, creation time, and expiry.
- **FR-003** A pending change MUST NOT take effect before approval, and there MUST
  be no code path that applies one without a recorded decision.
- **FR-004** Approval MUST apply the change atomically, recording requester and
  approver.
- **FR-005** Rejection MUST preserve the reason and surface it to the requester.
- **FR-006** Pending changes MUST expire after a configurable period, closing with
  notification.
- **FR-007** Self-approval MUST be configurable per policy and MUST default to
  forbidden.
- **FR-008** A change queued against a value that has since changed MUST be
  detected as conflicted and require re-review.
- **FR-009** Approving one of several changes to the same target MUST mark the
  others conflicted rather than applying them.
- **FR-010** Approval permission MUST be re-checked at decision time, not only at
  queue time.

**Review presentation**

- **FR-011** A pending change MUST expose a structured diff of current versus
  proposed.
- **FR-012** It MUST expose its blast radius: which nodes and teams the change
  would affect through inheritance.
- **FR-013** Large diffs MUST remain reviewable through summarisation with
  drill-down, never truncation without indication.

**Security policies**

- **FR-014** Org-level policies MUST control: which change types require approval,
  which side-effect levels require approval, self-approval permission, locked
  settings, maximum values, required settings, and allowed values.
- **FR-015** Policies MUST control token lifecycle defaults: expiry, warning
  window, inactivity revocation.
- **FR-016** Policy constraints MUST be enforced regardless of role — an owner
  cannot exceed a maximum the policy sets without changing the policy itself.
- **FR-017** Policy changes MUST themselves be auditable and MAY be
  approval-gated.
- **FR-018** A policy change MUST NOT retroactively invalidate already-approved
  changes, and MUST be explicit about its effect on queued ones.

**Routing and notification**

- **FR-019** A pending change MUST notify eligible reviewers through configured
  surfaces.
- **FR-020** Approval MUST be actionable from the console and from chat surfaces.
- **FR-021** A decision made on one surface MUST immediately close the request on
  all others.

**Audit**

- **FR-022** Every queue, approval, rejection, expiry, and conflict MUST be
  audited.
- **FR-023** The audit record MUST retain the diff, so a past decision is
  reconstructable.

### Key entities

| Entity | Description |
|---|---|
| **PendingChange** | A queued change awaiting decision |
| **ChangeType** | configuration, prompt, capability, knowledge, remediation |
| **Decision** | Approve or reject, with approver, timestamp, and reason |
| **SecurityPolicy** | Org-level constraints governing what requires approval |
| **ReviewerSet** | The principals eligible to decide a given change |
| **BlastRadius** | The nodes and teams a change would affect |
| **Conflict** | Detected divergence between queued and current state |

## Success criteria

- **SC-001** No code path applies a gated change without a recorded decision —
  asserted by attempting it through every entry point.
- **SC-002** Self-approval is refused when policy forbids it, including via
  impersonation.
- **SC-003** A conflicting change is detected and blocked from blind application.
- **SC-004** Approval permission is re-checked at decision time — a reviewer who
  lost permission cannot approve.
- **SC-005** A decision on one surface immediately closes the request on all
  others.
- **SC-006** Policy maximums are enforced against every role including owner.
- **SC-007** The audit record for a past decision reconstructs the exact diff that
  was approved.
- **SC-008** A 10,000-line diff remains reviewable with summarisation and
  drill-down.

## Out of scope

- Remediation execution and rollback (feature 017)
- Review UI (feature 021) — this feature provides API and state machine
- Chat approval rendering (feature 022)

## Clarifications

| Question | Resolution |
|---|---|
| Why one mechanism for config changes and production remediation? | They are the same problem: a proposed action, a reviewer, a decision, an audit record. Two mechanisms would mean two state machines, two audit shapes, and two surfaces to keep consistent. |
| Is self-approval ever legitimate? | For a single-operator deployment, yes — which is why it is a policy (FR-007) rather than a prohibition. The default is forbidden because the multi-person case is where the control matters. |
| What happens to queued changes when policy changes? | FR-018: policy changes are explicit about their effect on the queue and never retroactively invalidate approved changes. Silent reinterpretation of pending state is worse than requiring re-review. |
| Why re-check permission at decision time? | Between queuing and decision a reviewer may have been offboarded. Checking only at queue time would let a departed employee's pending authority apply a change. |
