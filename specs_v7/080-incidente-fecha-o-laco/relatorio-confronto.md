# Confrontation report — 080 O incidente fecha o laço

## Conclusion

This report was built in two passes on the same day, and both are reflected
below rather than one overwriting the other. **Pass one** found `tasks.md`
drifted in exactly the direction the dispatching brief named — all 92 boxes
unchecked, wrong for 32 of them, where the runbooks, the evidence collector
and its 31-case test suite, the confronto column, and the rewritten backlog
already existed and already passed their gates, exactly as `controle.md`
(a separate, prose-form control document for this feature) had claimed on
2026-08-23. Pass one also found, mid-audit, that three commits had landed
that same morning from the operator (`kyo@kyo.ninja`, not an agent): the
evidence collector had run for real against staging Postgres, proving half
of the read loop (User Story 2) with real data, while the destructive loop
remained provably unexecuted — the approval and outcome tables the collector
reads all came back at zero rows.

**Pass two** started after the coordinator reported the destructive loop had
now run end to end against real staging and the real hypervisor, and pointed
at `evidence/demo-2026-08-24/` as the record. That directory — an
`EVIDENCIA.md`, an `achados.md`, a `marco-zero.txt`, and eleven screenshots —
was read in full and the screenshots opened and inspected directly by this
audit, not summarised from the coordinator's message. It is real: CT122
stopped at 10:26:29Z, the alert fired on its own at 10:29:34, the webhook
accepted an authenticated `202` at 10:29:45, the incident opened, the
investigation recorded 13 events with two verbatim upstream failures (a
Proxmox `501`, a "no change source configured"), the report's headline was a
genuine sentence naming the correct node, and the incident **closed itself**
at 10:50:06 — `state: resolved`, `close_reason` naming the real cause,
`self_resolved: true`, the product not claiming credit for what a human did
by hand. Twenty more boxes are checked from this alone, verified against the
opened screenshots and the text files, not the coordinator's summary of them
— one claim (a Proxmox token holding `Administrator`) was reported in chat
but does not appear anywhere in the written record, and per the coordinator's
own instruction to trust the file over the message, its box stays unchecked.

**The proposal, approval, and execution stations did not happen, and the
evidence now proves why, rather than merely proving they hadn't yet.** This
deployment's entire catalogue holds exactly three write capabilities, and all
three are notifications (Alertmanager acknowledge, Pushover, Telegram) —
nothing anywhere acts on infrastructure. The desk composed 20 capabilities,
the gate registered per run, the tool ceiling of 40 was nowhere near hit (4
used). The agent was correct to propose nothing. That is the
`REPROVOU (produto)`/declared-acceptable outcome spec.md's own E7 edge case
already names, not an environment gap — and this report now marks it that
way rather than leaving it indistinguishable from "not yet reached."

Two real, new findings surfaced by this pass, neither a product defect:
eleven real screenshots exist and are genuinely full-page, but captured at
1280px wide rather than the 1920px `spec.md` and `tasks.md` both specify, and
the evidence collector never ran against this investigation's own
`run`/`incident` identifiers, so the whole-loop stations have strong
screenshot-and-prose evidence but not the SQL-literal artifact FR-024 asks
for. Four real product findings are named in `evidence/demo-2026-08-24/EVIDENCIA.md`
(incident title is the alert's name rather than a sentence; the incident
header attributes the wrong Proxmox node; guest discovery leaves the node
segment of `native_id` literally `unknown`; cost renders two ways on two
screens) — none assigned an owning feature yet, which is deliberately left to
whoever spends the wave's repair cycles with full context, not decided here.
The candidate finding from pass one (`prometheus_metric_statistics` → `400`
on an empty `start` parameter) did not recur in this run's four tool calls;
it stays open and unowned rather than being marked resolved on an absence of
one data point.

## Table

Convention for "Final status": **DONE** — the code, a test, or already-committed
evidence proves it; box checked. **NOT STARTED / PARTIAL, not done — reason
given** — box left unchecked, with the reason this table and the Evidence
section state; none are silent. No item in this feature had regressed
(**REGRESSED**) — everything `controle.md` claimed done on 2026-08-23 was
independently reconfirmed done today.

| Item | What `tasks.md` claimed (before) | What the code proved (before this audit) | Final status |
|---|---|---|---|
| T001 confirm wave merges + PASS, record tree commit | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE, and here is why** — the coordinator's own words: "the wave is not fully merged yet, several worktrees are still open" |
| T002 `make verify` before publish | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE, and here is why** — the coordinator's own words: "`make verify` is not green yet, four separate reds are being worked right now" |
| T003 publish via `make deploy-stg` **without** `COMPONENTS=` | unchecked | not run by this feature | **NOT DONE, and it is a named finding against the demo's own preparation** — the coordinator deployed with `COMPONENTS="app web"`, narrower than this exact task's own text; the credential proxy stayed on 30-hour-old code and cost an hour of wrong diagnosis. The task said the right thing; it was not followed. A full deploy is promised before the wave closes |
| T004 wait for Argo `Synced + Healthy` | unchecked | not read | **NOT DONE** — requires a live `ssh`/`kubectl` session this audit does not open |
| T005 confirm service responds, separately | unchecked | not read | **NOT DONE** — same reason as T004 |
| T006 record digest + Argo state in `EVIDENCIA.md` | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE** — depends on T003–T005 |
| T007 discover org identifier | unchecked | not written to `EVIDENCIA.md` §2, but used correctly | **DONE** — `evidence/E4-...txt`: `org=default` returns real, non-empty, org-scoped counts (5 turns, 4 calls, 1 evidence row); a wrong `:org` would return zero everywhere |
| T008 provider Verified, key from vault | unchecked | no screenshot | **DONE** — `evidence/demo-2026-08-24/antes-01-modelos.png`, opened and read in this pass: "Google Gemini · Verified" |
| T009 Proxmox connected, `/resources` real | unchecked | `evidence/E3-...txt`: `estate_resources` present count = **0** at 09:11 UTC | **DONE** — `evidence/demo-2026-08-24/antes-02-integracoes.png` ("Proxmox VE · Verified") and `antes-03-recursos.png` ("100 watched · 71 healthy · 0 degraded · 14 unhealthy") resolve pass one's timing gap: the sync happened after the 09:11 UTC reading |
| T010 Proxmox token privilege | unchecked | not read | **NOT DONE, and here is why** — the coordinator reported the token is `root@pam!infra` holding `Administrator` in chat, but that claim appears nowhere in `EVIDENCIA.md` or `achados.md` (swept for `root@pam`, `Administrator`, `VM.PowerMgmt`: zero matches). Per the coordinator's own instruction to trust the file over the message, this box stays unchecked |
| T011 operator confirms victim at window open | unchecked | not recorded | **DONE** — `evidence/demo-2026-08-24/EVIDENCIA.md:4-5`: "parado com autorização explícita do operador" |
| T012 victim `running`, confirmed | unchecked | not read | **DONE, proven a different way than a manual check** — `evidence/demo-2026-08-24/e5-01-relato.png`, the investigation's own finding, read directly by this audit: "transitioned from running (pve_up == 1) to a stopped state (pve_up == 0)" |
| T013 alert rule active + Alertmanager route | unchecked | not read; confirmed no rule definitions exist anywhere in this repository | **DONE** — `evidence/demo-2026-08-24/e3-01-lista-incidentes.png`: `ProxmoxGuestStopped`, `RedisExporterDown`, `InstanceDown`, `GatusEndpointHea…`, `DatabaseTcpProbe…` all CRITICAL, opened within minutes. See the honest correction below: four of these predate and superseded the coordinator's own stated precondition |
| T014 webhook refuses without credential | unchecked | not probed | **PARTIAL, not done** — the accept half is proven live (`202`, authenticated, `EVIDENCIA.md:14,29-30`); the specific refusal-without-credential probe is not recorded |
| T015 choose the already-firing alert, and why | unchecked | not written up | **NOT DONE** — the underlying action clearly happened (`RestoreDrillStale`, evidenced in `evidence/E3-...txt`/`E10-...txt`), but the required "which and why" record is absent from `EVIDENCIA.md` |
| T016 record the fitness table in `EVIDENCIA.md` §2 | unchecked | 12-row table, every cell blank | **NOT DONE** |
| T017 read-loop runbook | unchecked | `runbooks/laco-de-leitura.md` complete | **DONE** — preconditions, E1–E7, real URLs, no-write/no-window statement all present |
| T018 whole-loop runbook | unchecked | `runbooks/laco-inteiro.md` complete | **DONE** — "what it is not", the two-condition victim, initial-state check, destructive step, E1–E10 all present |
| T019 station table in both runbooks | unchecked | present in both | **DONE** — `laco-de-leitura.md` §3, `laco-inteiro.md` §4 |
| T020 outcome classification, written before execution | unchecked | present in both, with the separating rule | **DONE** — `laco-de-leitura.md` §4, `laco-inteiro.md` §5 |
| T021 manual rollback before the destructive step | unchecked | present, in the right order | **DONE** — `laco-inteiro.md` §1 precedes §6 |
| T022 human approval, via the interface | unchecked | stated explicitly, twice | **DONE** — `laco-inteiro.md` header and §6 step 10 |
| T023 confirm E4–E7 before approving | unchecked | present, with the reason | **DONE** — `laco-inteiro.md` §6 step 9 |
| T024 rejection station, different occurrence | unchecked | present | **DONE** — `laco-inteiro.md` §7 |
| T025 blank `EVIDENCIA.md` skeleton | unchecked | present, 8 sections, every field blank | **DONE** |
| T026 secret sweep of the runbooks | unchecked | no secret present, confirmed by re-reading all three runbooks | **DONE** |
| T027 `tools/demo_evidence/` package | unchecked | exists: `queries.py`, `collector.py`, `__main__.py`, `__init__.py`, `sql/` — 23 statement files across 8 stations | **DONE** |
| T028 the minimum queries, contrast baseline included | unchecked | present, verified against `queries.py` and the SQL files directly | **DONE** — including the three schema corrections and the vocabulary resolution `controle.md` documents |
| T029 one file per station, query + literal output | unchecked | `collector.py::collect`/`file_name_for`, `--- output ---` markers | **DONE** |
| T030 refuse anything that is not `SELECT` | unchecked | `collector.py::only_select`, refuses `DELETE`/`UPDATE`/`INSERT`/`DROP`/`TRUNCATE`/`WITH…DELETE…RETURNING`/two statements | **DONE** |
| T031 collector unit test, red confirmed first | unchecked | `tests/unit/tools/test_demo_evidence.py`, 31 cases | **DONE** — re-run in this audit: `31 passed` |
| T032 no credential printed or written | unchecked | forbidden-column test + connection-string-never-written test | **DONE** |
| T033 exact collector command in both runbook headers | unchecked | present in all three runbooks | **DONE** — `laco-de-leitura.md` §1, `laco-inteiro.md` §0, `navegador.md` step 15 |
| T034 dry run against staging, pre-wave params → `000-partida.txt` | unchecked | neither the file nor `evidence/consultas/` exists | **NOT DONE** — orchestrator; what exists instead is a real collection with a *new* run's parameters (T043), not a pre-wave run's |
| T035 confirm queries return the expected baseline | unchecked | not independently re-run against pre-wave data | **NOT DONE** — the "before" values on file are the fixed strings from `queries.py`, not a fresh reading |
| T036 record the red in `EVIDENCIA.md` §3 | unchecked | table present, every "measured dry" cell blank | **NOT DONE** |
| T037 run `laco-de-leitura.md` end to end | unchecked | the database chain ran for real; the browsing/screenshot half did not | **NOT DONE** — partial evidence named precisely in Evidence and corrections |
| T038 E2/E3 screenshots | unchecked | `evidence/telas/` does not exist | **NOT DONE** |
| T039 E4 screenshot | unchecked | no screenshot; DB proof exists | **NOT DONE** — the underlying claim is proven (`evidence/E4-...txt`), the screenshot this task specifically requires is not |
| T040 E5 screenshot | unchecked | no screenshot; DB proof exists | **NOT DONE** — same shape as T039 |
| T041 tool selection matches configured integrations | unchecked | no artifact | **NOT DONE** |
| T042 E7 screenshots | unchecked | no screenshot; DB proof of the (correct) zero-proposal outcome exists | **NOT DONE** |
| T043 run the collector for this run, attach per-station output | unchecked | 8 real files under `evidence/`, dated `2026-08-24T09:11:29Z` | **DONE** — with the location caveat named (written to `evidence/`, not the documented `evidence/consultas/`) |
| T044 run the read loop a second time, compare | unchecked | one collection, one instant | **NOT DONE** |
| T045 open the window, record victim confirmation | unchecked | not recorded | **DONE** — `EVIDENCIA.md:4-5` (authorization) and `marco-zero.txt` (the anchoring instants) |
| T046 the destructive step, typed once by a person | unchecked | not performed by this audit, and still not | **DONE** — `marco-zero.txt`: `pct stop 122` at 10:26:29Z, confirmed 10:26:36Z. This audit still touched nothing: the step is the operator's, evidenced after the fact |
| T047 E1 — the alert fires on its own | unchecked | `evidence/E9-...txt`/`E8-...txt`: zero rows anywhere downstream (for the *old* read-loop run) | **DONE** — `EVIDENCIA.md:12-13`: `activeAt` 10:27:34, fired 10:29:34 after `for: 2m`; "no alert was emitted by hand" |
| T048 E2 — the delivery arrives authenticated | unchecked | same zero-row evidence (old run) | **DONE, with a caveat** — `202` at 10:29:45, authenticated (`EVIDENCIA.md:14,29-30`); no dedicated E2 screenshot exists, only the timeline/text record |
| T049 E3 — the incident opens legible, subject resolved | unchecked | same zero-row evidence (old run) | **NOT DONE — the station ran, but its own claim is contradicted by two real findings** — addressable, no unrecoverable panel, correct status chip: all true (`e3-02-incidente.png`). But the title is `ProxmoxGuestStopped`, not a sentence (finding 1), and the header names `node pve02` while the alert body three lines below says `node=pve01`, the correct node (finding 2) |
| T050 E4 — the investigation records | unchecked | same zero-row evidence (old run) | **DONE, with a named gap** — `e5-01-relato.png`: 13 events, 5 turns, 44,746 tokens, 4 tool calls each with its real result. The collector never ran against this run's own id, so there is no independent SQL-literal cross-check for this specific investigation (FR-024's own bar) |
| T051 E5 — the report is legible | unchecked | same zero-row evidence (old run) | **DONE** — headline: "Proxmox LXC container redis on node pve01 stopped unexpectedly causing service and exporter outages" — a full sentence, no markdown, and it names the *correct* node (direct contrast with finding 2, same run) |
| T052 E6 — the tools match what is connected | unchecked | same zero-row evidence (old run) | **DONE, with a narrower scope than the task text** — the 4-call table (`EVIDENCIA.md:48-56`) is real and honest, including two verbatim upstream failures. No vendor tool outside what is connected was offered. The log-based exclusion half (`tool_selection`/`integrations_unresolved`) was not separately checked |
| T053 E7 — the proposal waits with a rollback plan | unchecked | `evidence/E7-...txt`: 0 rows (old run) | **NOT DONE — not exercised, and the evidence now proves the reason is the product's, not the environment's** — the entire catalogue has exactly three write capabilities, all notifications; nothing acts on infrastructure. Desk composed (20 capabilities), gate registered per run, tool ceiling (40) nowhere near hit (4 used) — nothing was cut for budget. The agent was correct to propose nothing: spec.md's own E7 edge case names this exact outcome as acceptable |
| T054 confirm E4–E7 before approving | unchecked | n/a — nothing to confirm yet | **NOT DONE** — not applicable: no proposal exists to approve, the same reason as T053 |
| T055 E8 — the operator approves, via the interface | unchecked | `evidence/E8-...txt` (old run): `nothing-executed-unattended`: 0; `decision`: `NOT COLLECTED` | **NOT DONE** — not exercised, same reason as T053: no proposal, no decision to make |
| T056 E9 — execution happens through the gate | unchecked | `evidence/E9-...txt` (old run): `outcome` `NOT COLLECTED`, `episode`: 0 rows | **NOT DONE** — not exercised, same reason as T053: no approval, no execution |
| T057 E10 — the incident reflects the outcome | unchecked | `evidence/E10-...txt` (old incident): still `investigating`, never closed | **DONE, by a path the task text did not anticipate** — not through gate execution (there was none). The incident **closed itself**: `EVIDENCIA.md:62-70` — `state: resolved`, `close_reason: "ProxmoxGuestStopped was resolved upstream"`, `self_resolved: true`. `e10-01-incidente-fechado.png` shows the chip changed from `Investigating` to `Resolved`. The product does not claim credit for what the operator did by hand |
| T058 confirm the alert resolved and closed the incident | unchecked | same as T057 (old incident) — still `investigating` | **DONE** — same text as T057: the resolution and the closure are the same event, on the same incident that opened |
| T059 reversion: confirm the guest is `running` | unchecked | not read | **DONE** — `marco-zero.txt`: restarted by hand at 10:44:47Z, because no product path would have done it |
| T060 close the window, record instant + summary | unchecked | `EVIDENCIA.md` §4 E1–E10 all blank (old gabarito) | **DONE, in substance** — `evidence/demo-2026-08-24/EVIDENCIA.md` itself is exactly this summary; no separate "window closed at HH:MM" line beyond the last event (E10, 10:50:06) |
| T061 reject without a reason | unchecked | `evidence/R-...txt`: 0 rows | **NOT DONE** — no proposal of any kind appeared in the 2026-08-24 run to reject. Structural note: since only the three notification capabilities can ever propose anything, a "different occurrence" for rejection needs one of those three, not a second CT122-shaped incident |
| T062 reject with a reason | unchecked | same file: 0 rows | **NOT DONE** — same reason as T061 |
| T063 confirm both decisions in the audit trail | unchecked | same file, second query: 0 rows | **NOT DONE** — no decisions exist yet to appear in the trail |
| T064 name resolution inside each monitoring container | unchecked | not read | **NOT DONE** — not addressed by the coordinator's message; `backlog.md`'s own current entry carries the last known state (still broken) |
| T065 managed-secret sync | unchecked | not read | **NOT DONE** — not addressed by the coordinator's message; `backlog.md` entry still present |
| T066 model-gateway key, Verified | unchecked | not read | **NOT DONE** — the self-hosted gateway is a *different* provider from the already-Verified Google Gemini `antes-01-modelos.png` shows (T008); no fresh evidence about the self-hosted gateway's key exists |
| T067 write the backlog entry for each unfinished operational task | unchecked | all three present in the rewritten `backlog.md` | **DONE** |
| T068 mark stations not exercised by a pending operational task | unchecked | `EVIDENCIA.md` §5 field blank | **NOT DONE — and the task's own premise did not hold** — E7/E8/E9 genuinely were not exercised, but for none of the three operational reasons this task anticipates: the real reason is that the catalogue has no infrastructure-write capability, a product fact, not a pending DNS/secret/key task |
| T069 fill `EVIDENCIA.md` station by station | unchecked | still the blank skeleton (original gabarito) | **DONE, in a document of its own** — `evidence/demo-2026-08-24/EVIDENCIA.md` ties expectation/evidence/verdict together per station in prose, not the original gabarito's literal fields (that file, `evidence/EVIDENCIA.md`, is untouched and still blank) |
| T070 confirm full-page 1920×1080 screenshot per screen-station | unchecked | `evidence/telas/` does not exist | **NOT DONE — real screenshots exist, at the wrong width** — eleven real, genuinely full-page captures (heights up to 2370px) confirmed via `file`: all **1280px wide**, not 1920px. E2 has no dedicated screenshot |
| T071 confirm query + literal output per recording-station | unchecked | true for 4 of 8 stations (old run only) | **NOT DONE — the whole loop ran, and the SQL-literal artifact still does not exist for it** — the collector never ran against `run=d393d5d0…`/`incident=inc_05328c58ca88676b`. Real, verified screenshot-and-prose evidence exists instead, which is not what FR-024 asks for |
| T072 secret sweep, text and screenshots | unchecked | not run | **DONE** — text: all eight old evidence files plus the three new ones (`EVIDENCIA.md`, `achados.md`, `marco-zero.txt`) swept against a structural pattern file and the two real `.env` staging values (boolean check, value never printed) — clean both times. Screenshots: all eleven opened and read directly in this audit — none shows a token, password, or credential |
| T073 run owning features' acceptance + transversal against staging | unchecked | the 2026-08-23 deterministic run is on file, not this final one | **NOT DONE** |
| T074 one-sentence verdict + per-station verdicts | unchecked | `EVIDENCIA.md` top line and §7 blank (old gabarito) | **NOT DONE — two of three parts present** — "Estações cumpridas" and "Estações NÃO exercidas, e por quê" cover the per-station verdict in prose; no single top-line verdict sentence exists |
| T075 list every finding in `EVIDENCIA.md` §6 | unchecked | header row only (old gabarito) | **DONE, in a document of its own** — `evidence/demo-2026-08-24/EVIDENCIA.md`, "Achados de produto": four numbered findings, each with description and evidence. None has an owning feature assigned yet — that is T077's open work, not this task's |
| T076 hand product-owned findings to the orchestrator, do not fix | unchecked | n/a | **DONE** — the four findings reached this audit by the coordinator's own message with an explicit no-fix instruction; zero product files were touched (reconfirmed after this pass too) |
| T077 write backlog entries for ownerless findings | unchecked | n/a | **NOT DONE** — naming an owning feature (or declaring genuine ownerlessness) for each of the four is the orchestrator's call with full wave context; this audit traced only a first lead for findings 1/2 (`platform/persistence/ports/incident_store.py:148,188` — `title` is a field distinct from any investigation headline) and went no further |
| T078 re-run and replace evidence after an accepted repair | unchecked | n/a | **NOT DONE** — no repair happened inside this feature |
| T079 per-feature section with verifier verdict in `CONFRONTO.md` | unchecked | absent, deliberately | **NOT DONE, and here is why** — `CONFRONTO.md`'s own header states it is measured by the orchestrator and never copied from an implementer's report; writing verifier verdicts here would violate exactly that |
| T080 fixed "who builds this in production?" column | unchecked | present | **DONE** — `specs_v7/CONFRONTO.md`, "Quem constrói isso em produção? — a coluna da onda" |
| T081 column filled for the required minimum mechanisms | unchecked | all five present with `file:line` | **DONE** — 2 of the 17 rows spot-checked directly against source in this audit and found byte-accurate (see Evidence) |
| T082 dormant mechanisms declared | unchecked | 3 entries, none pointing at a test | **DONE** |
| T083 confronto closes citing the demo as evidence | unchecked | present, with an honest verdict | **DONE** — the verdict text itself ("não executado") is now one step behind the tree; named as a staleness note, not silently fixed, since that file is the orchestrator's to maintain |
| T084 backlog-destination table in the confronto | unchecked | 11 of 11 rows, zero without a destination | **DONE** |
| T085 rewritten `backlog.md` | unchecked | 14 items | **DONE** |
| T086 wording checked against committed-file rules | unchecked | re-swept in this audit: zero `FR-`/`SC-`/`specs_v*`/`Article`/feature-number references | **DONE** |
| T087 the file's existing shape preserved | unchecked | every item has "what happens today" / "why it is not trivial" / "how it should be judged" | **DONE** |
| T088 no removed item without named evidence | unchecked | checked row by row against the destination table | **DONE** |
| T089 full `make verify` | unchecked | not run | **NOT DONE, and here is why** — the coordinator's own words: "four separate reds are being worked right now"; reserved for the orchestrator on the final tree. This audit ran the equivalent tier gates for the surface it touched instead (see Verification) |
| T090 no product file touched | unchecked | true, not yet reconfirmed | **DONE** — reconfirmed in this audit: `git diff --stat a0bfa74~1 aeb0dd6` outside the declared paths returns zero files |
| T091 write this feature's `controle.md` | unchecked | existed, accurate but ungranular | **DONE** — rewritten in this audit with a per-task ledger |
| T092 report to the orchestrator | unchecked | n/a | **DONE** — this report, and the summary delivered alongside it |

## Evidence and corrections

### Fase 1–2 — pre-flight and environment fitness (T001–T016)

Nothing here is code. `evidence/EVIDENCIA.md` §1 and §2
(`/srv/workspaces/NinjaSRE/.claude/worktrees/agent-a93e02cefd3bb41b0/specs_v7/080-incidente-fecha-o-laco/evidence/EVIDENCIA.md:17-54`)
are, respectively, an 8-row and a 12-row table with every value cell blank —
read directly, not inferred. This audit did not open a session to
`192.168.68.159`, did not query the staging Postgres directly, and did not
send a request to `https://stg-ninjasre.lan.kyo.ninja`, by instruction and to
avoid contending with the operator's own concurrent session on the same
target.

**T007 is the one exception**, and it is DONE by a different route than
"discovered by this audit": `tools/demo_evidence/collector.py:106-122`
(`Parameters.get`) resolves `:org` from the `--org` flag a caller supplies,
and every one of the eight files the operator's collector run produced today
— `evidence/E4-the-investigation-records-its-turns-its-calls-it.txt:3` reads
`parameters: org=default run=0c9c0d5ce453458d9e115af98763ade4
incident=inc_d4b0bf515a6a7e1e` — carries `org=default` and returns real,
non-empty, org-scoped rows: `run_turns=5`, `tool_calls=4`, `evidence_rows=1`,
`trace_events=12` (`evidence/E4-...txt:14-71`). A wrong organisation
identifier would read zero on every one of those counts; it reads real
numbers, which is proof the value is correct, independent of who ran the
discovery query in the first place.

**T009 is worth naming precisely because it looks like it contradicts the
dispatching brief.** `evidence/E3-the-incident-opens-legible-over-a-subject-the-es.txt:33-46`
carries the *only* real reading of `estate_resources` on file:

```
SELECT count(*) AS present_resources
FROM estate_resources
WHERE org_id = 'default'
  AND absent_since IS NULL;

--- output ---
 present_resources
-------------------
                 0
(1 row)
```

collected `2026-08-24T09:11:29Z`. The dispatching brief states the estate now
holds 100 real resources including a healthy CT122. Both can be true: the
estate sync most likely happened *after* 09:11 UTC today, and at the time
this was written, this audit had no later reading because it did not touch
staging.

**Update, same pass, after the destructive loop ran.** The timing gap is
resolved: `evidence/demo-2026-08-24/antes-03-recursos.png`, opened and read
directly, shows "100 watched · 71 healthy · 0 degraded · 14 unhealthy" —
taken before the destructive step, after the estate sync this audit's first
reading had missed. T009 is now DONE. `antes-01-modelos.png` similarly
settles T008 ("Google Gemini · Verified"), and `e5-01-relato.png` — the
investigation's own finding, not a manual check — settles T012 ("transitioned
from running... to a stopped state"). All three screenshots were opened and
read pixel-by-pixel by this audit, not summarised from the coordinator's
message; see the Table for the full set of fifteen rows this changed.

**T010 is the one claim this audit declines to credit, on the coordinator's
own stated standard.** The coordinator reported in chat that the stored
Proxmox token is `root@pam!infra` holding `Administrator`. A sweep of both
new text files —

```
$ grep -n "root@pam\|Administrator\|VM.PowerMgmt\|token" \
    evidence/demo-2026-08-24/EVIDENCIA.md evidence/demo-2026-08-24/achados.md
evidence/demo-2026-08-24/EVIDENCIA.md:38:**E4 — a investigação gravou.** 13 eventos, 5 turnos, 44.746 tokens, com o
```

— finds only the unrelated word "tokens" (LLM tokens, in a different
sentence). The privilege claim is not in the written record. The coordinator
opened this exact message by writing "do not take this message as the
source, take the file"; applied symmetrically, T010's box stays unchecked.

### Fase 3 — the runbooks (T017–T026, T033)

Read in full and independently, not sampled:
`runbooks/laco-de-leitura.md` (279 lines) and `runbooks/laco-inteiro.md` (337
lines). Both carry every element `tasks.md` asks for, cross-checked line by
line:

- `laco-inteiro.md:50-68` (§1, the manual rollback) precedes `laco-inteiro.md:190-301`
  (§6, the window and its destructive step) — T021's ordering requirement
  confirmed by reading, not by the section numbers alone.
- `laco-inteiro.md:20-23` ("Não aprova por API… a frase 'aprovação humana'
  perde o sentido no exato instante em que ela passa a importar") and
  `laco-inteiro.md:264-271` (step 10) both state the approval is human, via
  the interface — T022.
- `laco-inteiro.md:252-262` (step 9, "CONFERIR E4 A E7 ANTES DE APROVAR")
  states the reason, not just the instruction — T023.
- `laco-inteiro.md:304-319` (§7) separates the two rejection sub-steps and
  requires a different occurrence from the approved one — T024.
- The collector's exact invocation appears in `laco-de-leitura.md:56-68`
  (§1), `laco-inteiro.md:35-41` (§0), and `runbooks/navegador.md:357-376`
  (step 15, confirmed by `grep -n "^## Passo\|tools.demo_evidence
  collect" runbooks/navegador.md`) — T033, across all three files.
- `runbooks/laco-de-leitura.md`, `runbooks/laco-inteiro.md`, and
  `runbooks/navegador.md` were each re-read for a transcribed secret;
  none is present, and where a credential is needed, the file names *where
  to get it* (e.g. `laco-de-leitura.md:31-39`) rather than the value — T026.

### Fase 4 — the collector (T027–T033)

`tools/demo_evidence/collector.py` (336 lines) and
`tools/demo_evidence/queries.py` (381 lines) read in full via
`codegraph_explore`, cross-checked against the 23 files in
`tools/demo_evidence/sql/` (`E3`×3, `E4`×6, `E5`×2, `E7`×3, `E8`×3, `E9`×2,
`E10`×2, `R`×2 = 23 statements across 8 stations — `STATIONS` at
`queries.py:363` is exactly `(E3, E4, E5, E7, E8, E9, E10, R)`). Verified
directly, not assumed from `controle.md`:

- `only_select` (`collector.py:136-155`) refuses anything whose body is not a
  bare `SELECT` after stripping comments, refuses a second statement after a
  semicolon, and refuses `WITH … DELETE … RETURNING` specifically because a
  CTE can smuggle a write behind something that reads like a query — T030.
- `Parameters.get` (`collector.py:106-122`) resolves a name against
  `VOCABULARY` before falling back to a field on `Parameters`, and
  `queries.py:57-62` builds that `VOCABULARY` dict from
  `APPROVAL_AUDIT_RESOURCE_KIND_REQUEST`, `REMEDIATION_AUDIT_RESOURCE_KIND`,
  and `ApprovalState.REJECTED.value` imported from the modules that declare
  them (`queries.py:41-45`) — exactly as `controle.md`'s "Correções à
  `tasks.md`" section claims, confirmed by reading the current file directly
  rather than trusting the claim.
- `test_no_query_reads_a_column_that_could_hold_a_secret` and
  `test_the_command_that_reached_the_database_is_not_written_into_the_evidence`
  (`tests/unit/tools/test_demo_evidence.py:195-226`) are real, executed tests,
  not descriptions of intended behaviour — T032.

Ran, not inferred: `uv run pytest tests/unit/tools/test_demo_evidence.py -q`
→ **31 passed in 0.15s**, matching `controle.md`'s 2026-08-23 figure exactly
on a tree that has since absorbed the wave's other seven feature slots.

### Fase 6 — the read loop, partially exercised (T037–T044)

The database half of the read loop ran for real, evidenced by
`evidence/E10-the-incident-reflects-the-outcome-instead-of-sto.txt:10-46`
(the `timeline` query and its 18-row output):
the same alert (`RestoreDrillStale`, subject `192.168.68.159`) correlated
into incident `inc_d4b0bf515a6a7e1e` six times between `03:38:53Z` and
`09:03:53Z` on 2026-08-24, each producing a fresh investigation run —
`0c9c0d5ce453458d9e115af98763ade4` is the newest of the six run ids on that
timeline. `evidence/E4-...txt:14-71` shows this run recorded 5 turns, 4 tool
calls, 1 evidence row, 12 trace events — all greater than zero against the
wave's own zero baseline, satisfying the substance of what E4 exists to
prove. `evidence/E5-...txt:18-26` shows the run's `headline` reads as a
sentence ("Weekly restore drill jobs on pve02 exceeded their maximum
allowable execution window without a successful run") while `summary` still
opens with `### Investigation Report` — the split T033/E5 exists to prove.
`evidence/E7-...txt:20-23` shows zero proposals for this run, which
`laco-de-leitura.md:132` (§4, the E7 row) names explicitly as an acceptable,
declared outcome: "a investigação concluiu sem evidência suficiente para
propor... e isso é correto."

None of that is a screenshot, and `EVIDENCIA.md` was not written from it.
T043 is marked done because its own text — "rodar o coletor para o run deste
laço e anexar as saídas por estação" — asks for exactly what exists: the
collector ran, and eight per-station files are attached, with real, literal
query output. T037–T042 and T044 stay unchecked because each names something
beyond that (a screenshot, a second run for repeatability, a written record
in `EVIDENCIA.md`) that is not yet on file.

**The candidate finding**, named but not classified by this audit:
`evidence/E4-...txt:105-128` records four tool calls for this run, in
sequence:

```
0 | prometheus_active_alerts     | succeeded
1 | search_knowledge_base        | failed | The knowledge base is not configured for this deployment...
2 | logs_for_resource            | failed | this deployment has no log source configured...
3 | prometheus_metric_statistics | failed | prometheus answered 400 to GET /api/v1/query_range: {"status":"error","errorType":"bad_data","error":"invalid parameter \"start\": cannot parse \"\" to a valid timestamp"}
```

Calls 1 and 2 fail because nothing is configured — consistent with the
already-open backlog items for this deployment, environment rather than
product. Call 3 is different in shape: an empty `start` parameter reaching a
Prometheus range query reads like a construction bug in the caller, not an
absent configuration. This audit did not trace which capability builds that
call, because classifying it and naming its owning feature is T075's job,
done with the full demonstration's evidence in view — precisely the judgment
this feature's own plan (`plan.md`: "esta feature encontra defeitos e não os
conserta") reserves for the orchestrator.

### Fase 7 — the window, run for real (T045–T060)

At the time this section was first written, `evidence/E8-...txt`,
`evidence/E9-...txt`, and `evidence/R-...txt` (all timestamped
`2026-08-24T09:11:29Z`, for the *earlier* read-loop investigation) showed
zero rows throughout, and this audit correctly read that as "not yet
exercised." **The window then actually happened**, and the destination
directory is `evidence/demo-2026-08-24/`, not the old `evidence/*.txt`
files (which were never re-run against the new investigation — see the
FR-024 gap named in the Conclusion and in T071's row).

`evidence/demo-2026-08-24/marco-zero.txt` anchors three real instants:
`pct stop 122` at `2026-08-24T10:26:29Z`, confirmed six seconds later, and
`pct start 122` at `10:44:47Z`. `EVIDENCIA.md`'s own timeline
(`evidence/demo-2026-08-24/EVIDENCIA.md:7-19`) chains every station between
those two instants to the one before it: the alert activated at 10:27:34,
fired at 10:29:34 (`for: 2m` elapsed), the webhook returned `202` at
10:29:45, the incident and investigation opened the same second, the
investigation concluded at 10:30:08 after 23 seconds, and the incident closed
itself at 10:50:06.

Two of the five screenshots checked in this second pass matter most:
`e5-01-relato.png` (opened directly, described in full above and in
`controle.md`) shows a 13-event, 5-turn, 44,746-token transcript with two
verbatim upstream failures (`proxmox_guest_tasks` → Proxmox `501`;
`changes_in_window` → "no change source is configured") and a headline that
both reads as a sentence and names the correct node. `e10-01-incidente-fechado.png`
shows the incident's status chip changed from `Investigating` to `Resolved`,
matching the `state: resolved`, `self_resolved: true`, and named
`close_reason` `EVIDENCIA.md:62-70` quotes.

**E7, E8, E9 did not happen, and this pass traced why rather than accepting
the report's own framing at face value.** `EVIDENCIA.md:77-96` states the
catalogue's entire write surface is three notification capabilities
(`alertmanager_acknowledge_incident`, `pushover_post_message`,
`telegram_post_message`), none of which acts on infrastructure, and that the
desk composed 20 capabilities with a tool ceiling of 40 against 4 actually
used — nothing was cut for budget. This matches this audit's own earlier,
independent finding (Fase 12 section, `gateway/http/remediation.py:172`
`compose_remediation`) that the desk composition is real and working; the
absence of a proposal is therefore a fact about the declared capability
surface, not about whether the mechanism runs. spec.md's own E7 edge case —
"a investigação conclui sem evidência suficiente para propor... e isso é
correto" — already names this shape of outcome as acceptable, and this
report now marks T053 that way rather than leaving it indistinguishable from
an environment gap.

### Fase 8 — the rejection, not reachable in this run (T061–T063)

Unaffected by the window's own success: no proposal of any kind existed to
reject. Worth naming precisely because of what Fase 7 established — if the
catalogue's only write capabilities are the three notification tools, the
"different occurrence" FR-019 asks for the rejection path cannot be a second
disposable-and-observed host; it has to be an occurrence where one of those
three notification capabilities gets proposed instead.

### Fase 12 — the confronto's new column (T080–T083)

Verified by reading the merged tree directly, not by trusting either
`controle.md` or `specs_v7/CONFRONTO.md`'s own claim to have been
code-read:

```
$ grep -n "compose_control_plane\|compose_remediation(" gateway/http/lifespan.py
26:from gateway.http.control_plane import compose_control_plane
100:        await compose_control_plane(
105:        await compose_remediation(
```

matches `specs_v7/CONFRONTO.md`'s table rows for "Balcão de remediação" and
"Vínculo do plano de controle" exactly (`:105` and `:100`), and
`codegraph_explore` on `compose_control_plane`/`compose_remediation`
confirmed the function definitions themselves sit at
`gateway/http/control_plane.py:64` and `gateway/http/remediation.py:172` —
again matching the confronto table's cited lines precisely. `specs_v7/CONFRONTO.md:289-322`
("Quem constrói isso em produção? — a coluna da onda") has 17 rows, none
pointing at a test; `specs_v7/CONFRONTO.md:324-330` ("Declarados dormentes")
has exactly 3, each naming what would wire it. T081's five required minimums
(recorder, both gates, the team resolver, certificate trust to egress) are
all present by name.

**Staleness named, not fixed**: `specs_v7/CONFRONTO.md:353-362` ("A demo, e
o que ela ainda deve") still reads "Veredito da demo: não executado... quem
escreveu os roteiros roda em worktree isolada e não alcança cluster, banco
nem Alertmanager" — true when written, one step behind the tree now that
`evidence/E4-...txt` and its siblings exist. Not corrected here: that file's
own opening lines state it is measured by the orchestrator and never copied
from an implementer's report, the same rule that already reserves T079 to
the orchestrator.

### Fase 13 — the backlog (T084–T088)

`backlog.md` (311 lines) read in full: 14 items, each in the shape the file
already used — what happens today, why it is not trivial, how it would be
judged. Swept directly in this audit:

```
$ grep -nE "FR-[0-9]|SC-[0-9]|specs_v[0-9]|Article [IVXLC]|constitution|feature [0-9]{3}|\b0[0-9]{2}-[a-z]" backlog.md
(no output — exit 1)
```

`specs_v7/CONFRONTO.md:332-352` ("Backlog anterior → destino, item por item")
has 11 rows against the 11 items the prior backlog carried, none without a
named destination — checked row by row against `backlog.md`'s current
contents, not merely counted.

### T090 — reconfirmed, not merely repeated

```
$ git diff --stat a0bfa74~1 aeb0dd6 -- . ':!specs_v7/080-incidente-fecha-o-laco' \
    ':!tools/demo_evidence' ':!tests/unit/tools/test_demo_evidence.py' \
    ':!backlog.md' ':!specs_v7/CONFRONTO.md'
(no output)
```

Zero files outside the declared lane across the feature's own commit range.
This audit's own changes are `tasks.md`, `controle.md`, and this report — all
inside the feature's own directory, so the boundary holds after this audit
too.

## Verification

Gates actually run in this audit, on the current merged tree
(`10a329c`, which already includes the wave's other seven feature slots —
not the `4f438f7` tree `controle.md`'s 2026-08-23 pass measured against):

| Gate | Command | Result |
|---|---|---|
| Collector unit tests | `uv run pytest tests/unit/tools/test_demo_evidence.py -q` | **31 passed in 0.15s** |
| Tools + architecture suite | `uv run pytest tests/unit/tools tests/architecture -q` | **734 passed, 3 warnings in 56.01s** |
| Raw-SQL guard, CLI | `uv run python tools/check_raw_sql.py` | exit 0 |
| Raw-SQL guard, strict test | `uv run pytest tests/unit/tools/test_check_raw_sql.py -q` | **53 passed in 4.41s** |
| Lint | `uv run ruff check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | All checks passed! |
| Format | `uv run ruff format --check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | 5 files already formatted |
| Types | `uv run mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | Success: no issues found in 5 source files |
| Constants guard | `uv run python tools/check_constants.py` | exit 0 |
| Direct-credential guard | `uv run python tools/check_direct_credentials.py` | exit 0 |
| Docs-drift guard | `uv run python -m tools.check_docs_drift` | exit 0 |
| Documented examples | `uv run python -m tools.test_doc_examples` | 29 documented example(s) check out |
| Integration-catalogue parity | `uv run python -m tools.verify_integrations` | 15 integration(s) at full parity, every permission probed |
| Backlog wording sweep | `grep -nE "FR-[0-9]\|SC-[0-9]\|specs_v[0-9]\|Article [IVXLC]\|constitution\|feature [0-9]{3}\|\b0[0-9]{2}-[a-z]" backlog.md` | no matches |
| Backlog upstream-name sweep | `grep -niE` against a short list of prior-art product names | no matches |
| Evidence secret sweep (text, pass one) | pattern-file `grep` across the eight old `evidence/*.txt` + `EVIDENCIA.md`, plus a boolean `grep -qF` of the two real `.env` staging values against the same files (value never printed) | clean on both |
| Evidence secret sweep (text, pass two) | same two sweeps, against the three new files in `evidence/demo-2026-08-24/` (`EVIDENCIA.md`, `achados.md`, `marco-zero.txt`) | clean on both |
| Evidence secret sweep (screenshots) | all eleven PNGs in `evidence/demo-2026-08-24/` opened and read directly (not listed, not thumbnailed) | none shows a token, password, or credential |
| Screenshot dimensions | `file` on all eleven PNGs | all `1280 × N` (N from 773 to 2370) — full-page, but not the specified 1920px width |
| Product-boundary diff | `git diff --stat a0bfa74~1 aeb0dd6` outside the declared lane | zero files |

**Not run, and why:**

- `make verify` (full) — repository-wide, reserved for the orchestrator on
  the final tree; the orchestrator's own pass-two report says it is not
  green yet ("four separate reds are being worked right now"), so this
  audit's earlier decision not to attempt it is now independently confirmed
  rather than merely unrevisited. This audit ran the equivalent tier gates
  above instead.
- The deterministic transversal Playwright suite against staging
  (`spec_validation browser … transversal-rules.spec.ts`) — not re-run in
  either pass. The 2026-08-23 result (45 passed, 7 skipped, `EXCEPTIONS`
  empty) is on file in `controle.md`; this audit changed nothing under
  `console/`, so there is no reason to expect drift.
- Any live read against staging, the cluster, or the Alertmanager — not
  run in either pass, by instruction. Pass two's evidence came entirely from
  files the coordinator had already placed in the shared checkout
  (`/srv/workspaces/NinjaSRE/specs_v7/080-incidente-fecha-o-laco/evidence/demo-2026-08-24/`,
  read via absolute path because a worktree-isolated agent's git operations
  cannot reach a different checkout's branch state) and from `.env`'s two
  staging values, read only to prove their absence and never printed.
- No test was written test-first in either pass, because nothing was found
  both (a) missing and (b) inside this feature's own implementable surface
  (`tools/demo_evidence/`, its test, the docs). Everything checked off was
  already built and already passing, or already captured as real evidence by
  the operator; everything left unchecked needs a live environment or an
  orchestrator-level judgment this audit does not make on its own. There was
  accordingly no red to confirm and no implementation phase, in either pass —
  stated plainly rather than implied.

## Control reconciliation

**`specs_v7/080-incidente-fecha-o-laco/tasks.md`**: 52 of 92 boxes checked —
32 from pass one (`T007`, `T017`–`T033`, `T043`, `T067`, `T080`–`T088`,
`T090`–`T092`) plus 20 from pass two (`T008`, `T009`, `T011`, `T012`, `T013`,
`T045`–`T048`, `T050`–`T052`, `T057`–`T060`, `T069`, `T072`, `T075`, `T076`),
each independently verified against source, a passing test, or
already-committed evidence — including, for pass two, opening and reading
all eleven screenshots directly rather than trusting the coordinator's
description of them. The other 40 stay unchecked; a cross-check confirms
every row in the Table above agrees exactly with `tasks.md`'s checkbox state
and with `controle.md`'s per-task `FEITO`/`NÃO FEITO` label — zero
mismatches across all 92 tasks, checked programmatically, not by eye.

**`specs_v7/080-incidente-fecha-o-laco/controle.md`**: pass one rewrote it
from a range-grouped ledger to one row per task. Pass two added a dated
"Atualização, mesmo dia" section under the existing "Segunda auditoria"
heading (not a new dated section — this is the same audit, continued after
the coordinator's message arrived mid-session) covering: the real timeline
from `marco-zero.txt`, the four product findings with a first ownership
lead for two of them, the coordinator's own correction about which alert
rule was the real precondition, the 1280px-not-1920px screenshot finding,
the missing SQL-literal evidence for the new investigation, and the
`prometheus_metric_statistics` finding's non-recurrence. Every Fase table
from Fase 1 through Fase 11 was then individually revised to match — not
appended to, replaced, so the ledger never shows two contradictory claims
about the same task. A closing section answers the spec's own "did the loop
close" question directly, naming the specific, qualified shape of the
answer rather than a bare yes or no.

**`specs_v7/CONFRONTO.md`**, **`evidence/EVIDENCIA.md`** (the original
gabarito), and **`evidence/demo-2026-08-24/`**: all read, none written.
`evidence/demo-2026-08-24/` was read from the shared checkout at
`/srv/workspaces/NinjaSRE/specs_v7/...` rather than this worktree's own
tree, because it was never merged onto `master` by the time this audit
inspected it, and a worktree-isolated agent cannot run git operations
against a different checkout to pull it in — reading the files directly by
absolute path was the available, sufficient path. `CONFRONTO.md`'s stale
verdict paragraph is now more out of date than pass one found it, and is
still not corrected here, for the same reason: it is the orchestrator's own
measured document, not this feature's.
