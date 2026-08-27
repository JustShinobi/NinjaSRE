# Feature 022 — Chat Surfaces

- **Wave:** 5 — Surfaces
- **Branch:** `feat/022-chat-bots`
- **Status:** Draft
- **Depends on:** 008, 014, 018, 020

## Summary

Investigation where incidents are already discussed: Slack, Microsoft Teams,
Telegram, and Discord. Mention the bot, get a streaming investigation in the
thread, approve remediation inline, and answer the agent's questions without
leaving the conversation.

## User scenarios

### Primary story

An alert lands in `#incidents`. Someone types `@ninjasre what's happening with
checkout?`. The bot investigates in-thread with live progress, posts an
evidence-backed root cause, and asks for approval to roll back the deployment —
which the on-call engineer grants with one tap, from their phone.

### Acceptance scenarios

1. **Given** the bot is mentioned in a channel, **when** it responds, **then** the
   investigation runs in a thread and streams progress there.
2. **Given** an investigation in a thread, **when** a human adds a message,
   **then** it becomes mid-run context (feature 018).
3. **Given** an approval is raised, **when** it appears in chat, **then** it shows
   target, proposed change, blast radius, and rollback plan, and is decidable
   inline.
4. **Given** a decision made in the console, **when** the chat approval is open,
   **then** it closes there immediately.
5. **Given** a chat user, **when** they act, **then** their chat identity maps to a
   NinjaSRE principal and permissions apply.
6. **Given** an unmapped chat user, **when** they attempt a privileged action,
   **then** it is refused with instructions on how to be granted access.
7. **Given** a long investigation, **when** it streams, **then** updates are
   rate-limited and edited in place rather than posting a message per event.
8. **Given** a report exceeding the platform's message limit, **when** it is
   posted, **then** it is split or attached without losing content.
9. **Given** a thread with prior context, **when** an investigation starts,
   **then** the thread history informs it, subject to guardrail filtering.

### Edge cases

- The bot removed from a channel mid-investigation.
- A platform rate limit hit during streaming.
- A user reacting to an approval after it expired.
- Two people approving simultaneously in different channels.
- A message containing content the guardrails must redact before it enters agent
  context.
- A platform outage mid-investigation.
- A thread that outlives the session's retention.

## Requirements

### Functional

**Common behaviour across platforms**

- **FR-001** All four platforms MUST support: start an investigation by mention or
  command, stream progress in a thread, deliver the final report, resolve
  interactions inline, and add mid-run context.
- **FR-002** Chat identities MUST map to NinjaSRE principals; permissions apply as
  on every other surface.
- **FR-003** An unmapped user attempting a privileged action MUST be refused with
  actionable instructions.
- **FR-004** Streaming MUST rate-limit and edit in place, not post per event.
- **FR-005** Reports exceeding a platform's message limit MUST be split or
  attached, never truncated silently.
- **FR-006** Thread history MAY inform an investigation, and MUST pass the
  guardrail engine before entering agent context.
- **FR-007** Interactions MUST close across surfaces on first decision
  (feature 018).
- **FR-008** No exception detail may appear in a chat message (Constitution
  Article IV, feature 008).
- **FR-009** Platform rate limits MUST be respected with backoff; a rate-limited
  update MUST NOT drop content.
- **FR-010** Losing platform connectivity MUST NOT fail a running investigation;
  the report is delivered on reconnect or through a fallback sink.

**Slack**

- **FR-011** MUST support Socket Mode and HTTP events, selectable by configuration.
- **FR-012** MUST use interactive components for approvals and questions.
- **FR-013** MUST support slash commands for common operations.
- **FR-014** MUST post an introduction on joining a channel explaining usage.

**Microsoft Teams**

- **FR-015** MUST support channel and direct-message conversations.
- **FR-016** MUST use Adaptive Cards for reports, approvals, and questions.
- **FR-017** MUST support the Teams authentication flow for identity mapping.

**Telegram**

- **FR-018** MUST support group and direct chats.
- **FR-019** MUST use inline keyboards for approvals and questions.

**Discord**

- **FR-020** MUST support guild channels and threads.
- **FR-021** MUST use application commands and message components.

**Configuration**

- **FR-022** Channel-to-team routing MUST be configurable, so one workspace can
  serve multiple teams.
- **FR-023** Per-channel settings MUST control which alert sources auto-post there
  and at what severity.
- **FR-024** Bot setup MUST be documented per platform, including the minimum
  permission scopes required.

### Key entities

| Entity | Description |
|---|---|
| **ChatPlatform** | Slack, Teams, Telegram, or Discord adapter |
| **ChatIdentity** | A platform user mapped to a NinjaSRE principal |
| **ChatThread** | A conversation bound to an investigation |
| **StreamingMessage** | The in-place-edited progress message |
| **InteractiveElement** | The platform-native control for an approval or question |
| **ChannelRouting** | Channel-to-team and alert-source configuration |

## Success criteria

- **SC-001** All four platforms pass the same behavioural contract suite.
- **SC-002** An approval decided on one platform closes on every other surface
  within the propagation budget.
- **SC-003** Streaming a 200-event investigation stays within every platform's
  rate limits.
- **SC-004** A report exceeding the message limit is delivered complete, by
  splitting or attachment.
- **SC-005** An unmapped user cannot perform a privileged action on any platform.
- **SC-006** No chat message contains exception detail — asserted by fault
  injection per platform.
- **SC-007** Platform connectivity loss mid-investigation does not fail the run,
  and the report still arrives.
- **SC-008** Concurrent approvals in different channels resolve to one decision.

## Out of scope

- Outbound notification sinks (feature 023)
- Report formatting (feature 023 — this feature renders per platform)
- Console (feature 021)

## Clarifications

| Question | Resolution |
|---|---|
| Why four platforms rather than Slack only? | The upstreams cover different ones — Slack, Telegram, and Discord from Tracer; Teams from Swapnil. Teams in particular is where a large share of enterprise incident conversation happens, and it is the platform most often missing from open-source tooling. |
| Is thread history a prompt-injection risk? | Yes, and it is treated as data, never instructions. It passes the guardrail engine (FR-006) and enters as observed context; the agent's instructions come from its system prompt and the operator's configuration only. |
| How is identity handled for someone with no account? | Refused with instructions (FR-003). Auto-provisioning from a chat identity would let anyone in a workspace act as a principal. |
| What if the platform is down mid-run? | The investigation continues (FR-010). Chat is a surface, not the runtime. The report is delivered on reconnect or via a fallback notification sink. |
