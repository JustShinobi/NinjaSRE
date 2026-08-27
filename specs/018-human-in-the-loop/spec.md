# Feature 018 — Human in the Loop

- **Wave:** 4 — Action Governance
- **Branch:** `feat/018-human-in-the-loop`
- **Status:** Draft
- **Depends on:** 004, 014, 015, 016
- **Blocks:** 021, 022

## Summary

The interaction layer between an investigating agent and the humans around it: the
agent asking a clarifying question, a human injecting context mid-run, a human
taking over, and every approval or question reaching the person at the surface
they are already using — and closing everywhere at once when answered.

## User scenarios

### Primary story

Mid-investigation the agent cannot determine whether a traffic spike was a planned
launch. It asks. The question appears in the incident's Slack thread with three
options. The on-call engineer taps one. The agent incorporates the answer and
continues — without anyone opening a console.

### Acceptance scenarios

1. **Given** the agent needs information only a human has, **when** it invokes the
   handoff capability, **then** a question is raised at the active surface and the
   loop waits.
2. **Given** a question with structured options, **when** it is presented, **then**
   the human can answer by selection or free text.
3. **Given** a question that expires, **when** the timeout elapses, **then** the
   agent receives a structured no-answer result and continues reasoning.
4. **Given** an investigation running, **when** a human sends additional context,
   **then** it is queued and merged at the next turn boundary.
5. **Given** several messages sent in quick succession, **when** they are merged,
   **then** they arrive as one numbered guidance block, not several interruptions.
6. **Given** a question or approval raised, **when** it is answered on any surface,
   **then** it closes immediately on all others.
7. **Given** a human takes over an investigation, **when** they do, **then** the
   agent pauses, the human's actions are recorded under their principal, and the
   agent can be resumed with the human's actions in context.
8. **Given** a long-running investigation, **when** it reaches a configurable
   duration, **then** a progress notification is sent so nobody is waiting blind.
9. **Given** an investigation with a pending question, **when** the session is
   resumed later, **then** the pending question is still answerable or is clearly
   marked expired.

### Edge cases

- A question raised in a channel the requester has left.
- Two humans answering simultaneously on different surfaces.
- A queued message arriving during the final turn after tool access was stripped.
- Takeover while a sub-agent is mid-flight.
- A question whose answer arrives after the investigation concluded.
- An answer containing content the guardrails must redact.

## Requirements

### Functional

**Agent-initiated questions**

- **FR-001** A handoff capability MUST let the agent ask a question, with optional
  structured options and a stated reason for needing the answer.
- **FR-002** The question MUST be routed to the surface the investigation
  originated from, plus any surface the team configured for escalation.
- **FR-003** A question MUST have a timeout with a structured no-answer result on
  expiry (FR acceptance 3).
- **FR-004** An answer MUST be attributed to the answering principal and recorded
  in the trace.
- **FR-005** Answers MUST pass the guardrail engine before entering the agent's
  context.
- **FR-006** The agent MUST NOT be able to ask a question that requests a
  credential or secret; such a question MUST be refused at the capability
  boundary.

**Human-initiated context**

- **FR-007** A human MUST be able to add context to a running investigation from
  any surface.
- **FR-008** Messages MUST be debounced and merged at the next turn boundary into
  one numbered guidance block.
- **FR-009** A merge MUST emit an event so the human sees their input was received.
- **FR-010** Context added after the final tool-stripped turn MUST NOT reintroduce
  tool access.

**Takeover and resumption**

- **FR-011** A human MUST be able to pause an investigation and take over.
- **FR-012** During takeover, actions MUST be attributed to the human principal and
  recorded in the same trace.
- **FR-013** The agent MUST be resumable with the human's actions present in
  context.
- **FR-014** Takeover MUST safely interrupt in-flight sub-agents.

**Cross-surface consistency**

- **FR-015** A question or approval raised on multiple surfaces MUST close on all
  of them when answered on one.
- **FR-016** Concurrent answers MUST resolve to the first, with the second told the
  question was already answered.
- **FR-017** A pending interaction MUST survive session persistence and be
  answerable or clearly expired on resumption.

**Progress and attention**

- **FR-018** An investigation exceeding a configurable duration MUST emit a
  progress notification.
- **FR-019** Notifications MUST respect cooldown so a long run does not spam.
- **FR-020** An investigation requiring attention (pending question, pending
  approval) MUST be distinguishable in run listings.

### Key entities

| Entity | Description |
|---|---|
| **Question** | An agent-raised request for human input, with options and timeout |
| **Answer** | A human response with principal attribution |
| **QueuedMessage** | Human-added context awaiting merge |
| **GuidanceBlock** | The merged, numbered form injected at a turn boundary |
| **Takeover** | A human-controlled interval within an investigation |
| **Interaction** | The common supertype of question and approval for cross-surface closure |
| **AttentionState** | Whether a run is waiting on a human |

## Success criteria

- **SC-001** A question answered on one surface closes on all others within the
  configured propagation budget.
- **SC-002** Concurrent answers resolve deterministically to one, with the other
  informed.
- **SC-003** Question timeout produces a structured result and the investigation
  reaches a conclusion.
- **SC-004** Five messages sent within the debounce window arrive as one numbered
  guidance block.
- **SC-005** A question requesting a credential is refused at the capability
  boundary.
- **SC-006** Takeover mid-sub-agent leaves a consistent, resumable state, and the
  human's actions appear in the same trace.
- **SC-007** A pending question survives session persistence and remains
  answerable, or is clearly marked expired, on resumption.
- **SC-008** Progress notifications respect cooldown across a long run.

## Out of scope

- Approval decision semantics (feature 015)
- Remediation approval content (feature 017)
- Per-surface rendering (features 021, 022)
- Notification transport (feature 023)

## Clarifications

| Question | Resolution |
|---|---|
| Why can the agent not ask for a credential? | Constitution Article IV. Asking a human to paste an API key into a chat thread reintroduces exactly the exposure the credential proxy exists to remove — and the value would then live in the trace. |
| Is takeover different from just cancelling? | Yes. Cancellation ends the run; takeover pauses it, records human actions in the same trace, and allows resumption with those actions in context. The trace stays a single coherent record of how the incident was handled. |
| What if a question is never answered? | It times out (FR-003) and the agent continues with a structured no-answer result. An investigation blocked indefinitely on an unanswered question is worse than one that concludes with a stated uncertainty. |
| Why merge messages rather than deliver each immediately? | Delivering mid-turn would mean either interrupting a model call or holding messages inconsistently. Merging at turn boundaries is deterministic, and numbering preserves the human's ordering. |
