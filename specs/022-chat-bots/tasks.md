# Tasks — 022 Chat Surfaces

## Phase 1 — Contract and abstraction (test-first)

- **T001** `gateway/chat/port.py`: `ChatPlatform` protocol — receive, stream,
  render interaction, resolve identity.
- **T002** `gateway/chat/contract.py` plus `tests/contract/chat/`: the ten shared
  behaviours from the plan, parameterised over four platforms (SC-001). Red.
- **T003** Write the unmapped-identity refusal test per platform (SC-005). Red.
- **T004** Write the error-sanitisation fault-injection test per platform
  (SC-006). Red.
- **T005** Write the oversized-report delivery test (SC-004). Red.
- **T006** Write the disconnect-resilience test (SC-007). Red.
- **T007** Write the concurrent-approval test across two channels (SC-008). Red.
- **T008** Add chat constants to `config/constants/surfaces.py`: streaming edit
  interval, per-platform message limits, backoff parameters.

## Phase 2 — Shared behaviour

- **T009** `gateway/chat/streaming.py`: single progress message edited in place at
  a bounded interval (FR-004).
- **T010** Rate-limit backoff with coalescing; never drop content (FR-009).
- **T011** `gateway/chat/chunking.py`: split or attach oversized reports (FR-005);
  confirm SC-004.
- **T012** `gateway/chat/identity.py`: platform user → `ChatIdentity` → principal
  (FR-002).
- **T013** Refusal with actionable instructions for unmapped users (FR-003);
  confirm SC-005.
- **T014** `gateway/chat/routing.py`: channel → team, per-channel alert-source and
  severity settings (FR-022, FR-023).
- **T015** `gateway/chat/history.py`: thread-history ingestion through the
  guardrail engine, treated as data not instructions (FR-006).
- **T016** `gateway/chat/commands.py`: shared command catalogue rendered per
  platform.
- **T017** Error sanitisation at the chat sink (FR-008); confirm SC-006.
- **T018** Interaction closure integration with feature 018 (FR-007).

## Phase 3 — Slack

- **T019** `gateway/slack/socket_mode.py` and HTTP events, selectable by
  configuration (FR-011).
- **T020** `gateway/slack/events.py`: mention and message handling, thread binding.
- **T021** `gateway/slack/output_sink.py`: streaming and report delivery.
- **T022** `gateway/slack/interactions.py`: Block Kit approvals and questions
  (FR-012).
- **T023** Slash commands from the shared catalogue (FR-013).
- **T024** `gateway/slack/intro.py`: channel-join introduction (FR-014).
- **T025** `gateway/slack/identity.py`: Slack user mapping.
- **T026** Contract suite green for Slack.

## Phase 4 — Microsoft Teams

- **T027** `gateway/teams/app.py`: Bot Framework wiring, channel and DM support
  (FR-015).
- **T028** `gateway/teams/cards.py`: Adaptive Cards for reports, approvals,
  questions (FR-016).
- **T029** `gateway/teams/stream_handler.py`: in-place card updates.
- **T030** `gateway/teams/identity.py`: Teams auth flow for identity mapping
  (FR-017).
- **T031** Contract suite green for Teams.

## Phase 5 — Telegram

- **T032** `gateway/telegram/client.py`: Bot API with polling or webhook (FR-018).
- **T033** `gateway/telegram/events.py`: group and direct chat handling.
- **T034** `gateway/telegram/keyboards.py`: inline keyboards for approvals and
  questions (FR-019).
- **T035** `gateway/telegram/output_sink.py`: streaming and report delivery.
- **T036** Contract suite green for Telegram.

## Phase 6 — Discord

- **T037** `gateway/discord/client.py`: gateway connection, guild channels and
  threads (FR-020).
- **T038** `gateway/discord/events.py`: mention and command handling.
- **T039** `gateway/discord/components.py`: application commands and message
  components (FR-021).
- **T040** `gateway/discord/output_sink.py`: streaming and report delivery.
- **T041** `gateway/discord/worker.py`: background task handling with correct
  cancellation reaping.
- **T042** Contract suite green for Discord (SC-001 complete).

## Phase 7 — Resilience and verification

- **T043** Reconnection handling per platform: run continues, report delivered on
  reconnect or via fallback sink (FR-010); confirm SC-007.
- **T044** Bot removed from a channel mid-investigation: report delivered via
  fallback, situation recorded.
- **T045** Concurrent approvals across channels resolve to one decision; confirm
  SC-008.
- **T046** Expired-approval interaction: clear message rather than a silent no-op.
- **T047** Streaming validation: 200-event investigation within every platform's
  rate limits (SC-003).
- **T048** Cross-surface closure validation with the console (SC-002).
- **T049** Per-platform setup documentation including minimum permission scopes
  (FR-024).
- **T050** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] All four platforms pass the shared contract suite (SC-001)
- [ ] Decisions propagate across surfaces within budget (SC-002)
- [ ] 200-event streaming within all rate limits (SC-003)
- [ ] Oversized reports delivered complete (SC-004)
- [ ] Unmapped users cannot act privileged on any platform (SC-005)
- [ ] No exception detail in any chat message (SC-006)
- [ ] Connectivity loss does not fail a run (SC-007)
- [ ] Concurrent approvals resolve to one decision (SC-008)
- [ ] `make verify` green
