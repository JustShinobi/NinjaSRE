# Plan — 019 CLI and Interactive REPL

## Summary

Adapt Tracer's CLI, interactive shell, and cross-platform installers — the most
mature surface in either upstream — rebranding, removing telemetry, and wiring
them to NinjaSRE's vault, config service, and interaction model.

## Technical context

| Aspect | Choice |
|---|---|
| CLI framework | `typer` with rich help and shell completion |
| Rendering | `rich` for tables, streaming, and progress; graceful degradation without colour or Unicode |
| REPL | `prompt_toolkit` for input, history, and completion |
| Transport | Direct in-process for local deployments; the REST client (feature 020) for remote |
| Credentials | Entered through the vault API; never written to config or history |
| Installers | Shell script and PowerShell script, artefact integrity verified; Homebrew tap |
| Output contract | Every command emits a documented JSON shape under `--json` |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | Streaming shows evidence as it is gathered; `runs replay` reconstructs any past run |
| II | `/effort` and `/model` change bounded parameters; the bounds themselves stay named constants |
| III | `/approve` presents the full approval context; no CLI path bypasses gating |
| IV | FR-010, SC-006 — credentials go to the vault, never to disk or history |
| V | The CLI drives the canonical runtime |
| VI | `providers verify` and `onboard` treat all nine providers equally, local included |
| VII | `memory search` and `memory stats` expose what was learned |
| VIII | `surfaces/cli/` and `surfaces/repl/` are tier 1; they never import `gateway` |
| IX | `/help` and completion are generated from capability metadata |
| X | No telemetry; `doctor` produces a local report the operator chooses to share |
| XI | Storage reached through the core, never directly |
| XII | Slash-command no-LLM assertion and JSON schema validation written first |
| XIII | Provenance headers; installers adapted with attribution |

**Violations:** none.

## Project structure

```
surfaces/cli/
├── app.py                   # typer application root
├── commands/
│   ├── onboard.py  investigate.py  integrations.py  providers.py
│   ├── runs.py     config.py       schedule.py      memory.py
│   ├── doctor.py   update.py       uninstall.py
├── output/
│   ├── json_.py             # --json shapes with published schemas
│   ├── tables.py            # rich tables with width adaptation
│   └── degradation.py       # no-colour, no-Unicode, piped detection
├── wizard/
│   ├── flow.py              # onboarding orchestration
│   ├── providers/<name>.py  # per-provider onboarding
│   └── integrations/        # per-integration setup prompts
└── client.py                # local in-process or remote REST

surfaces/repl/
├── loop.py                  # the REPL itself
├── input.py                 # prompt_toolkit wiring, history, completion
├── commands/                # one module per slash command
│   └── registry.py
├── streaming.py             # live event rendering
├── interaction.py           # inline questions and approvals
└── session.py               # list, resume, compact, new

install/
├── install.sh
├── install.ps1
└── homebrew/
```

## Slash command catalogue

| Command | Effect |
|---|---|
| `/help` | Command reference, generated from the registry |
| `/status` | Session state, active run, attention items |
| `/cost` | Token usage and cost, per session and per run |
| `/sessions` | List resumable sessions |
| `/resume <id>` | Restore a session |
| `/compact` | Compact the transcript, preserving evidence references |
| `/new` | Start a fresh session |
| `/exit` | Leave |
| `/integrations [list\|verify]` | Integration state and health |
| `/runs [list\|show\|replay]` | Run history and replay |
| `/effort <level>` | Reasoning effort, where the provider supports it |
| `/model <name>` | Switch model for this session |
| `/approve` | Present and resolve a pending approval |
| `/answer` | Answer a pending question |
| `/takeover` | Pause the agent and take control |
| `/cancel` | Cancel the in-flight investigation |

Every one executes locally (FR-014), asserted by SC-008's call counter.

## Action routing (FR-015)

A line beginning with a literal `/` is a slash command. **Everything else goes to
the agent.** No regex matching, no keyword heuristics, no deterministic bypass for
inputs that "look like" a known command.

This rule is inherited directly from Tracer's documented experience: intent
shortcuts around the agent path create behaviour that does not appear in the trace,
cannot be scored by the evaluation suite, and diverges from every other surface.
The prohibition is recorded in `surfaces/repl/AGENTS.md`.

## Implementation phases

### Phase 1 — Contracts (test-first)
JSON output schemas, exit-code contract, slash-command no-LLM assertion,
credential-never-on-disk assertion. All red.

### Phase 2 — CLI core
Typer application, output layer with degradation, local and remote client
selection, `investigate`, `runs`, `config`.

### Phase 3 — Onboarding
Guided flow, per-provider onboarding, integration setup with vault entry and
verification, ending in a verified working configuration.

### Phase 4 — REPL core
Loop, input handling with history and completion, streaming renderer, session
management, Ctrl+C cancellation.

### Phase 5 — Slash commands and interaction
The full catalogue, inline question and approval handling, takeover.

### Phase 6 — Diagnostics and lifecycle
`doctor` against a set of deliberately broken configurations, `update`,
`uninstall` with full local data removal.

### Phase 7 — Installers
Shell and PowerShell installers with integrity verification and the PATH
instruction path, Homebrew tap, cross-platform time-to-first-investigation
validation.

## Complexity tracking

| Item | Justification |
|---|---|
| A REPL alongside a web console | They serve different moments. Duplication is limited to rendering, since both consume the same event stream from the same core. |
| Two installer scripts plus Homebrew | Upstream evidence shows the one-command install is the single biggest factor in whether someone tries the tool. Homebrew covers the users who will not pipe a script to a shell. |
| Forbidding intent shortcuts | Costs some perceived responsiveness for common phrasings. Buys trace completeness, evaluation validity, and cross-surface consistency — all three constitutional. |
| `--json` on every command | Makes the CLI scriptable, which is how operators automate around it. A published schema per command (SC-002) is what makes that contract dependable. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `surfaces/cli/` | ADAPT — commands, structure, wizard |
| Tracer | `surfaces/interactive_shell/` | ADAPT → `surfaces/repl/` |
| Tracer | `surfaces/interactive_shell/command_registry/` | ADAPT → slash-command registry |
| Tracer | `surfaces/interactive_shell/ui/` | ADAPT → streaming, tables, layout, degradation |
| Tracer | `install.sh`, `install.ps1` | ADAPT — rebranded, telemetry removed, integrity verification retained |
| Tracer | Homebrew tap | ADAPT |
| Tracer | `surfaces/interactive_shell/AGENTS.md` action-selection rule | ADOPT — the no-intent-routing prohibition |
| Tracer | `tools/interactive_shell/actions/` | ADAPT → capability-driven actions |
| Tracer | `platform/terminal/` | ADAPT |

## Risks

| Risk | Mitigation |
|---|---|
| Windows terminal divergence | Cross-platform CI runs the REPL through a scripted session on all three OSes; degradation layer handles the differences explicitly |
| Streaming rendering breaks when piped | Piped detection switches to line-oriented output (FR-022, SC-005) |
| Ctrl+C leaves inconsistent state | Cancellation goes through the runtime's safe-point mechanism (feature 004), not a signal kill; SC-003 tests it mid-sub-agent |
| Credentials leak into shell history | Never accepted as command arguments — always prompted and written to the vault (FR-010, SC-006) |
| Installer breaks on an unusual PATH setup | FR-002's user-local fallback with an explicit PATH instruction, tested against a no-writable-PATH fixture |
