# Plan — 021 Web Console

## Summary

Adapt Swapnil's Next.js console — the most complete UI in either upstream — as a
pure client of feature 020's REST API. Keep its information architecture,
rebuild its data layer against the new API, and add permission-aware rendering,
configuration provenance preview, and accessibility.

## Technical context

| Aspect | Choice |
|---|---|
| Framework | Next.js App Router with TypeScript |
| Package manager | pnpm |
| Data layer | Typed client generated from the OpenAPI spec (feature 020) |
| Streaming | `EventSource` with `Last-Event-ID` cursor recovery |
| State | Server components where possible; client state only for live streams and forms |
| Virtualisation | Windowed rendering for transcripts and large tables |
| Styling | Tailwind with a small component library; light and dark themes |
| Testing | Component tests, a role-matrix test, and automated accessibility checks |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | The trace view shows every capability call, argument, and result — evidence made inspectable |
| II | Budget and guardrail actions are rendered in the trace, so bounds are visible rather than invisible |
| III | FR-009 — approvals show blast radius and rollback plan; the console never executes a write directly |
| IV | FR-020, SC-006 — credentials post straight to the vault, never through console state |
| V | Renders the canonical runtime's events |
| VI | Provider and model selection are configuration surfaces, vendor-neutral |
| VII | The memory hub exposes episodes, strategies, and their effectiveness |
| VIII | `surfaces/console/` is tier 1 and never imports `gateway`; it calls the HTTP API |
| IX | The capability catalogue is rendered from metadata, never hard-coded |
| X | The console talks only to the operator's deployment |
| XI | No direct database access (FR-030) |
| XII | Role matrix, stream recovery, and accessibility tests written first |
| XIII | English UI with i18n scaffolding; provenance headers on adapted components |

**Violations:** none.

## Project structure

```
surfaces/console/
├── src/
│   ├── app/
│   │   ├── (auth)/                  # sign-in, SSO callback
│   │   ├── runs/                    # list, [runId] detail
│   │   ├── interactions/            # pending questions and approvals
│   │   ├── memory/                  # episodes, strategies, topology
│   │   ├── knowledge/               # documents, proposals
│   │   ├── config/                  # org tree, editor, templates
│   │   ├── catalogue/               # capabilities and integrations
│   │   ├── admin/                   # identity, tokens, audit, policies, SSO
│   │   └── onboarding/
│   ├── components/
│   │   ├── run/                     # transcript, trace, sub-agent expansion
│   │   ├── interaction/             # approval card, question card
│   │   ├── config/                  # tree, editor, effective preview, diff
│   │   ├── memory/                  # episode card, strategy editor, topology graph
│   │   └── common/
│   ├── lib/
│   │   ├── api/                     # generated typed client
│   │   ├── stream.ts                # EventSource with cursor recovery
│   │   ├── permissions.ts           # permission-aware rendering helpers
│   │   └── i18n/
│   └── test/
└── package.json
```

## Information architecture

| Area | Purpose |
|---|---|
| **Runs** | The default landing area. Filter by status, team, trigger, attention. |
| **Run detail** | One component for live and replay: transcript, trace, evidence, cost, report. |
| **Interactions** | Cross-run queue of everything waiting on a human. |
| **Memory** | Episodes, strategies with source traceability, topology explorer. |
| **Knowledge** | Documents, hierarchy, agent proposals awaiting review. |
| **Config** | Org tree, per-node editor with effective preview and provenance, templates. |
| **Catalogue** | Capabilities and integrations: available, enabled, unavailable with reasons. |
| **Admin** | Identity, tokens, audit, security policies, SSO. |
| **Onboarding** | First-run guided setup mirroring the CLI wizard. |

## Live and replay as one component (FR-002)

Both consume the same event vocabulary. The only difference is the source: a live
`EventSource` subscription versus a replay of the persisted event log. Building
them as one component is what guarantees a replayed investigation looks exactly
like the live one did — and is what makes SC-002's recovery path shared rather
than special-cased.

## Permission-aware rendering (FR-023, SC-004)

Rendering consults the principal's effective permissions and **omits** unavailable
actions. A role-matrix test walks every page as every role and asserts the absence
of write controls for read-only roles. Server-side authorisation (feature 014)
remains the real control; this is defence in depth and a usability property.

## Implementation phases

### Phase 1 — Contracts and harness (test-first)
Generated API client, role-matrix test skeleton, stream-recovery test,
accessibility harness. All red.

### Phase 2 — Auth and shell
Sign-in with SSO and token, session handling, navigation shell, permission-aware
rendering helpers, impersonation banner.

### Phase 3 — Runs
List with filters and attention state, detail component unified across live and
replay, transcript virtualisation, sub-agent expansion, cost display.

### Phase 4 — Interactions
Approval card with full context, question card, cross-surface closure without
refresh, rollback action within its window.

### Phase 5 — Memory and knowledge
Episode browse and search, strategy view with source episodes and editing,
topology explorer, knowledge documents and proposal review.

### Phase 6 — Configuration and catalogue
Org tree at scale, editor with effective preview and provenance, locked-field
display, queued-change marking, schema-generated integration forms with direct
vault posting, capability catalogue.

### Phase 7 — Admin, accessibility, polish
Identity and token management, audit browse and export, policy editing, SSO
configuration with test-before-activate, accessibility remediation, responsive
approval and monitoring flows.

## Complexity tracking

| Item | Justification |
|---|---|
| A separate TypeScript surface | A web console is what makes this a team platform rather than a personal tool. Keeping it a pure API client (FR-030) bounds the cost to rendering. |
| One component for live and replay | Marginally harder than two, and it is the only way to guarantee a replayed run looks like the live one — which is what makes the trace trustworthy as a review artefact. |
| Permission-aware omission rather than disabling | More rendering logic, but avoids leaking deployment configuration and removes an entire class of "why can't I click this" confusion. |
| Transcript virtualisation | Necessary rather than optional: real investigations produce thousands of events, and a console that stalls during an incident is not used during incidents. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Swapnil | `web_ui/` overall architecture and information design | ADAPT → `surfaces/console/` |
| Swapnil | `ConversationTranscript.tsx`, `InvestigationReport.tsx`, `TodoProgressPanel.tsx` | ADAPT |
| Swapnil | `web_ui/src/app/team/memory/{episodes,search,strategies}` | ADAPT → memory hub |
| Swapnil | `web_ui/src/app/admin/{config,org-tree,audit,pending-changes,templates,token-management,sso,security-policies}` | ADAPT |
| Swapnil | `web_ui/src/app/team/agent-runs/[runId]/trace` | ADAPT → unified run detail |
| Swapnil | `web_ui/src/app/team/knowledge/` | ADAPT |
| Swapnil | `RequirePermission.tsx`, `RequireRole.tsx` | ADAPT → omission rather than disabling |
| Swapnil | `NewInvestigationDrawer.tsx`, `ConversationComposer.tsx` | ADAPT |
| Swapnil | Remediation review and rollback pages | ADAPT → interaction queue |
| Tracer | Report formatters and renderers | REFERENCE → report presentation |

## Risks

| Risk | Mitigation |
|---|---|
| Business logic creeps into the console | FR-030 plus a review rule: any computation the CLI would also need belongs in the API. The generated client makes calling easier than reimplementing. |
| Large transcripts degrade the console during incidents | Virtualisation with a 10,000-event benchmark (SC-001) |
| Live stream recovery loses or duplicates events | Cursor-based recovery over feature 016's log, tested by an induced interruption (SC-002) |
| Permission drift between console and API | The API is the real control; the role-matrix test (SC-004) catches console-side drift |
| Configuration preview diverges from actual behaviour | SC-005 compares the preview against the server's computed effective config rather than reimplementing merge in TypeScript |
