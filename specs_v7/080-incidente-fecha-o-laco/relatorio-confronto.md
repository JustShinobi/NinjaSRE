# Confrontation report — 080 O incidente fecha o laço

## Conclusion

`tasks.md` drifted in exactly the direction the dispatching brief named: every
one of its 92 boxes was unchecked, and that was wrong for 32 of them — the
runbooks, the evidence collector with its 31-case test suite, the confronto
column, and the rewritten backlog all exist, are correct, and pass their gates
today exactly as `controle.md` (a separate, prose-form control document for
this same feature) already claimed on 2026-08-23. The boxes never reflected
the prose; nobody had gone back and ticked them. That gap is now closed: 32
boxes are checked, each with the `file:line` or test that proves it, verified
independently in this audit rather than copied from the prior session's own
report.

The other 60 do not get a box, and every one of them gets a reason instead of
silence. The overwhelming majority are the demonstration itself — the janela
combinada, the destructive step against CT122, the human approval in the
browser — which this audit was explicitly instructed not to touch, and did
not: no SSH session, no `kubectl`, no request against
`https://stg-ninjasre.lan.kyo.ninja`, no write of any kind. But three commits
landed in `master` today, 2026-08-24, authored by the operator
(`kyo@kyo.ninja`) rather than by any agent, after the point `controle.md`'s
prior pass had inspected. They are real: the evidence collector this feature
built ran for real against the staging Postgres, and eight files under
`evidence/` now carry live query output for one real investigation
(`RestoreDrillStale` over `192.168.68.159`, run
`0c9c0d5ce453458d9e115af98763ade4`) — five recorded turns, four tool calls,
one evidence row, a headline that reads as a sentence while the underlying
document still opens with `###`, and a legitimate zero-proposal outcome for a
run that found nothing to remediate. That is real, useful, current-source
proof that half of User Story 2 (the read loop) executed against real data,
and it moved one task (T043) from "not done" to "done" that would otherwise
have stayed grouped with the rest of the demo. The other half — the window,
the approval, the execution, the rejection — is proven **not yet** to have
happened by the same evidence: the approval and outcome tables the collector
already reads all come back at zero rows, dated the same instant. That is the
correct state for the boundary this audit was told to hold, evidenced rather
than assumed.

One thing this audit found and is handing back rather than fixing, per this
feature's own rule against repairing product code: a tool call in that same
real investigation, `prometheus_metric_statistics`, came back `400` from
Prometheus with `invalid parameter "start": cannot parse "" to a valid
timestamp` — a candidate product defect (an empty start parameter reaching a
range query), not classified or assigned an owner here because that judgment
belongs to whoever closes the full demonstration with the destructive loop's
evidence in view.

## Table

Convention for "Final status": **DONE** — the code, a test, or already-committed
evidence proves it; box checked. **NOT STARTED / PARTIAL, not done — reason
given** — box left unchecked, with the reason this table and the Evidence
section state; none are silent. No item in this feature had regressed
(**REGRESSED**) — everything `controle.md` claimed done on 2026-08-23 was
independently reconfirmed done today.

| Item | What `tasks.md` claimed (before) | What the code proved (before this audit) | Final status |
|---|---|---|---|
| T001 confirm wave merges + PASS, record tree commit | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE** — orchestrator; needs a verifier's judgment across features this audit does not re-measure |
| T002 `make verify` before publish | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE** — orchestrator; tied to the `deploy-stg` action |
| T003 publish via `make deploy-stg` | unchecked | not run | **NOT DONE** — infrastructure change, out of this feature's bounds by its own rule |
| T004 wait for Argo `Synced + Healthy` | unchecked | not read | **NOT DONE** — requires a live `ssh`/`kubectl` session this audit does not open |
| T005 confirm service responds, separately | unchecked | not read | **NOT DONE** — same reason as T004 |
| T006 record digest + Argo state in `EVIDENCIA.md` | unchecked | `EVIDENCIA.md` §1 blank | **NOT DONE** — depends on T003–T005 |
| T007 discover org identifier | unchecked | not written to `EVIDENCIA.md` §2, but used correctly | **DONE** — `evidence/E4-...txt`: `org=default` returns real, non-empty, org-scoped counts (5 turns, 4 calls, 1 evidence row); a wrong `:org` would return zero everywhere |
| T008 provider Verified, key from vault | unchecked | no screenshot | **NOT DONE** — orchestrator; indirect evidence only (real Gemini calls succeed in `evidence/E4-...txt`), not the Verified-label proof the task requires |
| T009 Proxmox connected, `/resources` real | unchecked | `evidence/E3-...txt`: `estate_resources` present count = **0** | **NOT DONE** — the only real reading on file still shows the pre-wave baseline (0), collected 09:11 UTC today; no screenshot exists |
| T010 Proxmox token privilege | unchecked | not read | **NOT DONE** — live console read, operator's security-boundary decision |
| T011 operator confirms victim at window open | unchecked | not recorded | **NOT DONE** — verbal confirmation, inherently outside a code audit |
| T012 victim `running`, confirmed | unchecked | not read | **NOT DONE** — live `pct status`; dispatcher-reported "CT122 currently healthy" is context, not this audit's own verified reading |
| T013 alert rule active + Alertmanager route | unchecked | not read; confirmed no rule definitions exist anywhere in this repository | **NOT DONE** — the monitoring stack's rules live outside this repository by construction |
| T014 webhook refuses without credential | unchecked | not probed | **NOT DONE** — this audit initiates no request against the live staging target |
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
| T045 open the window, record victim confirmation | unchecked | not recorded | **NOT DONE** — orchestrator; the operator's own live action |
| T046 the destructive step, typed once by a person | unchecked | not performed | **NOT DONE, and correctly so** — this audit was explicitly instructed not to touch CT122 or `pve01`/`pve02`, and did not |
| T047 E1 — the alert fires on its own | unchecked | `evidence/E9-...txt`/`E8-...txt`: zero rows anywhere downstream | **NOT DONE** — no alert from this run has reached the tables the collector reads |
| T048 E2 — the delivery arrives authenticated | unchecked | same zero-row evidence | **NOT DONE** |
| T049 E3 — the incident opens legible | unchecked | same zero-row evidence | **NOT DONE** |
| T050 E4 — the investigation records | unchecked | same zero-row evidence | **NOT DONE** |
| T051 E5 — the report is legible | unchecked | same zero-row evidence | **NOT DONE** |
| T052 E6 — the tools match what is connected | unchecked | same zero-row evidence | **NOT DONE** |
| T053 E7 — the proposal waits with a rollback plan | unchecked | `evidence/E7-...txt`: 0 rows in `approvals` for any run of this loop | **NOT DONE** |
| T054 confirm E4–E7 before approving | unchecked | n/a — nothing to confirm yet | **NOT DONE** |
| T055 E8 — the operator approves, via the interface | unchecked | `evidence/E8-...txt` `nothing-executed-unattended`: 0; `decision`/`audit-of-the-decision`: `NOT COLLECTED`, no `--approval` value exists | **NOT DONE** |
| T056 E9 — execution happens through the gate | unchecked | `evidence/E9-...txt`: `outcome` `NOT COLLECTED`, `episode`: 0 rows | **NOT DONE** |
| T057 E10 — the incident reflects the outcome | unchecked | `evidence/E10-...txt`: this same incident is still `state=investigating` (from `evidence/E3-...txt`), never closed | **NOT DONE** |
| T058 confirm the alert resolved and closed the incident | unchecked | same as T057 — still `investigating` | **NOT DONE** |
| T059 reversion: confirm the guest is `running` | unchecked | not read | **NOT DONE** — live `pct status`, outside this audit |
| T060 close the window, record instant + summary | unchecked | `EVIDENCIA.md` §4 E1–E10 all blank | **NOT DONE** |
| T061 reject without a reason | unchecked | `evidence/R-...txt`: 0 rows | **NOT DONE** |
| T062 reject with a reason | unchecked | same file: 0 rows | **NOT DONE** |
| T063 confirm both decisions in the audit trail | unchecked | same file, second query: 0 rows | **NOT DONE** |
| T064 name resolution inside each monitoring container | unchecked | not read | **NOT DONE** — `backlog.md`'s own current entry carries the last known state (still broken) |
| T065 managed-secret sync | unchecked | not read | **NOT DONE** — same pattern, `backlog.md` entry still present |
| T066 model-gateway key, Verified | unchecked | not read | **NOT DONE** — same pattern, `backlog.md` entry still present |
| T067 write the backlog entry for each unfinished operational task | unchecked | all three present in the rewritten `backlog.md` | **DONE** |
| T068 mark stations not exercised by a pending operational task | unchecked | `EVIDENCIA.md` §5 field blank | **NOT DONE** |
| T069 fill `EVIDENCIA.md` station by station | unchecked | still the blank skeleton | **NOT DONE** |
| T070 confirm full-page 1920×1080 screenshot per screen-station | unchecked | `evidence/telas/` does not exist | **NOT DONE** |
| T071 confirm query + literal output per recording-station | unchecked | true for 4 of 8 stations; the other 4 correctly show `NOT COLLECTED`/zero because those stations have not happened | **NOT DONE** — cannot be closed until the whole loop has run |
| T072 secret sweep, text and screenshots | unchecked | not run | **PARTIAL, not done** — this audit ran the text half now (see Verification): the 8 evidence files and `EVIDENCIA.md` are clean against a structural pattern file and against the two real `.env` staging values themselves (boolean check, value never printed); the screenshot half has no artifact yet to sweep |
| T073 run owning features' acceptance + transversal against staging | unchecked | the 2026-08-23 deterministic run is on file, not this final one | **NOT DONE** |
| T074 one-sentence verdict + per-station verdicts | unchecked | `EVIDENCIA.md` top line and §7 blank | **NOT DONE** |
| T075 list every finding in `EVIDENCIA.md` §6 | unchecked | header row only | **NOT DONE** — a candidate finding is named in this report and in `controle.md`, not written into `EVIDENCIA.md` by this audit |
| T076 hand product-owned findings to the orchestrator, do not fix | unchecked | n/a | **NOT DONE** as a task closure — but honoured in spirit: the candidate finding is handed off, not touched |
| T077 write backlog entries for ownerless findings | unchecked | n/a | **NOT DONE** — depends on T075 |
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
| T089 full `make verify` | unchecked | not run | **NOT DONE, and here is why** — repository-wide (12223+ tests as of the last measured slot), reserved for the orchestrator on the final tree by standing instruction already recorded on 2026-08-23; this audit ran the equivalent tier gates for the surface it touched instead (see Verification) |
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
estate sync most likely happened *after* 09:11 UTC today, and this audit has
no later reading because it does not touch staging. The honest statement is
the one in the table above — not done, because the only evidence this audit
can cite still shows zero — not a claim that the estate is actually empty
right now.

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

### Fase 7–8 — the window and the rejection, proven not yet exercised (T045–T063)

Not "unattempted because this audit could not reach it" — **proven** not to
have happened, from the same real evidence collection: `evidence/E8-the-decision-its-author-and-its-instant-recorded.txt:15-32`
(`nothing-executed-unattended`) reads `0`, and both the `decision` and
`audit-of-the-decision` queries above it are `NOT COLLECTED` because no
`--approval` value exists yet. `evidence/E9-...txt` and
`evidence/R-...txt` show the same pattern: zero rows throughout. This is
exactly the state the dispatching instruction describes — the operator has
not yet typed `pct stop 122` or approved anything through the browser — and
this audit did not attempt to change that.

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
| Evidence secret sweep (text) | pattern-file `grep` across `evidence/*.txt` + `EVIDENCIA.md`, plus a boolean `grep -qF` of the two real `.env` staging values against the same files (value never printed) | clean on both |
| Product-boundary diff | `git diff --stat a0bfa74~1 aeb0dd6` outside the declared lane | zero files |

**Not run, and why:**

- `make verify` (full) — repository-wide (12223+ tests as of the last
  measured slot), reserved for the orchestrator on the final tree per the
  standing instruction `controle.md` already recorded on 2026-08-23; this
  audit is docs-and-tooling-only and ran the equivalent tier gates above
  instead.
- The deterministic transversal Playwright suite against staging
  (`spec_validation browser … transversal-rules.spec.ts`) — not re-run. The
  2026-08-23 result (45 passed, 7 skipped, `EXCEPTIONS` empty) is on file in
  `controle.md`; this audit changed nothing under `console/`, so there is no
  reason to expect drift, and re-running it means opening a new Playwright
  session against the exact staging target the operator is using live right
  now.
- Any live read against staging, the cluster, or the Alertmanager (Fase 1,
  2, 5, 6's screenshot half, 7, 8, 9, 10, 11) — not run, by instruction, to
  keep this audit entirely inside committed repository state and local
  gates.
- No test was written test-first in this audit, because nothing was found
  both (a) missing and (b) inside this feature's own implementable surface
  (`tools/demo_evidence/`, its test, the docs). Everything checked off was
  already built and already passing; everything left unchecked needs a live
  environment this audit does not touch. There was accordingly no red to
  confirm and no implementation phase — stated plainly rather than implied.

## Control reconciliation

**`specs_v7/080-incidente-fecha-o-laco/tasks.md`**: 32 of 92 boxes checked
(`T007`, `T017`–`T033`, `T043`, `T067`, `T080`–`T088`, `T090`–`T092`), each
independently verified in this audit against source, a passing test, or
already-committed evidence — not copied from `controle.md`'s prior claim. The
other 60 stay unchecked; none is silent, since the reason for each now lives
in `controle.md`'s per-task ledger (see below) and in the table above.

**`specs_v7/080-incidente-fecha-o-laco/controle.md`**: rewritten from a
range-grouped ledger (`T007–T016`, `T037–T044`, …) to a one-row-per-task
ledger, because several of those old ranges no longer had a single answer —
the read loop now has real database evidence for some of its stations and
none for others within what used to be one row. Added: a dated
"Segunda auditoria" section explaining why a second pass existed and what it
found; a table of the three commits that landed after the prior pass's
`aeb0dd6` cutoff, with what each touches; discoveries (h) through (j)
covering the real read-loop evidence, the one paragraph in
`specs_v7/CONFRONTO.md` that is now a step behind the tree, and the candidate
Prometheus finding; a reconfirmation note under "Gates rodados" recording
that this audit re-ran the same suite against the now-larger merged tree and
got identical counts. Nothing the 2026-08-23 pass got right was reverted —
every claim in it was independently re-checked against source before this
audit built on it, per this task's own rule against trusting a prior
session's report.

**`specs_v7/CONFRONTO.md`** and **`evidence/EVIDENCIA.md`**: read, not
written. Both declare in their own text that they are the orchestrator's to
maintain (measured directly by him, or filled in by whoever is present for
the live demonstration); this audit named the one place `CONFRONTO.md` is
now stale rather than editing a document outside this feature's own
boundary.
