# Feature 019 — CLI and Interactive REPL

- **Wave:** 5 — Surfaces
- **Branch:** `feat/019-cli-and-repl`
- **Status:** Draft
- **Depends on:** 002, 005, 007, 013, 014, 016, 018

## Summary

The `ninjasre` command: a one-command installer, a scriptable CLI, and a stateful
interactive REPL. This is how the platform is operated, debugged, and demonstrated
— and the surface where a full investigation is fastest to run without opening a
browser.

## User scenarios

### Primary story

An engineer installs with one command, runs `ninjasre onboard` to configure a
provider and two integrations, and then types `ninjasre` to enter a REPL where
they describe an incident in plain language and watch the investigation stream,
with `/cost` telling them what it spent and `/resume` bringing it back tomorrow.

### Acceptance scenarios

1. **Given** a supported OS, **when** the installer runs, **then** `ninjasre` is on
   `PATH` without requiring elevated privileges, and the PATH instruction is
   printed if a shell restart is needed.
2. **Given** no configuration, **when** `ninjasre onboard` runs, **then** it guides
   provider selection, credential entry into the vault, integration setup, and
   verification, ending in a working configuration.
3. **Given** a configured install, **when** `ninjasre investigate -i alert.json`
   runs, **then** an investigation executes and the report is written to stdout and
   to a file.
4. **Given** a TTY, **when** `ninjasre` runs with no subcommand, **then** a REPL
   starts; without a TTY it exits with a clear message rather than hanging.
5. **Given** a REPL session, **when** the user types a slash command, **then** it
   executes locally without an LLM call.
6. **Given** an investigation streaming, **when** the user presses Ctrl+C, **then**
   the investigation cancels without ending the session or losing state.
7. **Given** a prior session, **when** `/resume` is used, **then** the session
   restores with its transcript, evidence, and accounting.
8. **Given** a pending question or approval, **when** it is raised during a REPL
   investigation, **then** it is presented inline and answerable in place.
9. **Given** the platform is running remotely, **when** the CLI is pointed at it,
   **then** the same commands operate against the remote deployment.

### Edge cases

- A terminal without colour or Unicode support.
- A very wide or very narrow terminal.
- Output piped to a file or another process.
- Ctrl+C during a sub-agent dispatch.
- A REPL session whose token expires mid-use.
- Windows terminal behaviour differing from POSIX.
- An installer running where no writable directory is on `PATH`.

## Requirements

### Functional

**Installation**

- **FR-001** Installers MUST exist for macOS, Linux (shell) and Windows
  (PowerShell), and MUST NOT require elevated privileges.
- **FR-002** With no writable `PATH` directory available, the installer MUST
  install to a user-local directory and print the exact command to update `PATH`.
- **FR-003** A package-manager path (Homebrew) MUST be available.
- **FR-004** `ninjasre update` and `ninjasre uninstall` MUST exist, with uninstall
  removing all local data on confirmation.
- **FR-005** The installer MUST verify the downloaded artefact's integrity.

**CLI**

- **FR-006** Commands MUST include: `onboard`, `investigate`, `integrations`
  (`list`, `setup`, `verify`), `providers` (`list`, `verify`), `runs`
  (`list`, `show`, `replay`), `config` (`show`, `set`, `diff`), `schedule`
  (`list`, `add`, `remove`), `memory` (`search`, `stats`), `doctor`, `update`,
  `uninstall`.
- **FR-007** Every command MUST support `--json` for machine-readable output.
- **FR-008** Exit codes MUST be meaningful and documented, so the CLI is scriptable.
- **FR-009** The CLI MUST operate against a local or a remote deployment,
  selected by configuration or a flag.
- **FR-010** Credentials MUST be entered into the vault; the CLI MUST NOT write
  them to a config file or shell history.
- **FR-011** `doctor` MUST diagnose configuration, connectivity, provider
  availability, and integration health, producing an actionable report.

**REPL**

- **FR-012** With no subcommand and a TTY, `ninjasre` MUST start a REPL; without a
  TTY it MUST exit with a clear message.
- **FR-013** Slash commands MUST include: `/help`, `/status`, `/cost`, `/sessions`,
  `/resume`, `/compact`, `/new`, `/exit`, `/integrations`, `/runs`, `/effort`,
  `/model`, `/approve`, `/answer`, `/takeover`, `/cancel`.
- **FR-014** Slash commands MUST execute locally with no LLM call.
- **FR-015** Natural-language input MUST route to the agent; no regex or keyword
  intent routing may bypass the agent path.
- **FR-016** Ctrl+C MUST cancel an in-flight investigation without ending the
  session or losing state.
- **FR-017** Sessions MUST be listable and resumable with transcript, evidence, and
  accounting intact.
- **FR-018** Pending questions and approvals MUST be presented inline and
  answerable in place (feature 018).
- **FR-019** Streaming output MUST render thoughts, capability calls, sub-agent
  activity, and results as they occur.
- **FR-020** `/cost` MUST report per-session and per-run token usage and cost.

**Presentation**

- **FR-021** Output MUST degrade gracefully without colour or Unicode support.
- **FR-022** Output MUST adapt to terminal width and MUST remain readable when
  piped.
- **FR-023** The local terminal is NOT an external surface: full error detail MAY
  be shown, while persisted and transmitted content is still guardrail-filtered.

### Key entities

| Entity | Description |
|---|---|
| **Command** | A CLI subcommand with arguments, output modes, and an exit-code contract |
| **ReplSession** | A stateful interactive session with transcript and accounting |
| **SlashCommand** | A locally-executed REPL directive |
| **OnboardingFlow** | The guided first-run configuration sequence |
| **Doctor** | The diagnostic report generator |

## Success criteria

- **SC-001** Installation to first successful investigation takes under 10 minutes
  on a clean machine, on all three platforms.
- **SC-002** Every command's `--json` output validates against a published schema.
- **SC-003** Ctrl+C during an investigation cancels cleanly and the session remains
  usable — including during a sub-agent dispatch.
- **SC-004** A resumed session's transcript, evidence, and accounting match the
  pre-suspension state exactly.
- **SC-005** Output is readable at 80 columns, without colour, and when piped.
- **SC-006** No credential ever appears in shell history, a config file, or CLI
  output.
- **SC-007** `doctor` correctly diagnoses each of a set of deliberately broken
  configurations.
- **SC-008** Every REPL slash command executes without an LLM call — asserted by a
  call counter.

## Out of scope

- REST API (feature 020)
- Web console (feature 021)
- Chat surfaces (feature 022)

## Clarifications

| Question | Resolution |
|---|---|
| Why a REPL when there is a web console? | Different jobs. The console is for teams reviewing and configuring; the REPL is for the engineer already in a terminal during an incident, and for anyone debugging the platform itself. Both drive the same core. |
| Why forbid keyword intent routing? | Adopted from Tracer's hard-won rule. Regex shortcuts around the agent path produce behaviour that is invisible in the trace, untestable by the evaluation suite, and divergent from every other surface. The only exception is a literal leading `/`. |
| Is the terminal really not an external surface? | For error detail, yes — the person running it is authenticated locally and already has more access than the message reveals. Anything persisted or transmitted is still filtered (FR-023). |
| Does the CLI need the full platform running? | For `investigate` against a local deployment, it starts what it needs. For a remote deployment, it is a thin client (FR-009). |
