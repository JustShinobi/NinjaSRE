# Confrontation report — 080 O incidente fecha o laço

## Conclusion

This is the third pass over the same feature, and it is layered on top of
two trustworthy prior passes rather than redoing them. **Pass one** found
`tasks.md` drifted in exactly the direction its own dispatching brief named
— all 92 boxes unchecked, wrong for 32 of them, where the runbooks, the
evidence collector and its test suite, the confronto column, and the
rewritten backlog already existed and already passed their gates. **Pass
two** confirmed the destructive loop had run for real against staging and
the real hypervisor: CT122 stopped at 10:26:29Z, the alert fired on its own
at 10:29:34, the webhook accepted an authenticated `202`, the incident
opened, the investigation recorded 13 events with two verbatim upstream
failures, the report's headline named the correct node, and the incident
**closed itself** at 10:50:06. Pass two also refused one specific claim — a
Proxmox token holding `Administrator` — because it existed only in a chat
message, not in the written record, and correctly said so.

**This pass exists because two things changed in the record between pass
two and now, and both are read directly rather than taken on anyone's
word.** `evidence/demo-2026-08-24/EVIDENCIA.md` gained two new sections: "O
ciclo de publicação, executado depois da demo" (T001–T006, the wave merge,
the gate, the publish without `COMPONENTS=`, the Argo reconciliation, the
service confirmed separately) and "O privilégio do token, que faltava aqui"
(T010, exactly the fact pass two refused to credit, now written down with
its own reasoning — a `pveproxy` access-log correlation plus the datacenter
ACLs). Both are read in full below, cross-checked against source where a
cross-check is possible without touching staging, `pve01`, `pve02`, or
CT122 — none of which this pass touched either.

**Six boxes move from open to done on that evidence: T001, T003, T004,
T005, T006, T010.** One does not, on a finding this pass made rather than
inherited: **T002's own recorded table names a real failure**
(`tests/contract/console::test_the_untouched_baselines_still_match`, tied to
14 visual baselines that diverge from their committed images and were not
re-accepted) inside what its summary line calls "Verde." Reading the test's
own source (`tests/contract/console/test_console_visual_regression.py:156-167`)
confirms it exists specifically to prove the comparison "is not simply
always red," and it failed — which only happens on a genuine divergence.
`console-visual` is not part of the `verify:` Make target
(`Makefile:516-521`), so this red lives inside the general `test` suite, not
a side channel; and `specs_v7/CONFRONTO.md:433-434` — written before this
session — already carries this exact debt as a known, open item requiring
human curation, so it is not a new regression the wave introduced. Neither
fact makes it not-red. T002's own text calls any red here a blocker
("Um vermelho aqui é bloqueio"), and this pass declines to round the
table's own honestly-reported failure up to a clean pass — it leaves the
box open, names precisely why, and lets the orchestrator weigh the debt
against the rule.

**Three items were checked again by direct instruction, and each is
reported exactly as instructed, confirmed by this pass's own reading rather
than assumed.** T014 stays open: the demo shows an accepted, authenticated
delivery, never a refused, unauthenticated one — half a claim is not the
claim, and a fresh sweep of every evidence file found no refusal probe
anywhere. T049 stays open: `e3-02-incidente.png`, opened directly by this
pass, shows `ProxmoxGuestStopped` as the title (not a sentence) and
`node pve02` in the header three lines above `node=pve01` in the alert body
— both visible in the same screenshot, without scrolling. T053–T056 and
T061–T063 stay not-exercised, and this pass adds real evidentiary weight to
the *reason* rather than changing the verdict: `e7-01-incidente-apos.png`
and `e10-02-decisoes.png`, opened directly, show the product correctly
reporting "Nothing proposed yet" and "Nothing is waiting on a decision" —
the observable shape of a catalogue whose entire write surface is three
notification capabilities, none of which acts on infrastructure. This is
recorded as a product-scope statement, not a demo shortfall, exactly as
instructed.

**T015 and T038–T042 were re-opened and each screenshot was opened
individually, not assumed from a filename.** The read loop (Fase 6, against
`RestoreDrillStale`) and the whole loop (Fase 7, against CT122 /
`ProxmoxGuestStopped`) are two different executions. Every one of the eleven
screenshots this pass opened — including `e3-01-lista-incidentes.png`,
`e3-02-incidente.png`, and `e5-01-relato.png` — turns out to belong to the
whole loop. `e3-01-lista-incidentes.png` does show `RestoreDrillStale`
genuinely firing in a live incident list (real, new value for T015's
"listar" half), but no screenshot of `RestoreDrillStale`'s own detail, run,
or report exists anywhere, and no file states *why* it was chosen as the
read loop's raw material. T038–T042 (which explicitly ask for the read
loop's own captures) therefore stay open — crediting them with the whole
loop's screenshots would launder one execution's evidence into a different
task's requirement, which this pass declines to do even though the
temptation, given how good those screenshots are, is real.

**T089 stays open, and this pass adds genuine, freshly-run evidence rather
than repeating "not run."** `make verify` was never executed as one command,
neither before publish (T002 was measured piece by piece, for a stated
environment reason) nor on the Fase-14 final tree. This pass ran the static
and architecture slice itself, directly, on the current tree: the
collector's own 31 tests, 752 tests across `tests/unit/tools` and
`tests/architecture` (734 at the last audit — growth from other merges, zero
failures), the raw-SQL guard's 53-case strict test, lint, format, mypy, five
guard scripts, and all 7 import contracts — all clean, zero regressions.
The general pytest suite (12,000+ cases at the scale pass two measured),
`console-check`, and `console-visual` were not attempted, deliberately: this
feature touches no product code, roughly twenty other agent worktrees are
active on the same host at once, and repeating a multi-thousand-test run
that pass two's own account says "always died at the same point" risks
resource contention against concurrent work for a gate whose true state
(one named, pre-existing red) is already known and disclosed.

**One more thing surfaced by opening every screenshot rather than sampling
two of them, named because a rigor sweep should catch it rather than pass
over it**: `e10-02-decisoes.png` and `antes-04-decisoes.png` are
byte-identical (`md5sum` matches). Both landed in the same commit with the
same checkout timestamp, so git history cannot settle whether the
`/decisions` screen was captured twice and genuinely produced the same
pixels (plausible — it is a static screen with no relative timestamp, and
nothing was ever proposed for it to differ over) or whether one file was
copied under two names. This changes no verdict — the claim both captures
support (nothing waiting on a decision, before and after) is consistent with
the rest of the record — but it is named rather than quietly noticed and
dropped. Also confirmed directly in this pass, not re-stated from the prior
report: `specs_v7/CONFRONTO.md` now contradicts itself internally — lines
353–363 ("A demo, e o que ela ainda deve") still say "Veredito da demo: não
executado," while lines 451 onward ("A demo, executada · 2026-08-24") narrate
the whole thing having run. Not corrected here, for the same reason the
prior pass gave for not touching that file: its own header states it is
measured by the orchestrator, not edited by a feature confrontation — but
the contradiction is real, newly visible now that both sections coexist, and
is named for whoever closes that file next.

## Table

Convention for "Final status," unchanged from the prior pass: **DONE** — the
code, a test, or already-committed evidence proves it; box checked.
**PARTIAL** — real, substantial work is on file, but the task's own bar is
not fully met; box left unchecked. **NOT DONE** — box left unchecked, with
the reason stated; none are silent. No item in this feature has
**REGRESSED** — everything previously done was reconfirmed done. Rows marked
"(unchanged)" were re-spot-checked in this pass against the current tree and
found to still hold exactly as the second pass reported; they are not
reproduced from memory.

| Item | What the control claimed (before this pass) | What this pass proved | Final status |
|---|---|---|---|
| T001 confirm wave merges + PASS, record tree commit | Open — orchestrator's own words: not fully merged | `EVIDENCIA.md` "O ciclo de publicação": 233 commits since `abbc418`, clean tree, no worktree pending. Reconfirmed independently: `git log --oneline abbc418..HEAD` on this tree = **235** (2 more `docs(wave)` commits landed after that count was written — consistent, not contradictory). PASS-per-feature corroborated against `specs_v7/CONFRONTO.md`: explicit `S0 · PASS`, `S1` gate table all-green (`12278 passed / 27 skipped`, exit 0), `S2–S5` narrates every remaining feature closing something, and `grep -niE "REPROVOU\|FAIL...\|reprovad"` across the whole file returns **zero matches** | **DONE** |
| T002 `make verify` before publish | Open — orchestrator's own words: four reds being worked | `EVIDENCIA.md` records the gate piece by piece with real counts — **and one piece is a real, named failure**: `tests/contract/console` "483 passed; única falha é `test_the_untouched_baselines_still_match`", and `console visual` "14 baselines divergentes, nenhuma aceita." Read directly: the failing test (`tests/contract/console/test_console_visual_regression.py:156-167`) exists specifically to prove the comparison is not always green, and only fails on genuine divergence. `console-visual` sits outside the `verify:` target (`Makefile:516-521`) but the failing *test* lives inside `test`, which is in `verify:`. `CONFRONTO.md:433-434` (written before this session) already names this exact debt as open, pre-existing, requiring human curation — not a new regression | **PARTIAL — a real red is on the record inside a table its own summary calls "Verde"; not credited as a clean pass** |
| T003 publish via `make deploy-stg` without `COMPONENTS=` | Open — deployed narrower than the task's own text | `EVIDENCIA.md`: `make deploy-stg`, exit 0, components `app proxy web` — no `COMPONENTS=`, exactly as this task's own text requires. Process finding along the way (the operator's, not this feature's): the manifest declared a fourth component (`console`) that was a full second copy of the application, 18 hours stale; removed from the staging manifest | **DONE** |
| T004 wait for Argo `Synced + Healthy` | Open — no live session opened | `EVIDENCIA.md`: `Synced/Healthy`, GitOps commit `83d7ef9b8bde`. Terser than a literal pasted `kubectl get application` (no explicit instant stamped separately), but the state and the commit are both on record | **DONE** |
| T005 confirm service responds, separately from Argo | Open — same reason as T004 | `EVIDENCIA.md`: `GET /` → `307` to `/sign-in` in 0.03s; `POST /api/session` → session obtained; `POST .../proxmox/verify/report` → `ok: True`; `select count(*) estate` → 100 resources survived. Not literally the three named probes (pods appear under T006 instead; no `/health/ready` curl shown), but a stronger, more substantive set — a live session plus a real Proxmox round-trip is harder to fake than a liveness probe | **DONE** |
| T006 record digest + Argo state in `EVIDENCIA.md` | Open — not present in the narrative `EVIDENCIA.md` | `EVIDENCIA.md`: GitOps `83d7ef9b8bde`; three pods came up together, three old ones left; `app`, `proxy`, `web` at `1/1 Running` | **DONE** |
| T007 discover org identifier | DONE | (unchanged) `org=default`, used successfully across every collected query | **DONE** |
| T008 provider Verified, key from vault | DONE | (unchanged) `antes-01-modelos.png`, re-opened this pass: "Google Gemini · Verified", provider "Google Gemini", model "Gemini Flash Latest" | **DONE** |
| T009 Proxmox connected, `/resources` real | DONE | (unchanged) `antes-02-integracoes.png` re-opened: Proxmox VE listed under "Connected" with "Verified"; `antes-03-recursos.png` re-opened: "100 watched · 71 healthy · 0 degraded · 14 unhealthy" | **DONE** |
| T010 Proxmox token privilege | Open — the claim existed only in chat, not in the file; correctly refused | `EVIDENCIA.md` "O privilégio do token, que faltava aqui": the stored handle carries no identity (the vault behaving correctly); the question was answered from the hypervisor's own `pveproxy` access log, correlating principal against path in the discovery-sweep window (98 calls from `root@pam!infra`, 84 of them `/nodes/pveN`, matching the sweep's own reported 87 provider calls), plus the datacenter ACLs: `root@pam!infra` holds `Administrator` with `propagate 1`. Proxmox VE's built-in `Administrator` role carries every privilege, `VM.PowerMgmt` included — this is how Proxmox defines that role, not an inference. The prior pass's refusal is quoted back inside `EVIDENCIA.md` itself as having been correct | **DONE** |
| T011 operator confirms victim at window open | DONE | (unchanged) `EVIDENCIA.md:4-5`: explicit operator authorization | **DONE** |
| T012 victim `running`, confirmed | DONE | (unchanged) `e5-01-relato.png`, re-opened: "transitioned from running (pve_up == 1) to a stopped state (pve_up == 0)" | **DONE** |
| T013 alert rule active + Alertmanager route | DONE | (unchanged) `e3-01-lista-incidentes.png`, re-opened: `ProxmoxGuestStopped`, `RedisExporterDown`, `InstanceDown`, `GatusEndpointHea…`, `DatabaseTcpProbe…` — all CRITICAL, opened within minutes of each other | **DONE** |
| T014 webhook refuses without credential | PARTIAL | Accept half proven live (`202`, authenticated). Fresh sweep this pass, whole `evidence/` tree, for `401\|403\|sem credencial\|without credential\|unauthenticated\|refus`: the only hit is the still-blank gabarito row `evidence/EVIDENCIA.md:49` ("Webhook recusa entrega sem credencial \| \| \|") and the unrelated `R-...txt` (rejection of an *approval*, a different "R"). No refusal-without-credential probe exists anywhere | **PARTIAL, not done — confirmed absent by a fresh, full sweep** |
| T015 choose the already-firing alert, and why | NOT DONE | `e3-01-lista-incidentes.png`, opened directly: a genuine, live listing of already-firing alerts, `RestoreDrillStale` among them twice (22 minutes ago and 7 hours ago, both `INVESTIGATING`) — real, new evidence for the "listar" half that the prior pass did not cite for this task. But the task also asks to register **which one and why**; a fresh search (`grep -n "porque" evidence/EVIDENCIA.md` and a full read of `achados.md`/`evidence/demo-2026-08-24/`) finds no reasoning anywhere — the demo files are entirely about the CT122 whole loop, never mentioning `RestoreDrillStale`. The choice is inferable from which `run`/`incident` the `evidence/E*.txt` files query, but "inferable from usage" is not "registered with the reason" | **NOT DONE — the listing half now has real evidence; the reasoning half still does not exist anywhere** |
| T016 record the fitness table | NOT DONE | Original gabarito's table still blank; the narrative `EVIDENCIA.md` doesn't use this literal structure | **NOT DONE** (unchanged) |
| T017 read-loop runbook | DONE | (unchanged) `runbooks/laco-de-leitura.md` — preconditions, E1–E7, real URLs, no-write/no-window statement | **DONE** |
| T018 whole-loop runbook | DONE | (unchanged) `runbooks/laco-inteiro.md` — what it is not, the two-condition victim, initial-state check, destructive step, E1–E10 | **DONE** |
| T019 station table in both runbooks | DONE | (unchanged) `laco-de-leitura.md` §3, `laco-inteiro.md` §4 | **DONE** |
| T020 outcome classification, written before execution | DONE | (unchanged) both runbooks, with the separating rule | **DONE** |
| T021 manual rollback before the destructive step | DONE | (unchanged) `laco-inteiro.md` §1 precedes §6 | **DONE** |
| T022 human approval, via the interface | DONE | (unchanged) stated explicitly in the header and in §6 | **DONE** |
| T023 confirm E4–E7 before approving | DONE | (unchanged) `laco-inteiro.md` §6, with the reason stated | **DONE** |
| T024 rejection station, different occurrence | DONE | (unchanged) `laco-inteiro.md` §7 | **DONE** |
| T025 blank `EVIDENCIA.md` skeleton | DONE | (unchanged) present, 8 sections, every field blank | **DONE** |
| T026 secret sweep of the runbooks | DONE | (unchanged) re-swept this pass across `laco-de-leitura.md`, `laco-inteiro.md`, `navegador.md` — no secret present | **DONE** |
| T033 exact collector command in both runbook headers | DONE | (unchanged) present in all three runbooks — `laco-de-leitura.md` §1, `laco-inteiro.md` §0, `navegador.md` step 15 | **DONE** |
| T027 `tools/demo_evidence/` package | DONE | (unchanged) `queries.py`, `collector.py`, `__main__.py`, `__init__.py`, `sql/` | **DONE** |
| T028 the minimum queries, with baselines | DONE | (unchanged) present, including the three schema corrections `controle.md` documents | **DONE** |
| T029 one file per station, query + literal output | DONE | (unchanged) `collector.py::collect`/`file_name_for` | **DONE** |
| T030 refuse anything that is not `SELECT` | DONE | (unchanged) `collector.py::only_select` | **DONE** |
| T031 collector unit test, red confirmed first | DONE | Re-run this pass: `uv run pytest tests/unit/tools/test_demo_evidence.py -q` → **31 passed in 0.15s**, identical to both prior runs | **DONE** |
| T032 no credential printed or written | DONE | (unchanged) forbidden-column test + connection-string-never-written test | **DONE** |
| T034 dry run against staging, pre-wave params | NOT DONE | Neither `evidence/consultas/000-partida.txt` nor the directory exist — reconfirmed this pass (`ls` returns "No such file or directory") | **NOT DONE** (unchanged) |
| T035 confirm baseline values | NOT DONE | Consequence of T034 | **NOT DONE** (unchanged) |
| T036 record the red in `EVIDENCIA.md` §3 | NOT DONE | Table present, "measured dry" column still blank | **NOT DONE** (unchanged) |
| T037 run the read loop end to end | NOT DONE | Database chain ran for real (old evidence); the browsing/screenshot half never did, for this specific run | **NOT DONE** (unchanged) |
| T038 E2/E3 screenshots (read loop) | NOT DONE | This pass opened `e3-01-lista-incidentes.png` and `e3-02-incidente.png` directly: both show `ProxmoxGuestStopped` (header "started 2 minutes ago … node pve02"), the whole-loop's own incident, not `RestoreDrillStale`. No screenshot of the read loop's chosen incident exists anywhere | **NOT DONE — confirmed by opening the screenshots: they belong to a different execution (Fase 7, not Fase 6)** |
| T039 E4 screenshot (read loop) | NOT DONE | This pass opened `e5-01-relato.png` directly: it is the whole loop's run detail (`ProxmoxGuestStopped`'s investigation, 13 events, transcript with real capability calls/results), not `RestoreDrillStale`'s. The DB-level claim for `RestoreDrillStale` is still proven in `evidence/E4-...txt`, but that is not the screenshot this task asks for | **NOT DONE — same finding as T038** |
| T040 E5 screenshot (read loop) | NOT DONE | Same screenshot, same finding as T039: it is the whole loop's report, not the read loop's | **NOT DONE — same finding as T038** |
| T041 tools match connected integrations (read loop) | NOT DONE | No artefact — neither transcript nor tool-selection log for the read loop's own run | **NOT DONE** (unchanged) |
| T042 E7 screenshots (read loop) | NOT DONE | `evidence/E7-...txt` still shows 0 rows for the read loop's run — a declared-acceptable outcome per the runbook. No screenshot of `/decisions` for this specific run exists (the screenshots that do exist, `e7-01-incidente-apos.png`/`e10-02-decisoes.png`, are the whole loop's — see T053 below) | **NOT DONE** (unchanged, confirmed) |
| T043 run the collector, attach per-station output | DONE | (unchanged) 8 files under `evidence/`, real literal output, dated `2026-08-24T09:11:29Z` | **DONE** |
| T044 repeat the read loop, compare | NOT DONE | One collection, one instant; no second pass recorded | **NOT DONE** (unchanged) |
| T045 open the window, record victim confirmation | DONE | (unchanged) `EVIDENCIA.md:4-5`, `marco-zero.txt` | **DONE** |
| T046 the destructive step, typed once | DONE | (unchanged) `marco-zero.txt`: `pct stop 122` at 10:26:29Z, confirmed 10:26:36Z | **DONE** |
| T047 E1 — the alert fires on its own | DONE | (unchanged) `EVIDENCIA.md:12-13`: `activeAt` 10:27:34, fired 10:29:34 after `for: 2m` | **DONE** |
| T048 E2 — delivery arrives authenticated | DONE | (unchanged) `202` at 10:29:45, "authenticated by alertmanager-delivery"; no dedicated screenshot, timeline/text record only | **DONE, with the same caveat as before (no dedicated E2 screenshot)** |
| T049 E3 — incident opens legible, subject resolved | NOT DONE | `e3-02-incidente.png`, re-opened by this pass directly: title `ProxmoxGuestStopped` (not a sentence — finding 1) and header "node pve02" three lines above the alert body's "node=pve01" (finding 2), both visible without scrolling in the same capture. Left exactly as the prior pass left it, by explicit instruction, now doubly confirmed by an independent reading | **NOT DONE, unchanged — reconfirmed directly** |
| T050 E4 — investigation records | DONE | (unchanged) `e5-01-relato.png`, re-opened: 13 events, 5 turns, 44,746 tokens, 4 real capability calls each with a real result, cost apportioned per turn, "what this investigation touched" filled (incident + 2 resources). Named gap unchanged: the collector never ran against this run's own id | **DONE, with the same named gap as before** |
| T051 E5 — report is legible | DONE | (unchanged) Headline: "Proxmox LXC container redis on node pve01 stopped unexpectedly causing service and exporter outages" — full sentence, no raw markdown visible, correct node | **DONE** |
| T052 E6 — tools match what is connected | DONE | (unchanged) 4-call table in `EVIDENCIA.md`, verified again against `e5-01-relato.png`'s own transcript: `prometheus_active_alerts` SUCCEEDED, `proxmox_guest_tasks` FAILED (Proxmox `501` verbatim), `changes_in_window` FAILED ("unknown rather than answered" verbatim), `assess_evidence_sufficiency` SUCCEEDED | **DONE** |
| T053 E7 — proposal waits with a rollback plan | NOT DONE | This pass opened `e7-01-incidente-apos.png` and `e10-02-decisoes.png` directly: "Nothing proposed yet / No investigation has concluded with a remediation to decide on for this incident" and "Nothing is waiting on a decision / … The active rule asks for approval for actions at write_reversible and above." Real screenshot evidence of the *correct absence*, not of a proposal. Verdict unchanged: the catalogue's entire write surface is three notification capabilities; nothing acts on infrastructure; the desk composed 20 capabilities, the gate registers per run, the 40-tool ceiling was nowhere near hit (4 used) | **NOT DONE — not exercised, declared product-scope, now with screenshot evidence of the correct absence rather than none at all** |
| T054 confirm E4–E7 before approving | NOT DONE | No proposal exists to confirm before approving | **NOT DONE** (unchanged, not applicable) |
| T055 E8 — operator approves via the interface | NOT DONE | No proposal, no decision to make | **NOT DONE — not exercised, product-scope, same reason as T053** |
| T056 E9 — execution happens through the gate | NOT DONE | No approval, no execution | **NOT DONE — not exercised, product-scope, same reason as T053** |
| T057 E10 — incident reflects the outcome | DONE | (unchanged) `e10-01-incidente-fechado.png`, re-opened: chip reads "Resolved"; `EVIDENCIA.md:62-70`: `state: resolved`, `close_reason` names the real cause, `self_resolved: true` | **DONE** |
| T058 confirm alert resolved and closed the incident | DONE | (unchanged) same event as T057 | **DONE** |
| T059 reversion: confirm guest is `running` | DONE | (unchanged) `marco-zero.txt`: restarted by hand at 10:44:47Z | **DONE** |
| T060 close the window, record instant + summary | DONE | (unchanged, "in substance") `EVIDENCIA.md` itself is the summary; no separate "window closed at HH:MM" line | **DONE, in substance** |
| T061 reject without a reason | NOT DONE | No proposal of any kind existed to reject in this run | **NOT DONE — not exercised, product-scope, per explicit instruction** |
| T062 reject with a reason | NOT DONE | Same reason as T061 | **NOT DONE — not exercised, product-scope** |
| T063 confirm both decisions in the audit trail | NOT DONE | No decisions exist to appear in the trail | **NOT DONE — not exercised, product-scope** |
| T064 name resolution inside each monitoring container | NOT DONE | Not read; `backlog.md` carries the last known state | **NOT DONE** (unchanged) |
| T065 managed-secret sync | NOT DONE | Not read; `backlog.md` entry still present | **NOT DONE** (unchanged) |
| T066 model-gateway key, Verified | NOT DONE | The self-hosted gateway is a different provider from the already-Verified Google Gemini; no fresh evidence about it | **NOT DONE** (unchanged) |
| T067 backlog entry for each unfinished operational task | DONE | (unchanged) all three present in `backlog.md` | **DONE** |
| T068 mark stations blocked by a pending operational task | NOT DONE | E7–E9 were not exercised, but for none of the three operational reasons this task anticipates — the real reason is a product-scope fact (no infrastructure-write capability exists), not a pending DNS/secret/key task | **NOT DONE — the task's own premise does not hold** (unchanged) |
| T069 fill `EVIDENCIA.md` station by station | DONE | (unchanged, "in a document of its own") `evidence/demo-2026-08-24/EVIDENCIA.md` ties expectation/evidence/verdict per station in prose | **DONE** |
| T070 confirm full-page 1920×1080 screenshots | NOT DONE | Reconfirmed directly this pass: `file` on all eleven PNGs → every one is `1280 x N` (773 to 2370), genuinely full-page but at the wrong width. No dedicated E2 screenshot | **NOT DONE — width reconfirmed directly, not merely repeated** |
| T071 confirm query + literal output per recording station | NOT DONE | The collector never ran against `run=d393d5d0…`/`incident=inc_05328c58ca88676b`; `evidence/consultas/` still does not exist | **NOT DONE** (unchanged) |
| T072 secret sweep, text and screenshots | DONE | (unchanged) all text files clean; all eleven screenshots opened and read directly in this pass (again) — none shows a token, password, or credential | **DONE** |
| T073 run owning-feature acceptance + transversal against staging | NOT DONE | Last measurement on file is 2026-08-23; not re-run, by instruction (no staging touch) | **NOT DONE** (unchanged) |
| T074 one-sentence verdict + per-station verdicts at the top | NOT DONE | The new `EVIDENCIA.md` opens with a factual timeline paragraph, not a single verdict sentence; "Estações cumpridas"/"Estações NÃO exercidas" cover the per-station half in prose | **NOT DONE — two of three parts present, verdict sentence still absent** (unchanged) |
| T075 list every finding in `EVIDENCIA.md` §6 | DONE | (unchanged, "in a document of its own") four numbered findings with description and evidence | **DONE** |
| T076 hand product-owned findings to the orchestrator, don't fix | DONE | (unchanged) zero product files touched, reconfirmed again this pass | **DONE** |
| T077 write backlog entries for ownerless findings | NOT DONE | `grep` for any of the five findings' distinctive text in `backlog.md` returns nothing; `CONFRONTO.md:513-527` also still lists them "sem dono ainda" | **NOT DONE** (unchanged, reconfirmed) |
| T078 re-run and replace evidence after a repair | NOT DONE | No repair happened inside this feature | **NOT DONE** (unchanged) |
| T079 per-feature verifier verdicts in `CONFRONTO.md` | NOT DONE | `CONFRONTO.md`'s own header reserves this to the orchestrator, not a feature confrontation | **NOT DONE, deliberately** (unchanged) |
| T080 the fixed "who builds this in production?" column | DONE | (unchanged) `specs_v7/CONFRONTO.md`, "Quem constrói isso em produção?" | **DONE** |
| T081 column filled for the required minimum mechanisms | DONE | (unchanged) all required rows present with `file:line`, spot-checked in the second pass against `gateway/http/lifespan.py` and found byte-accurate | **DONE** |
| T082 dormant mechanisms declared | DONE | (unchanged) 3 entries, none pointing at a test | **DONE** |
| T083 confronto closes citing the demo as evidence | DONE | (unchanged) present, with the path and a verdict — though that verdict text is the stale one named above | **DONE** |
| T084 backlog-destination table in the confronto | DONE | (unchanged) 11 of 11 rows, zero without a destination | **DONE** |
| T085 rewritten `backlog.md` | DONE | (unchanged) 14 items | **DONE** |
| T086 wording checked against committed-file rules | DONE | Re-swept this pass: `grep -nE "FR-[0-9]\|SC-[0-9]\|specs_v[0-9]\|Article [IVXLC]\|constitution\|feature [0-9]{3}"` against `backlog.md` → no matches | **DONE** |
| T087 the file's existing shape preserved | DONE | (unchanged) every item has "what happens today" / "why it is not trivial" / "how it should be judged" | **DONE** |
| T088 no removed item without named evidence | DONE | (unchanged) checked row by row against the destination table | **DONE** |
| T089 full `make verify` | NOT DONE | Never run as one command, before or after publish. This pass ran the static/architecture slice itself, fresh: collector 31/31, `tests/unit/tools`+`tests/architecture` **752 passed** (734 at the last audit, zero failures, growth from other merges), raw-SQL strict test 53/53, lint/format/mypy clean, 5 guard scripts clean, all 7 import contracts kept. General pytest suite, `console-check`, `console-visual` not attempted — deliberately, given ~20 concurrent agent worktrees on the same host and a known, disclosed red already on file for the visual piece | **NOT DONE — reconfirmed with genuine, fresh, own-run evidence for the slice this pass could safely run** |
| T090 no product file touched | DONE | (unchanged) `git diff --stat` outside the declared lane returns zero files | **DONE** |
| T091 write this feature's `controle.md` | DONE | Rewritten again in this pass with the third-pass ledger | **DONE** |
| T092 report to the orchestrator | DONE | This report | **DONE** |

## Evidence and corrections

### T001–T006 — the publication cycle, read and cross-checked

`evidence/demo-2026-08-24/EVIDENCIA.md`, section "O ciclo de publicação,
executado depois da demo" (lines 196–266 of that file), read in full. Each
task's own text was checked against the recorded output rather than against
the section's summary prose:

- **T001**: the merge/PASS claim was cross-checked two ways. First,
  directly: `git log --oneline abbc418..HEAD` on this worktree's tree
  returns **235** commits, against the 233 the evidence file records — a
  difference of exactly the two `docs(wave)` commits that landed after that
  count was written (`5e7f1e8`, `68e13d9`), so the numbers agree rather than
  conflict. Second, against `specs_v7/CONFRONTO.md`: `S0` carries an
  explicit `**PASS**`; `S1` (`001`+`020`) shows `make verify: exit 0 —
  12278 passed / 27 skipped` with no failing line; `S2 a S5` narrates every
  one of the seven remaining features closing something specific, and a
  sweep for `REPROVOU|FAIL...|reprovad` across the whole file returns zero
  matches. This pass did not re-open each of the nine preceding features'
  own `controle.md` line by line — that would re-litigate nine other
  verifiers' own work — and says so rather than implying it did.
- **T002**: read in full, table intact
  (`EVIDENCIA.md:207-223`). Traced the one named failure to its source:
  `tests/contract/console/test_console_visual_regression.py:156-167`
  (`test_the_untouched_baselines_still_match`) asserts
  `finished.returncode == 0` for `python -m tools.console_visual compare`,
  and its own docstring states its purpose is to prove the comparison "is
  not simply always red" — meaning a failure here is a genuine pixel
  divergence, not a flake. Checked whether `console-visual` sits inside the
  `verify:` Make target: it does not (`Makefile:516-521` lists lint,
  format-check, typecheck, the `check-*` scripts, `console-check`, and
  `test` — `console-visual` only enters via `ci-run`, `Makefile:494`), but
  the *test* that failed lives inside the general `test` target, which is
  in `verify:`. Checked whether this is a new regression: `CONFRONTO.md:433-434`
  — dated before this session — already lists "Baselines visuais das telas
  reformadas: recapturar e aceitar é revisão humana" as an open, known item.
  Both facts are true at once: the debt is old and disclosed, and it is
  still the red T002's own text calls a publish-blocker. Left open rather
  than credited.
- **T003–T006**: each checked against its own specific ask.
  `EVIDENCIA.md:229-252` records `make deploy-stg` with components
  `app proxy web` (no `COMPONENTS=`, T003's own explicit requirement), the
  Argo `Synced/Healthy` state with GitOps commit `83d7ef9b8bde` (T004), a
  four-line live-probe table — public URL, session, Proxmox round-trip,
  estate count (T005) — and the pod rollout state plus the same GitOps
  commit (T006). T005's own three named probes (pods, `/health/ready`,
  public URL) are not all present in T005's own paragraph — pods appear
  under T006 instead, and no `/health/ready` curl is shown — but the
  substantive claim (the service responds, independent of what Argo
  reports) is proven by a stronger set of checks than the three named ones
  would have been on their own.

### T010 — the token's privilege, apurada

`EVIDENCIA.md:153-182` read in full. The reasoning chain: the stored
credential handle (`proxmox/-@v1`) carries no identity by design (the vault
withholding the principal is correct behaviour, not a gap); the question was
therefore answered from the hypervisor side, in the `pveproxy` access log,
correlating principal against path in the discovery sweep's window
(06:51 local = 09:51 UTC) — `root@pam!infra` made 98 calls, 84 of them
`/nodes/pveN` plus HA and cluster-config reads, a pattern matching the 87
provider calls the discovery sweep itself reported; `prometheus@pve` made
136 calls to `/cluster/status`, `/cluster/resources`, `/version`, consistent
with a regular scrape rather than a sweep. The datacenter ACLs:
`root@pam!infra` → `Administrator`, `propagate 1`. Proxmox VE's built-in
`Administrator` role is the one that carries every privilege, `VM.PowerMgmt`
included — general knowledge about the product this repository integrates
with, not a claim this pass could verify against source in this repository,
and not verified live either, since this pass did not open a session to the
hypervisor. `EVIDENCIA.md:155-158` itself quotes the second pass's refusal
back and calls it correct — this pass agrees with that framing and credits
the box now that the fact is written down, exactly as the second pass's
condition required.

### T014, T015 — the two searched exhaustively, one open by instruction, one upgraded in part

For T014, a fresh sweep (`grep -rniE
"401|403|sem credencial|without credential|unauthenticated|refus"` across
the whole `evidence/` tree) found exactly two hits: the still-blank gabarito
row `evidence/EVIDENCIA.md:49` and `evidence/R-the-refusal-path-exercised-on-a-different-occurr.txt`,
which is about rejecting an *approval*, an unrelated "R." No
refusal-without-credential probe exists anywhere in the record.

For T015, `spec.md:32-34` was checked first, since it also mentions
`RestoreDrillStale` — but that mention is under "Pré-condições verificadas
(2026-08-23 — não re-derivar)," establishing the environment has real firing
alerts before the spec existed, not a T015 registration. `runbooks/laco-de-leitura.md`
was read again in full: it is written alert-agnostic (parameterised by
`RUN_ID`/`INCIDENT_ID`), so it does not itself name which alert was chosen.
`e3-01-lista-incidentes.png`, opened directly, is a live capture of the
Alertmanager-backed incident list showing `RestoreDrillStale` twice
(`22 minutes ago`, `7 hours ago`, both `INVESTIGATING`, the second with 5
subjects) alongside the CT122 incidents — genuine evidence for the "listar"
verb that no prior pass had cited for this specific task. But a full text
search (`grep -n "porque" evidence/EVIDENCIA.md`, plus a full read of
`achados.md` and every file in `evidence/demo-2026-08-24/`) finds no written
reason anywhere; those files are entirely about the CT122 whole loop and
never mention `RestoreDrillStale`. The choice is inferable from which
`run`/`incident` values the `evidence/E*.txt` files query, but inference is
not the written record T015 asks for.

### T038–T042 — opened, and found to belong to a different execution

Each of the eleven screenshots in `evidence/demo-2026-08-24/` was opened
directly in this pass (not sampled, not inferred from filenames).
`e3-01-lista-incidentes.png` and `e3-02-incidente.png` (naming suggests
"E3", which both T038 and T049 touch) show, on inspection, the incident
`ProxmoxGuestStopped` — header "alertmanager · Alertmanager · started 2
minutes ago · zone Unplaced · node pve02" — which is the whole-loop
demo's own incident (Fase 7, T049's subject), not `RestoreDrillStale` (Fase
6, T015's chosen read-loop alert, T038's subject). `e5-01-relato.png`
(dimensions 1280×2370, the tallest of the eleven) shows the same
`ProxmoxGuestStopped` investigation's run detail — headline "Proxmox LXC
container redis on node pve01 stopped unexpectedly…", the same 4-call
transcript `EVIDENCIA.md` narrates — again the whole loop's own evidence,
not a capture of `RestoreDrillStale`'s run (T039/T040's subject). No
screenshot of `RestoreDrillStale`'s incident, run, report, or tool selection
exists among the eleven. T038–T042 (Fase 6, explicitly a *separate*
execution of `laco-de-leitura.md` against the alert T015 was meant to
choose) therefore remain open: the whole loop's screenshots are excellent,
real evidence for T049–T052 (already credited), and would only satisfy
T038–T042 by treating one execution's evidence as if it were a different
one's — which this pass declines to do.

### T049 — reconfirmed directly, left exactly as instructed

`e3-02-incidente.png` opened by this pass, independent of the prior pass's
own reading. Confirmed line by line: title "ProxmoxGuestStopped" (the
breadcrumb reads "Incidents > ProxmoxGuestStopped"; the page's own `<h1>` is
the same string) — not a sentence. Header, immediately below the title:
"alertmanager · Alertmanager · started 2 minutes ago · zone Unplaced ·
**node pve02**". Three lines further down, inside the "Alert received" body:
"alertname=ProxmoxGuestStopped, cluster=HAL9000, criticality=high,
env=homelab, id=lxc/122, instance=192.168.68.159, job=pve-exporter,
name=redis, **node=pve01**, service=pve-exporter, severity=critical,
type=lxc" — both claims visible in one screenshot, no scrolling required
between them. Left open exactly as instructed.

### T053–T056, T061–T063 — not exercised, now with screenshot evidence of the correct absence

`e7-01-incidente-apos.png` (`ProxmoxGuestStopped`, "started 3 minutes ago,"
one minute later than `e3-02-incidente.png`'s capture — a genuinely distinct
moment, not a duplicate) shows the "Proposed action" panel: "Nothing
proposed yet / No investigation has concluded with a remediation to decide
on for this incident." `e10-02-decisoes.png` shows the `/decisions` →
Actions tab: "Nothing is waiting on a decision / A change that needs a
person appears here with its blast radius and its rollback plan. None does.
The active rule asks for approval for actions at write_reversible and
above." Both are real screenshots of the demo's own CT122 run, and both
show the *correct*, declared-acceptable absence `EVIDENCIA.md` already
narrates in prose (three write capabilities in the whole catalogue, all
notifications, nothing acts on infrastructure). This does not change any of
the seven verdicts — nothing was proposed, so nothing could be approved,
executed, or rejected — but it moves the evidentiary basis from prose alone
to prose plus two directly-verified screenshots.

One observation surfaced while comparing these captures pixel-for-pixel:
`e10-02-decisoes.png` and `antes-04-decisoes.png` are byte-identical
(`md5sum 8b02f4d00f9ebb76c7ecf78c95723411`, both). `git log --follow` on
each returns the same single commit (`3505420f`) and the same checkout
timestamp, so history cannot distinguish "captured twice, pixel-identical
because the screen is static and nothing was ever proposed" from "one file
saved under two names." Named because a rigor sweep should catch it, not
because it changes any verdict — the claim both captures support is
internally consistent with everything else on file.

### T089 — the gate on the final tree, with fresh evidence for the slice this pass could run safely

`Makefile:516-521` read directly to establish `verify:`'s exact composition:
`lint format-check typecheck check-imports check-constants check-protocols
check-deps check-vendor-sdks check-literals check-raw-sql
check-run-status-vocabulary check-credentials check-console-boundary
check-integrations check-integration-docs check-env-example check-docs
check-doc-examples console-check test`. This pass ran, itself, on the
current tree (`68e13d9` and this pass's own commits on top):

| Gate | Command | Result |
|---|---|---|
| Collector unit tests | `uv run pytest tests/unit/tools/test_demo_evidence.py -q` | **31 passed in 0.15s** |
| Tools + architecture suite | `uv run pytest tests/unit/tools tests/architecture -q` | **752 passed, 3 warnings in 48.65s** |
| Raw-SQL guard, strict test | `uv run pytest tests/unit/tools/test_check_raw_sql.py -q` | **53 passed in 4.96s** |
| Lint | `uv run ruff check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | All checks passed! |
| Format | `uv run ruff format --check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | 5 files already formatted |
| Types | `uv run mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | Success: no issues found in 5 source files |
| Constants guard | `uv run python tools/check_constants.py` | exit 0 |
| Direct-credential guard | `uv run python tools/check_direct_credentials.py` | exit 0 |
| Protocol-body guard | `uv run python tools/check_protocol_bodies.py` | exit 0 |
| Runtime-dependency guard | `uv run python tools/check_dependencies.py` | exit 0 |
| Raw-SQL guard, CLI | `uv run python tools/check_raw_sql.py` | exit 0 |
| Docs-drift guard | `uv run python -m tools.check_docs_drift` | exit 0 |
| Documented examples | `uv run python -m tools.test_doc_examples` | 29 documented example(s) check out |
| Integration-catalogue parity | `uv run python -m tools.verify_integrations` | 15 integration(s) at full parity, every permission probed |
| Import contracts | `PYTHONPATH=$(pwd) uv run lint-imports` | Contracts: 7 kept, 0 broken |

Every number matches or exceeds the second audit's own run (734 → 752 tests
in the tools+architecture suite, purely from other merges landing; zero
failures either time). Not attempted: the general `test` target's full
pytest collection (the 12,000+-case scale pass two measured piece by piece),
`console-check` (pnpm/vitest/tsc/eslint/prettier/build/e2e — needs a
provisioned console toolchain this pass did not set up), and
`console-visual` (needs Docker and the pinned capture image, and its true
state — one real failure — is already known and disclosed via T002). The
decision not to attempt the full suite is deliberate: `git worktree list`
shows roughly twenty other agent worktrees active on this same host at the
time of this pass, and pass two's own account of background invocations of
this scale "dying at the same point" reads as a real resource-contention
risk in a shared environment, not a one-off. T089 stays open, honestly, with
the slice this pass could respons­ibly run credited on its own merits rather
than stretched to cover the whole gate.

### `specs_v7/CONFRONTO.md` — an internal contradiction, named and not corrected

`grep -n "não executado\|worktree isolada e não alcança" specs_v7/CONFRONTO.md`
finds `:360` ("Veredito da demo: não executado... quem escreveu os roteiros
roda em worktree isolada e não alcança cluster, banco nem Alertmanager"),
inside a section titled "A demo, e o que ela ainda deve" (`:353-368`). The
same file, starting at `:451` ("A demo, executada · 2026-08-24"), narrates
the whole loop having run against the real hypervisor, with the E1–E10
timeline and the same four product findings `EVIDENCIA.md` lists. Both
sections are present, unedited, contradicting each other. Not corrected in
this pass, for the reason the second pass already gave and this pass
independently agrees with after reading the file's own opening lines: it
states plainly that it is measured by the orchestrator and never copied from
an implementer's report, which is the same boundary that already reserves
T079 to the orchestrator rather than to a feature confrontation. Named here
so it does not go unnoticed a second time.

## Verification

Gates actually run in this pass, on the current tree (this worktree
fast-forwarded to `68e13d9`, then this pass's own commits on top of that):

| Gate | Command | Result |
|---|---|---|
| Collector unit tests | `uv run pytest tests/unit/tools/test_demo_evidence.py -q` | **31 passed in 0.15s** |
| Tools + architecture suite | `uv run pytest tests/unit/tools tests/architecture -q` | **752 passed, 3 warnings in 48.65s** |
| Raw-SQL guard, strict test | `uv run pytest tests/unit/tools/test_check_raw_sql.py -q` | **53 passed in 4.96s** |
| Lint | `uv run ruff check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | All checks passed! |
| Format | `uv run ruff format --check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | 5 files already formatted |
| Types | `uv run mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | Success: no issues found in 5 source files |
| Constants guard | `uv run python tools/check_constants.py` | exit 0 |
| Direct-credential guard | `uv run python tools/check_direct_credentials.py` | exit 0 |
| Protocol-body guard | `uv run python tools/check_protocol_bodies.py` | exit 0 |
| Runtime-dependency guard | `uv run python tools/check_dependencies.py` | exit 0 |
| Raw-SQL guard, CLI | `uv run python tools/check_raw_sql.py` | exit 0 |
| Docs-drift guard | `uv run python -m tools.check_docs_drift` | exit 0 |
| Documented examples | `uv run python -m tools.test_doc_examples` | 29 documented example(s) check out |
| Integration-catalogue parity | `uv run python -m tools.verify_integrations` | 15 integration(s) at full parity, every permission probed |
| Import contracts | `PYTHONPATH=$(pwd) uv run lint-imports` | Contracts: 7 kept, 0 broken |
| Wave commit count | `git log --oneline abbc418..HEAD \| wc -l` | **235** |
| CONFRONTO.md failure sweep | `grep -niE "REPROVOU\|FAIL...\|reprovad" specs_v7/CONFRONTO.md` | no matches (exit 1) |
| CONFRONTO.md staleness sweep | `grep -n "não executado\|worktree isolada e não alcança" specs_v7/CONFRONTO.md` | 1 match, at the pre-existing stale section — see Evidence |
| Webhook-refusal sweep | `grep -rniE "401\|403\|sem credencial\|without credential\|unauthenticated\|refus" evidence/` | 2 matches, neither is the probe T014 asks for — see Evidence |
| Backlog finding-ownership sweep | `grep -n` for each demo finding's distinctive text, against `backlog.md` | no matches |
| Screenshot dimensions | `file` on all eleven PNGs in `evidence/demo-2026-08-24/` | all `1280 x N` (773–2370) |
| Screenshot duplication check | `md5sum` on all eleven PNGs | `e10-02-decisoes.png` = `antes-04-decisoes.png`, byte-identical; the other nine are all distinct |
| Screenshots opened directly | `e3-01`, `e3-02`, `e5-01`, `e7-01`, `e10-01`, `e10-02`, `e10-03`, `antes-01`, `antes-02`, `antes-03` | all opened and read in this pass; contents match what is claimed above |

**Not run, and why:**

- `make verify` (full, single command) — never run, by anyone, on this
  tree. This pass ran the static/architecture slice above instead, fresh,
  as the responsibly-scoped substitute; T089 stays open rather than
  credited from that slice alone.
- The general pytest suite beyond `tests/unit/tools`+`tests/architecture`
  (the 12,000+-case scale pass two measured piece by piece), `console-check`,
  and `console-visual` — not attempted, for the shared-host resource-
  contention reason stated in the T089 evidence section above.
- Any live read against staging, the cluster, the hypervisor, or
  Alertmanager — not run, by explicit instruction not to touch staging,
  `pve01`, `pve02`, or CT122. Every T001–T006/T010 claim in this report
  comes from reading `evidence/demo-2026-08-24/EVIDENCIA.md` and the
  screenshots it references, not from a fresh probe against any of those
  targets.
- No test was written test-first in this pass, for the same reason as the
  prior two passes: nothing was found both missing and inside this
  feature's own implementable surface (`tools/demo_evidence/`, its test, the
  docs). Every task this pass moved to done was already proven by
  already-committed evidence; every task left open needs either a live
  environment this pass does not touch, or an orchestrator-level judgment
  (T002's debt-versus-blocker call, T077's ownership assignment, T079's
  cross-feature verdicts) this pass does not make unilaterally. There was
  accordingly no red to confirm and no implementation phase.

## Control reconciliation

**`specs_v7/080-incidente-fecha-o-laco/tasks.md`**: moved from 52 of 92 to
**58 of 92** boxes checked. Six moved from open to done in this pass — T001,
T003, T004, T005, T006, T010 — each on the two new `EVIDENCIA.md` sections,
independently cross-checked against source where a cross-check was possible
without touching staging. T002 was investigated in the same depth as those
six and deliberately **not** flipped: its own recorded table names a real
failure inside a "Verde" summary, and this pass declines to round that up.
The other 33 stay exactly as the second pass left them, each re-examined
rather than merely re-stated — T014, T015, T038–T042, T049, T053–T056, and
T061–T063 by explicit instruction, and the remainder by a fresh spot-check
against the current tree that found no drift in either direction.

**`specs_v7/080-incidente-fecha-o-laco/controle.md`**: a new "Terceira
auditoria" section was added, following the file's own established pattern
of layering a new dated pass on top of prior ones rather than rewriting
them — the "Segunda auditoria" text from earlier the same day is untouched,
exactly as it left the second pass's own text from 2026-08-23 untouched. The
Fase 1 table (T001–T006) and the T010 row in the Fase 2 table were revised
in place, with the prior state preserved alongside the new one, so the
ledger never states two contradictory things about the same task without
saying which is current. The "O que fica pendente" table was rewritten to
drop the six closed items and add T002's real exception, T015's and
T038–T042's refined reasoning, and the `CONFRONTO.md` self-contradiction. A
closing section states the final count and what stayed open by instruction
versus by genuine gap.

**`specs_v7/080-incidente-fecha-o-laco/relatorio-confronto.md`**: this
report, rewritten in full rather than appended — the full 92-row table is
reproduced so a reader gets one complete, current picture rather than having
to overlay three reports by hand, with every unchanged row marked as
re-spot-checked rather than carried over silently.

**`specs_v7/CONFRONTO.md`** and **`evidence/EVIDENCIA.md`** (the original
gabarito): both read, neither written — the first for the reason stated
above (orchestrator-owned, and its self-contradiction is named rather than
fixed), the second because it remains the untouched, blank gabarito the
narrative `evidence/demo-2026-08-24/EVIDENCIA.md` supersedes in substance
without literally filling in.
