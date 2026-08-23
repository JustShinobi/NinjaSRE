# Tasks — 018 Human in the Loop

## Phase 1 — Interaction contracts (test-first)

- **T001** `core/agent/interaction/models.py`: `Interaction` supertype,
  `Question`, `Answer`, `AttentionState`, states `pending | answered | expired |
  superseded`.
- **T002** Add interaction constants to `config/constants/investigation.py`:
  question timeout, debounce window, progress interval, notification cooldown,
  closure propagation budget.
- **T003** Write the cross-surface closure test (SC-001). Red.
- **T004** Write the concurrent-answer test: deterministic winner, loser informed
  (SC-002). Red.
- **T005** Write the persistence test: pending question survives restart (SC-007).
  Red.
- **T006** Write the secret-refusal test (SC-005). Red.
- **T007** Write the debounce-merge test: five messages, one numbered block
  (SC-004). Red.
- **T008** Write the takeover-mid-sub-agent test (SC-006). Red.

## Phase 2 — Questions

- **T009** `capabilities/tools/system/ask_human/tool.py`: declared capability with
  question text, optional structured options, and a stated reason (FR-001).
- **T010** Secret-request refusal at the capability boundary (FR-006); confirm
  SC-005.
- **T011** `core/agent/handoff.py`: raise the question, suspend the loop, await.
- **T012** Surface routing: originating surface plus configured escalation
  surfaces (FR-002).
- **T013** Timeout with a structured no-answer result (FR-003); confirm SC-003
  by asserting the investigation concludes.
- **T014** Answer attribution to the answering principal, recorded in the trace
  (FR-004).
- **T015** Guardrail filtering of answers before they enter agent context (FR-005).

## Phase 3 — Closure and concurrency

- **T016** `core/agent/interaction/registry.py`: pending interactions per run.
- **T017** `core/agent/interaction/closure.py`: decision event published to all
  surfaces (FR-015); confirm SC-001.
- **T018** First-writer-wins conditional transition; the loser is told the question
  was already answered (FR-016); confirm SC-002.
- **T019** `core/agent/interaction/persistence.py`: pending interactions stored
  with the session (FR-017).
- **T020** Resumption path: still answerable, or clearly marked expired; confirm
  SC-007.
- **T021** Handling a question raised in a channel the requester has left:
  escalation surfaces receive it, and the situation is recorded.

## Phase 4 — Message queue

- **T022** Extend `core/agent/message_queue.py`: accept from any surface (FR-007).
- **T023** Debounce window and merge at `on_turn_end` into a numbered guidance
  block (FR-008); confirm SC-004.
- **T024** Emit `message_queued` on merge so the human sees receipt (FR-009).
- **T025** Final-turn guard: context added after tool stripping does not
  reintroduce tool access (FR-010).
- **T026** Guardrail filtering of queued content.

## Phase 5 — Takeover

- **T027** `core/agent/takeover.py`: pause the loop at a safe point (FR-011).
- **T028** Sub-agent reaping during pause (FR-014).
- **T029** Human actions recorded under the human principal in the same run trace
  (FR-012).
- **T030** Resume with human actions present in agent context (FR-013).
- **T031** Manual conclusion path: the human ends the investigation, and the run
  records that.
- **T032** Confirm SC-006: takeover mid-sub-agent leaves a consistent, resumable
  state.

## Phase 6 — Attention and progress

- **T033** `core/agent/interaction/attention.py`: attention state for run listings
  (FR-020).
- **T034** Progress notification on the configured interval (FR-018).
- **T035** Cooldown so a long run does not spam (FR-019); confirm SC-008.
- **T036** Attention state exposed in the run history API for the console.

## Phase 7 — Approval unification

- **T037** Migrate feature 015's approval requests onto the `Interaction`
  abstraction.
- **T038** Verify approvals inherit cross-surface closure, persistence,
  concurrency resolution, and attention state.
- **T039** Regression: feature 015's and feature 017's success criteria still pass
  after unification.
- **T040** Surface contract documentation: what a surface must implement to render
  and resolve an interaction (consumed by features 021 and 022).
- **T041** Operator documentation: question timeouts, escalation surfaces, takeover
  procedure, progress tuning.
- **T042** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Answering on one surface closes all others within budget (SC-001)
- [ ] Concurrent answers resolve deterministically (SC-002)
- [ ] Timeout lets the investigation conclude (SC-003)
- [ ] Five rapid messages merge into one numbered block (SC-004)
- [ ] Credential-requesting questions refused (SC-005)
- [ ] Takeover mid-sub-agent is consistent and resumable (SC-006)
- [ ] Pending questions survive restart (SC-007)
- [ ] Progress notifications respect cooldown (SC-008)
- [ ] Approvals unified onto the same abstraction
- [ ] `make verify` green
