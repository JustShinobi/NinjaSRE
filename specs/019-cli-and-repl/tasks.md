# Tasks — 019 CLI and Interactive REPL

## Phase 1 — Contracts (test-first)

- **T001** Publish JSON output schemas for every command under `--json` (FR-007);
  write the validation test (SC-002). Red.
- **T002** Document the exit-code contract (FR-008); write the assertion test.
- **T003** Write the slash-command no-LLM test with a call counter (SC-008). Red.
- **T004** Write the credential-never-on-disk test: no credential in shell history,
  config files, or output (SC-006). Red.
- **T005** Write the degradation test: 80 columns, no colour, no Unicode, piped
  (SC-005). Red.
- **T006** Write the Ctrl+C test including mid-sub-agent cancellation (SC-003). Red.
- **T007** Write the session-resumption fidelity test (SC-004). Red.

## Phase 2 — CLI core

- **T008** `surfaces/cli/app.py`: typer root with shell completion.
- **T009** `surfaces/cli/output/degradation.py`: colour, Unicode, and pipe
  detection (FR-021, FR-022); confirm SC-005.
- **T010** [P] `surfaces/cli/output/tables.py`: width-adaptive rendering.
- **T011** [P] `surfaces/cli/output/json_.py`: schema-conformant JSON emission.
- **T012** `surfaces/cli/client.py`: local in-process or remote REST selection
  (FR-009).
- **T013** `commands/investigate.py`: run against a file or a description, report
  to stdout and file.
- **T014** [P] `commands/runs.py`: list, show, replay.
- **T015** [P] `commands/config.py`: show, set, diff.
- **T016** [P] `commands/schedule.py`: list, add, remove.
- **T017** [P] `commands/memory.py`: search, stats.
- **T018** [P] `commands/providers.py`: list, verify.
- **T019** [P] `commands/integrations.py`: list, setup, verify.
- **T020** Confirm SC-002 JSON schema validation across all commands.

## Phase 3 — Onboarding

- **T021** `wizard/flow.py`: guided sequence — provider, credentials, integrations,
  verification.
- **T022** Per-provider onboarding modules for all nine providers.
- **T023** Integration setup prompts generated from integration schemas
  (feature 013's exposure).
- **T024** Credential entry writing to the vault, never to a file or argument
  (FR-010); confirm SC-006.
- **T025** End-of-flow verification producing a working configuration.
- **T026** `commands/onboard.py` wiring the flow.

## Phase 4 — REPL core

- **T027** `surfaces/repl/loop.py`: TTY detection, clear non-TTY exit (FR-012).
- **T028** `surfaces/repl/input.py`: `prompt_toolkit` with history and completion.
- **T029** `surfaces/repl/streaming.py`: render thoughts, capability calls,
  sub-agent activity, results (FR-019).
- **T030** `surfaces/repl/session.py`: list, resume, compact, new (FR-017).
- **T031** Confirm SC-004 resumption fidelity.
- **T032** Ctrl+C cancellation through the runtime safe-point mechanism (FR-016);
  confirm SC-003.
- **T033** Action routing: literal leading `/` only; everything else to the agent
  (FR-015).
- **T034** Record the no-intent-routing prohibition in `surfaces/repl/AGENTS.md`.

## Phase 5 — Slash commands and interaction

- **T035** `surfaces/repl/commands/registry.py` with local-only execution
  (FR-014).
- **T036** [P] `/help` generated from the registry, `/status`, `/cost` (FR-020).
- **T037** [P] `/sessions`, `/resume`, `/compact`, `/new`, `/exit`.
- **T038** [P] `/integrations`, `/runs`.
- **T039** [P] `/effort`, `/model`.
- **T040** `surfaces/repl/interaction.py`: inline questions and approvals (FR-018).
- **T041** [P] `/approve`, `/answer`, `/takeover`, `/cancel`.
- **T042** Confirm SC-008: every slash command runs with zero LLM calls.

## Phase 6 — Diagnostics and lifecycle

- **T043** `commands/doctor.py`: diagnose configuration, connectivity, provider
  availability, integration health (FR-011).
- **T044** Fixture set of deliberately broken configurations; assert `doctor`
  identifies each (SC-007).
- **T045** Redacted diagnostic bundle the operator can review before sharing.
- **T046** `commands/update.py`.
- **T047** `commands/uninstall.py` removing all local data on confirmation
  (FR-004).

## Phase 7 — Installers

- **T048** `install/install.sh`: no elevated privileges, user-local fallback with
  the PATH instruction (FR-001, FR-002).
- **T049** [P] `install/install.ps1`.
- **T050** Artefact integrity verification in both (FR-005).
- **T051** No-writable-PATH fixture test.
- **T052** [P] Homebrew tap (FR-003).
- **T053** Measure installation to first successful investigation on all three
  platforms (SC-001).
- **T054** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Install to first investigation under 10 minutes, three platforms (SC-001)
- [ ] Every command's `--json` validates against its schema (SC-002)
- [ ] Ctrl+C cancels cleanly, including mid-sub-agent (SC-003)
- [ ] Resumed sessions match pre-suspension state (SC-004)
- [ ] Output readable at 80 columns, no colour, piped (SC-005)
- [ ] No credential in history, config, or output (SC-006)
- [ ] `doctor` diagnoses every broken-config fixture (SC-007)
- [ ] Every slash command runs with zero LLM calls (SC-008)
- [ ] `make verify` green
