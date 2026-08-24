# Confrontation report — 080 O incidente fecha o laço

## Conclusion

This is the fourth pass over the same feature, layered on top of three
trustworthy prior passes rather than redoing them. Pass one found `tasks.md`
at zero of 92 despite most of the work already existing. Pass two confirmed
the whole-loop demo had run for real against staging and the hypervisor: CT122
stopped, the alert fired on its own, the incident opened, the investigation
recorded honestly (two verbatim upstream failures included), the report named
the right node, and the incident closed itself. Pass three closed the
publish cycle (T001, T003–T006) and the token-privilege question (T010) on
two new `EVIDENCIA.md` sections, and refused to round T002 up to green over
one named, real test failure.

**This pass exists because a second execution actually happened between pass
three and now, and it is read directly rather than taken on anyone's word.**
`evidence/laco-de-leitura-2026-08-24/` is a new directory: the read-loop
runbook run start to finish against a live `RestoreDrillStale` occurrence,
with six screenshots genuinely captured at 1920×1080 — the viewport the spec
declares, unlike the whole-loop demo's eleven captures, which stay at 1280 and
were correctly named wrong by pass three. `evidence/demo-2026-08-24/EVIDENCIA.md`
grew three sections: the visual gate's fix (closing the one real red pass
three refused to round up), the webhook's refusal half, and the three
operational tasks, now measured rather than unknown.

**Ten boxes move from open to done on that evidence, each confirmed by
opening the file rather than trusting the claim that it exists: T002, T014,
T015, T037, T039, T040, T042, T044, T068, T077.** T002 moves because the
exact test that blocked it (`test_the_untouched_baselines_still_match`) is
reported passing, and this pass did not stop at the prose: `git log
68e13d9..HEAD` shows three real commits — `fix(fixtures)`, `fix(layout)`,
`chore(visual): accept eight baselines` — and each was opened, and each
matches the narrative's own description of what it fixed, word for word, not
approximately. T014 and T015 close because both refusal probes and the
seventeen-alert listing with its stated reason are now written down, in two
files that agree. T037, T039, T040, T042, and T044 close because this pass
opened all six new screenshots directly and found the read loop's own E2, E4,
E5, and E7 stations genuinely captured, at the right width, showing the
correct content — including the run's own headline, which is a full sentence
in both of two investigations opened eleven and one minutes apart. T068
closes because the three operational tasks are now individually measured and
none of them is the reason any station went unexercised. T077 closes because
this pass wrote the backlog entries the finding list has been missing for two
audits.

**One of those ten required tracing code, not reading a screen, and it
overturned something three prior passes had repeated unchallenged.** The
"native_id carries `unknown` where the node should be" claim — read as the
probable cause of the incident header naming the wrong host — is wrong.
`integrations/proxmox/identity.py` builds a guest's identity as
`kind/cluster/creation-discriminator/vmid`, by explicit, documented design:
the node is deliberately excluded so that migrating a guest does not restart
its history, and `unknown` is the fallback for a missing *creation
timestamp*, not for a missing node. The node travels as a separate parent
field and is present. Read further, `platform/incidents/detection.py:298`
sets an alert-raised incident's title to the bare detector name — a
deliberate choice, the function's own docstring says why — and
`console/src/surfaces/screens/incident-detail.tsx` resolves the header's host
text from the incident's first subject, which is where the real mechanism
lives: an alert whose own exporter is local to its subject resolves
correctly, and an alert scraped by one exporter describing many guests
resolves to the exporter's host instead. Three backlog entries now carry
this — title, header, and the two-screens-disagree-on-cost finding — written
in the file's own form, with the wrong prior attribution corrected in place
rather than quietly dropped.

**Three items stay open by direct instruction, reconfirmed rather than
assumed.** T049: `e3-02-incidente.png`, opened again, still shows
`ProxmoxGuestStopped` as a title and `node pve02` three lines above
`node=pve01` — now traced to the same two source locations named above, so
the finding is a code fact, not only a screen fact. T053–T056 and
T061–T063: still not exercised, and the read loop's own `/decisions` and
incident-panel captures, opened directly, show the identical correct-empty
state the whole loop already showed — the catalogue's entire write surface is
three notification capabilities, none of which touches infrastructure.
T034–T036: the collector's before-the-demo dry run never happened, and — the
point this pass adds rather than repeats — that moment cannot be
retroactively supplied. Both demo executions have already run; a collector
run today would not be a "before."

**One box stays open on a genuinely ambiguous reading this pass declines to
settle unilaterally.** T065 (managed-secret sync) was already checked in
`tasks.md` when this pass began — the operator's own commit, on the operator's
own new evidence. That evidence states the state plainly (partially managed,
which secrets are hand-written and which are not) but stops short of anyone
affirmatively deciding to live with it, and `backlog.md` — untouched by this
pass on that specific item — still frames it as an open decision gap. Both
readings are defensible; this pass names the ambiguity rather than either
rubber-stamping or overturning a human's own contemporaneous call on a
genuine 50/50.

**Everything else is reconfirmed, not re-derived from memory.** The eleven
whole-loop screenshots, the runbooks, the collector and its 31 tests, the
confronto column, the backlog rewrite, the publish cycle, and the token
privilege finding were spot-checked against the current tree and found
unchanged from pass three's own careful reading. No REGRESSED item exists in
this feature.

## Table

Convention, unchanged from prior passes: **DONE** — the code, a test, or
already-committed evidence proves it; box checked. **PARTIAL** — real,
substantial work is on file, but the task's own bar is not fully met; box
left unchecked. **NOT DONE** — box left unchecked, with the reason stated.
No item in this feature has **REGRESSED**. Rows marked "(unchanged)" were
re-spot-checked against the current tree in this pass and found to still hold
exactly as pass three reported.

| Item | What the control claimed (before this pass) | What the code proved before this audit | Final status |
|---|---|---|---|
| T001 confirm wave merges + PASS, record tree commit | DONE | (unchanged) `EVIDENCIA.md`, 235 commits since `abbc418` on this tree, `CONFRONTO.md` all-green | **DONE** |
| T002 `make verify` before publish | PARTIAL — a real red on record inside a "Verde" summary | `EVIDENCIA.md` now reports the blocking test passing (33 passed on `console-visual`, 335+20 on `console-e2e`). This pass opened the three commits behind that claim (`0fc8b8c6` fixtures, `2149b44a` layout, `20397a68` baseline acceptance) and each matches the narrative's own description of the fix, not approximately | **DONE** |
| T003 publish via `make deploy-stg` without `COMPONENTS=` | DONE | (unchanged) | **DONE** |
| T004 wait for Argo `Synced + Healthy` | DONE | (unchanged) | **DONE** |
| T005 confirm service responds, separately from Argo | DONE | (unchanged) | **DONE** |
| T006 record digest + Argo state | DONE | (unchanged) | **DONE** |
| T007 discover org identifier | DONE | (unchanged) | **DONE** |
| T008 provider Verified, key from vault | DONE | (unchanged) | **DONE** |
| T009 Proxmox connected, `/resources` real | DONE | (unchanged) | **DONE** |
| T010 Proxmox token privilege | DONE | (unchanged) | **DONE** |
| T011 operator confirms victim at window open | DONE | (unchanged) | **DONE** |
| T012 victim `running`, confirmed | DONE | (unchanged) | **DONE** |
| T013 alert rule active + Alertmanager route | DONE | (unchanged) | **DONE** |
| T014 webhook refuses without credential | PARTIAL — accept half only | `laco-de-leitura-2026-08-24/EVIDENCIA.md` and `demo-2026-08-24/EVIDENCIA.md` both record two live probes: no `Authorization` → `401`; invented `Bearer` token → `401`; identical body in both cases; no incident opened in the probe window, confirmed against the database. Two independent write-ups agree word for word | **DONE** |
| T015 choose the already-firing alert, and why | NOT DONE — listing existed, reason did not | `laco-de-leitura-2026-08-24/EVIDENCIA.md`, "E1": seventeen active alerts, `RestoreDrillStale` chosen, the reason written ("a resolvable subject gives a richer E3 traversal... unlike `ContainerMemoryHigh` on guest 184, which the estate does not have") | **DONE** |
| T016 record the fitness table | NOT DONE | Original gabarito table still blank. All twelve items' substance now exists somewhere in prose (T014/T015 were the last two gaps), but no consolidated table was ever produced — the literal deliverable this task asks for | **PARTIAL — substance complete, artefact never produced** |
| T017–T026, T033 runbooks and skeleton | DONE | (unchanged) | **DONE** |
| T027–T032 the collector package | DONE | (unchanged) | **DONE** |
| T034 dry run against staging, pre-wave params | NOT DONE | `evidence/consultas/` and `evidence/consultas/000-partida.txt` still do not exist — reconfirmed directly (`ls` returns "No such file or directory"), not inherited. Both demo executions have now run; there is no "before" left to measure | **NOT DONE — the window this task needed has closed, not merely unused** |
| T035 confirm baseline values | NOT DONE | Consequence of T034 | **NOT DONE — same reason** |
| T036 record the red in `EVIDENCIA.md` §3 | NOT DONE | Table present, column still blank | **NOT DONE — same reason** |
| T037 run the read loop end to end | NOT DONE — the database chain ran, the browsing half never did | `laco-de-leitura-2026-08-24/EVIDENCIA.md`, opened directly: the six-station browser walkthrough against the already-active alert chosen in T015, explicitly declared non-destructive ("nothing was torn down, nothing was emitted by hand") | **DONE** |
| T038 E2/E3 screenshots (read loop) | NOT DONE — no screenshot existed for this run | `e3-01-incidentes.png`/`e3-02-detalhe.png`, opened directly: three of the task's own four checks hold (clean URL, no unrenderable panel, subject correctly resolved to `pve02`, the node this alert is genuinely about) — the fourth, a legible title, does not: the incident shows `RestoreDrillStale`, not a sentence, confirmed in source at `platform/incidents/detection.py:298` | **PARTIAL — real screenshots now exist; the title criterion genuinely fails, traced to source** |
| T039 E4 screenshot (read loop) | NOT DONE | `e4-01-run-primeiro.png`/`e4-02-run-setimo.png`, opened directly: real transcript (`prometheus_active_alerts` succeeded, `search_knowledge_base`/`changes_in_window` failed with the real upstream reason, one call reproduced a `400` from an empty `start` parameter), cost per turn in its own table, `COMPLETED` status not a live-run control, "what this investigation touched" filled for the first run | **DONE** |
| T040 E5 screenshot (read loop) | NOT DONE | Same two screenshots: the *run's* own headline — a different field from the incident's title — is a full sentence in both captures ("The weekly restore drill cron jobs on node pve02 exceeded their maximum scheduled execution window without completing successfully", and a differently-worded but equally complete sentence on the seventh run), the report renders as a document, no raw `**`/`##` visible as text | **DONE** |
| T041 tools match connected integrations (read loop) | NOT DONE | No `/agent` screenshot and no tool-selection log grep exist for this run — the transcript alone (T039's evidence) does not stand in for the dedicated evidence this task asks for | **NOT DONE** (unchanged) |
| T042 E7 screenshots (read loop) | NOT DONE | `e7-01-decisoes.png` (the actual `/decisions` screen: "Nothing is waiting on a decision... the active rule asks for approval for actions at write_reversible and above") and `e3-02-detalhe.png`'s own "Proposed action" panel ("Nothing proposed yet"), both opened directly — the correct, declared-acceptable empty state for a deployment whose catalogue proposes nothing, captured rather than merely asserted | **DONE** |
| T043 run the collector, attach per-station output | DONE | (unchanged) | **DONE** |
| T044 repeat the read loop, compare | NOT DONE | Seven natural investigations of the same incident across six and a half hours; the first and seventh opened directly this pass show the same transcript-block shape and a sentence-form headline both times (different sentences, both correct) — a stronger repeatability signal than two manual runs would have been. One un-named variance: the "what this investigation touched" panel is filled on the first run and empty on the seventh, and the evidence file's "same shape" claim does not call this out specifically | **DONE — core repeatability claim holds; one small named gap in the write-up itself, not in the underlying evidence** |
| T045–T048 window open through delivery | DONE | (unchanged) | **DONE** |
| T049 E3 — incident opens legible, subject resolved | NOT DONE | `e3-02-incidente.png`, opened again: title `ProxmoxGuestStopped`, header "node pve02" three lines above the alert body's "node=pve01" — now traced to source (`platform/incidents/detection.py:298` for the title; `console/src/surfaces/screens/incident-detail.tsx:141-153,256-261` for the header, which resolves the incident's first subject and shows *its* kind/name) rather than only observed on screen | **NOT DONE, unchanged — reconfirmed against source, not only against the screenshot** |
| T050 E4 — investigation records (whole loop) | DONE | (unchanged) | **DONE** |
| T051 E5 — report is legible (whole loop) | DONE | (unchanged) | **DONE** |
| T052 E6 — tools match what is connected (whole loop) | DONE | (unchanged) | **DONE** |
| T053 E7 — proposal waits with a rollback plan | NOT DONE — not exercised, product-scope | Unchanged verdict; this pass's own evidence (the read loop's parallel empty state, T042) reinforces the same catalogue-wide fact rather than changing it | **NOT DONE — not exercised, product-scope** (unchanged) |
| T054–T056, T061–T063 approve/execute/reject | NOT DONE — not exercised, product-scope | Unchanged; no new proposal appeared in either execution this pass read | **NOT DONE** (unchanged) |
| T057–T060 E10, close, reversion, window close | DONE | (unchanged) | **DONE** |
| T064 name resolution inside each monitoring container | NOT DONE | `EVIDENCIA.md`, new section: Alertmanager and Gatus resolve the deployment's domain; Prometheus does not, and does not need to — it scrapes exporters and evaluates rules, and Alertmanager (which does resolve) is what delivers the webhook | **DONE — verified and registered, including the one that does not resolve and why it does not block anything today** |
| T065 managed-secret sync | NOT DONE | `EVIDENCIA.md`: database connection syncs via Crossplane; encryption key and local account are hand-written; "no decision registered anywhere to live with this... which is what this task exists to end." Already checked in `tasks.md` before this pass began, by the operator, on this text | **Left checked, flagged rather than settled — see Conclusion. `backlog.md`'s own unedited entry on this item still reads it as an open decision gap** |
| T066 model-gateway key, Verified | NOT DONE | `EVIDENCIA.md`, with a fresh screenshot citation: Google Gemini, Verified, the provider that drove every investigation in both traversals | **DONE** |
| T067 backlog entry for each unfinished operational task | DONE | (unchanged) | **DONE** |
| T068 mark stations blocked by a pending operational task | NOT DONE — the task's own premise did not hold | With all three operational tasks now measured, "Estações NÃO exercidas, e por quê" attributes E7–E9 exclusively to the catalogue's write-capability gap — none of the three operational tasks is named as a blocker for any station. The premise now has a real, checked answer: zero | **DONE** |
| T069 fill `EVIDENCIA.md` station by station | DONE | (unchanged, in a document of its own) | **DONE** |
| T070 confirm full-page 1920×1080 screenshots | NOT DONE — all eleven at 1280px | The six new read-loop screenshots are genuinely 1920px wide, confirmed with `file`, not presumed. The eleven whole-loop screenshots remain at 1280px, unchanged | **PARTIAL — half the picture now complies; the task's own "every station that is a screen" bar is not met while the other half does not** |
| T071 confirm query + literal output per recording station | NOT DONE | The collector has never run against either headline run of this wave — not the whole loop's `run=d393d5d0…`, and not the read loop's fresh `inc_5c836cbc6d57e28a` either, confirmed by the continued absence of `evidence/consultas/` | **NOT DONE** (unchanged) |
| T072 secret sweep, text and screenshots | DONE | (unchanged) | **DONE** |
| T073 run owning-feature acceptance + transversal against staging | NOT DONE | Neither new evidence directory contains a staging acceptance run; last measurement on file remains 2026-08-23 | **NOT DONE** (unchanged, reconfirmed absent by direct search of both new files) |
| T074 one-sentence verdict + per-station verdicts at the top | NOT DONE | `evidence/EVIDENCIA.md` (the literal gabarito this task names) remains entirely blank; the narrative documents cover the per-station half in prose but neither opens with a single verdict sentence | **NOT DONE** (unchanged) |
| T075 list every finding in `EVIDENCIA.md` §6 | DONE | (unchanged, in a document of its own) | **DONE** |
| T076 hand product-owned findings to the orchestrator, don't fix | DONE | (unchanged) | **DONE** |
| T077 write backlog entries for ownerless findings | NOT DONE | Three new `backlog.md` entries, in the file's established form, for the title, the header-host, and the two-screens-disagree-on-cost findings. A fourth prior finding — the native_id "unknown" segment as the header's probable cause — is not written up as a defect because it is not one: traced to `integrations/proxmox/identity.py`, `unknown` is a documented fallback for a missing creation timestamp, not for a missing node, and the correction is written into the header-host entry rather than silently dropped | **DONE** |
| T078 re-run and replace evidence after a repair | NOT DONE | No repair happened against a finding this feature's own demo produced (the two visual-gate fixes behind T002 were found by a different process and are outside this feature's findings list) | **NOT DONE — not applicable** (unchanged) |
| T079 per-feature verifier verdicts in `CONFRONTO.md` | NOT DONE | `CONFRONTO.md`'s own header reserves this to the orchestrator | **NOT DONE, deliberately** (unchanged) |
| T080–T083 the confronto column | DONE | (unchanged) | **DONE** |
| T084–T088 the backlog rewrite | DONE | (unchanged); this pass's own two corrections to `backlog.md` (the resolver entry, the closing entry) keep the file's own accuracy bar rather than contradicting T085–T087 | **DONE** |
| T089 full `make verify` | NOT DONE | Never run as one command. This pass re-ran the static/architecture slice itself, fresh, on its own tree: collector 31/31, `tests/unit/tools`+`tests/architecture` 752/752 (identical to pass three, zero regressions), raw-SQL strict test 53/53, lint/format/mypy clean, all guard scripts clean, all 7 import contracts kept | **NOT DONE — reconfirmed with fresh, independently-run evidence for the slice this pass could safely run** |
| T090 no product file touched | DONE | (unchanged) | **DONE** |
| T091 write this feature's `controle.md` | DONE | Extended again in this pass with a fourth dated section | **DONE** |
| T092 report to the orchestrator | DONE | This report | **DONE** |

## Evidence and corrections

Full per-item evidence for every task pass three already closed lives in that
pass's own report text, above and in `controle.md`; it was re-spot-checked in
this pass (see Verification) and is not reproduced paragraph by paragraph
here to avoid duplicating a record that is already accurate. What follows is
this pass's own evidence for the items that moved, stayed open by
instruction, or needed a correction.

### T002 — the visual gate, verified past the prose

`evidence/demo-2026-08-24/EVIDENCIA.md`, "O portão visual, depois da revisão
das baselines": `test_the_untouched_baselines_still_match` now passes;
`make console-visual` exit 0, 33 passed; `make console-e2e` exit 0, 335
(behaviour) + 20 (first-day). Fourteen baselines had diverged; six were
reviewed image by image, two real regressions were found and fixed in that
review, eight were accepted afterward.

This pass did not stop at reading that paragraph. `git log 68e13d9..HEAD`
names the real commits, and each was opened:

- `0fc8b8c6f46c` `fix(fixtures): give the two hand-triggered runs the
  sentence a real one has` — `fixtures/scenarios/populated/run-detail.json`,
  `fixtures/scenarios/populated/runs.json`. Matches the narrative's "a
  headline became a label" finding exactly: the synthesiser builds an
  objective from the trigger word when an entry declares no headline, and a
  hand-triggered run carries an objective this dataset never had.
- `2149b44a8ebc` `fix(layout): let a page say its own name on a narrow
  screen` — `console/src/components/layout.tsx`. Matches "the page name
  truncated at 320px" exactly: the heading carried `truncate` with no
  tooltip fallback for an ordinary title, and the actions crowded the title
  at every width instead of stacking below a breakpoint.
- `20397a68c026` `chore(visual): accept eight baselines, reviewed image by
  image` — names the same four screen categories the narrative names
  (`shell-*`, `machine-tokens`, `resources-320`/`gallery-320`), and names the
  same one defect found and *not* fixed (the 320px resources table drawing
  seven columns as `RESOURKINDZONE`) that the narrative also calls
  pre-existing and out of scope.

All three commits are by the same author as the evidence files, none touches
`specs_v7/080-incidente-fecha-o-laco/`, and none is part of this feature's
own diff (confirmed by T090's own sweep, unchanged). `make console-visual`
and `make console-e2e` were not re-executed by this pass — the same
resource-contention reasoning pass three already gave, with 23 agent
worktrees still present on the host at read time — so this pass's
confidence rests on independently reading the commits behind the claim,
not on repeating the gate.

### T014 — the refusal half, in two independent write-ups

`evidence/laco-de-leitura-2026-08-24/EVIDENCIA.md`, "E2 — a entrega, e a
recusa," and `evidence/demo-2026-08-24/EVIDENCIA.md`, "T014 — o webhook
recusa o que não se autentica," both read directly: two probes against
`POST /webhooks/alertmanager` with a valid alert body — no `Authorization`
header → `401`; `Authorization: Bearer` with an invented token → `401`;
identical response body in both
(`{"error":{"type":"unverified","message":"this alertmanager webhook did
not verify against any configured route"}}`). Both files independently note
the identical message is deliberate — a different message per case would
tell a probing party which half it got right. Both files independently
confirm no incident was opened in the probe window.

### T015 — the choice, and the reason, both on record

`evidence/laco-de-leitura-2026-08-24/EVIDENCIA.md`, "E1 — o alerta, e por
que este": seventeen alerts active in Alertmanager at read time;
`RestoreDrillStale` chosen (severity `critical`, started
`2026-08-24T11:08:43Z`, target `192.168.68.159:9100`), with the reason
written in full: the runbook's own criterion is that an alert whose subject
the estate already knows gives a richer E3 traversal, unlike
`ContainerMemoryHigh` on guest 184, which the estate does not have and which
the resources screen already reports correctly as "alert for something not
here."

### T037, T038, T039, T040, T042 — the read loop, opened screenshot by screenshot

All six screenshots in `evidence/laco-de-leitura-2026-08-24/` were opened
directly in this pass, not inferred from filenames:

- `e2-01-alert-intake.png` — `/settings/alert-intake`: the `alertmanager`
  receiver, `Receiving`, last delivery ten minutes before capture,
  `ACCEPTED`, 279 deliveries that week, authenticated with a named delivery
  token.
- `e3-01-incidentes.png` — `/incidents`: fourteen rows, all real, including
  three separate `RestoreDrillStale` rows at different ages and subject
  counts — consistent with the alert re-firing and re-delivering rather than
  a single static list.
- `e3-02-detalhe.png` — the chosen incident's detail: title
  `RestoreDrillStale` (fails the legible-title criterion, see below), chip
  `Investigating` + `Investigation running` (not `Unknown`), header "started
  7 hours ago · zone Unplaced · node pve02" (correct — this alert's own
  subject is the node), seven `Alert received` entries in the transcript
  spanning 11:08 AM to 5:38 PM, each authenticated, "Proposed action:
  Nothing proposed yet," "Evidence trail: Every query, answer and token
  spent, in order."
- `e4-01-run-primeiro.png` / `e4-02-run-setimo.png` — the first and seventh
  investigation's own run detail: real capability calls with real results
  (`prometheus_active_alerts` succeeded; `search_knowledge_base` failed,
  "not configured for this deployment"; `changes_in_window`/
  `recall_similar_incidents` failed with the real reason; the fourth call
  failed with a verbatim Prometheus `400` on an empty `start` parameter on
  the seventh run — the same failure shape a prior audit flagged as an
  unreproduced candidate finding, now reproduced); cost-per-turn table (five
  turns each); status `COMPLETED`; headline a full sentence in both
  ("...exceeded their maximum scheduled execution window without completing
  successfully" / "...exceeded their maximum healthy execution window
  without a successful run" — different wording, both correct sentences);
  report rendered with bold section labels, no raw markdown syntax visible
  as text; "What this investigation touched" filled (incident + resource)
  on the first run, empty ("Nothing linked yet") on the seventh — the one
  named, un-explained variance across the two captures.
- `e7-01-decisoes.png` — `/decisions`, Actions tab: "Nothing is waiting on a
  decision... The active rule asks for approval for actions at
  write_reversible and above."

T038's own four checks were scored individually: clean URL, no unrenderable
panel, and a correctly-resolved subject all hold; a legible title does not —
the incident shows `RestoreDrillStale`, the bare detector name, not a
sentence, traced to source below. T039, T040, and T042 hold in full — T040
in particular checks the *run's* own title, a different field from T038's
incident title, and that field is genuinely a sentence both times.

### The title and the header, traced to source — and a prior finding corrected

Two mechanisms, read directly rather than inferred a second time from a
screen:

**The incident's title.** `platform/incidents/detection.py:296-303`
(`_raise_for`):

```python
return IncidentRaise(
    correlation_key=correlation_key,
    title=f"{detector.name} is flapping" if flapping else detector.name,
    ...
)
```

The function's own docstring: "The title is the detector's name and the
summary counts the subjects, which is what makes one incident about fifty
resources readable in a list." A deliberate choice, with a real reason — an
incident can absorb many findings under one name, and a sentence composed
for one subject would not generalise to fifty — and a real cost: the
investigation attached to the same incident writes a genuine sentence every
time (confirmed in both `e4-01`/`e4-02` above), and it never reaches the
incident's own title field.

**The incident's header.** `console/src/surfaces/screens/incident-detail.tsx:141-153,256-261`:
the header's host text is built from `incident.subjects[0]`'s own resolved
estate resource — `subjectKind` and `subjectName` read straight off that
resource's `kind`/`display_name`. For `RestoreDrillStale`, that subject is
correctly the node itself, because the alert's own metric is scraped by the
node's own exporter — the two coincide by construction. For
`ProxmoxGuestStopped` (the whole-loop demo, pass two and three's own
finding, reconfirmed here), the subject resolves to the exporter's own host
instead of the guest, because Proxmox's guest-power metric is scraped by one
exporter describing every guest in the cluster, and whatever resolves
`subjects[0]` for that alert lands on the exporter's node rather than on the
guest.

**A correction to what three prior passes carried forward unchallenged.**
The earlier reading attributed the wrong-host header to a Proxmox guest's
`native_id` carrying a literal `unknown` where a node segment should be
(`lxc/HAL9000/unknown/122`), naming it the probable cause. Read at the
source, `integrations/proxmox/identity.py:32-58`:

```python
NO_DISCRIMINATOR: Final = "unknown"

def guest_identity(cluster: str, kind: str, vmid: int, *, created_at: str) -> str:
    """Return a guest's identity: cluster, kind, VMID, and when it was created."""
    return f"{kind}/{cluster}/{created_at or NO_DISCRIMINATOR}/{vmid}"
```

The module's own docstring: "The node is never part of a guest's identity.
Migration is a normal operation, and a guest that changed identity on
migration would be a guest whose history restarts every time the cluster
balances itself. The node is the *parent*." The third segment of
`lxc/HAL9000/unknown/122` is a missing *creation-timestamp discriminator*,
not a missing node — the node is carried separately, as `parent_native_id`,
and is present. This is deliberate, documented design, not a bug, and it is
not the cause of the header issue. The earlier attribution is corrected in
the new `backlog.md` entry rather than repeated a fourth time.

### T044 — repeatability, from seven natural executions

`e4-01-run-primeiro.png` (11:08 AM) and `e4-02-run-setimo.png` (5:38 PM,
same day) are the first and seventh independent investigations of the same
incident, seven Alertmanager re-deliveries over six and a half hours. Both
opened directly: same transcript-block count, same call-and-result shape,
sentence-form headline in both (different sentences, both grammatically
complete and factually correct). This is a stronger repeatability signal
than manually re-running the runbook twice would have produced — seven
independent trials, not two — and it directly reproduces a candidate finding
(the `prometheus_metric_statistics` `400` on an empty `start` parameter) a
prior audit had flagged as seen once and not repeated.

One variance exists and is not named in `laco-de-leitura-2026-08-24/EVIDENCIA.md`'s
own "same shape" claim: "What this investigation touched" is filled on the
first run and reads "Nothing linked yet" on the seventh. It does not disturb
the core repeatability claim (the shape and the sentence-headline pattern
both hold), so T044 is credited, with this specific gap named rather than
smoothed over.

### T068 — the operational tasks measured, and none of them the reason

`evidence/demo-2026-08-24/EVIDENCIA.md`, "As três tarefas operacionais,
medidas": name resolution works from the Alertmanager and Gatus containers,
fails from Prometheus (which does not need to reach this deployment,
explaining why delivery still works); secrets are partially managed
(database connection via Crossplane syncs; encryption key and local account
are hand-written); the model gateway (Google Gemini) reads Verified and
drove every investigation in both traversals. Cross-read against "Estações
NÃO exercidas, e por quê," which attributes E7–E9's non-exercise exclusively
to the catalogue's write-capability gap — none of the three operational
tasks is cited anywhere as the reason a station went unexercised. T068's own
premise ("register which stations depended on an unfinished operational
task") now has a checked, real answer: none did.

**T065's own status is flagged, not settled, by this pass.** Its box was
already checked in `tasks.md` before this pass began — the operator's own
edit, on the operator's own new text. That text states the real state
(partially managed) but reads more like an observation that no decision was
ever made than a decision now recorded; `backlog.md`'s own unedited entry on
this item ("What this product needs is a decision recorded either way")
still treats it as open. Both readings are genuinely defensible. This pass
leaves the box as the operator left it rather than overturning a
contemporaneous human judgment call on a real 50/50, and names the ambiguity
here instead.

### T077 — three findings written up, one correction folded in

`backlog.md` gained three entries in the file's established form (what
happens today / why it is not simply fixed / how it would be judged): the
incident-title finding (with the source trace above), the header-host
finding (with the source trace above, including the correction), and the
observation that a single run's cost reads `Not recorded` on the incident
panel and a real dollar-and-token breakdown on the run's own screen — this
last one at the observed-behaviour level, since this pass did not trace the
two screens' code to the exact divergence.

Two further edits to `backlog.md`, made for accuracy rather than requested
by name: the monitoring-container entry claimed universal resolver failure
("every name... returns nothing from inside them"), which T064's own fresh
measurement falsifies for two of the three containers — rewritten to the
real, more precise state. And the file's closing entry, "No deployment has
been observed acting on its own diagnosis," described the whole loop as
never having been attempted — false since the 2026-08-24 demo — rewritten to
state what was actually watched (seven of ten stations closing on their
own) and what remains missing (a capability that acts on infrastructure,
not an environment gap).

### T034–T036 — the window is closed, not merely unused

`evidence/consultas/` and `evidence/consultas/000-partida.txt` do not exist
— checked directly by this pass (`ls` returns "No such file or directory"),
not inherited from a prior report. The collector's dry run was supposed to
land *before* either demo execution; both have now run. Running the
collector today, against any run, would measure an "after" and could not
supply the "before" T035 asks for. These three stay open because the moment
they needed has passed, not because the evidence is merely missing and
recoverable.

### T049, T053–T056, T061–T063 — reconfirmed by direct instruction

T049: `e3-02-incidente.png` (the whole loop, CT122), opened again this pass:
title `ProxmoxGuestStopped`, header "node pve02" three lines above the alert
body's "node=pve01," both visible without scrolling. Now backed by the same
source trace given above rather than only a screen reading. T053–T056 and
T061–T063: `e7-01-decisoes.png` and `e3-02-detalhe.png` (the read loop's own
captures, a second, independent occurrence) show the identical correct-empty
state the whole loop's own captures already showed. The verdict does not
change; the evidence base for it doubles.

## Verification

Gates actually run in this pass, on the current tree (this worktree
recovered to `8837163` via `git merge --ff-only master`, then this pass's
own commit `1df87db` on top of that):

| Gate | Command | Result |
|---|---|---|
| Collector unit tests | `uv run pytest tests/unit/tools/test_demo_evidence.py -q` | **31 passed in 0.22s** |
| Tools + architecture suite | `uv run pytest tests/unit/tools tests/architecture -q` | **752 passed, 3 warnings in 47.41s** — identical to pass three, zero regressions |
| Raw-SQL guard, strict test | `uv run pytest tests/unit/tools/test_check_raw_sql.py -q` | **53 passed in 4.04s** |
| Lint | `uv run ruff check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | All checks passed! |
| Format | `uv run ruff format --check tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | 5 files already formatted |
| Types | `uv run mypy tools/demo_evidence tests/unit/tools/test_demo_evidence.py` | Success: no issues found in 5 source files |
| Constants / direct-credential / protocol-body / dependency / raw-SQL guards | `uv run python tools/check_*.py` | exit 0, all five |
| Docs-drift guard | `uv run python -m tools.check_docs_drift` | exit 0 — run twice, before and after the `backlog.md` edits |
| Documented examples | `uv run python -m tools.test_doc_examples` | 29 documented example(s) check out |
| Integration-catalogue parity | `uv run python -m tools.verify_integrations` | 15 integration(s) at full parity |
| Import contracts | `PYTHONPATH=$(pwd) uv run lint-imports` | Contracts: 7 kept, 0 broken |
| Forbidden-pattern sweep on `backlog.md` | `grep -nE "FR-[0-9]\|SC-[0-9]\|specs_v[0-9]\|Article [IVXLC]\|constitution\|080-incidente\|feature 0[0-9]{2}" backlog.md` | exit 1 — zero matches |
| Screenshot dimensions, read loop | `file` on all six PNGs in `evidence/laco-de-leitura-2026-08-24/` | all `1920 x N` (1080–2314) |
| Screenshots opened directly | all six read-loop PNGs; `e3-02-incidente.png`, `e7-01-incidente-apos.png`, `e10-02-decisoes.png` re-opened from the whole loop for the T049/T053 cross-check | all opened and read in this pass; contents match what is claimed above |
| Commits behind the T002 claim | `git log 68e13d9..HEAD`, then `git show --stat` on `0fc8b8c6`, `2149b44a`, `20397a68` | all three real, correctly scoped outside this feature, matching the narrative |
| Source trace for the title/header findings | `codegraph_explore` + direct read of `platform/incidents/detection.py`, `platform/observation/bridge/alerts.py`, `console/src/surfaces/screens/incident-detail.tsx`, `integrations/proxmox/identity.py` | mechanisms confirmed as described above; the native_id attribution corrected |

**Not run, and why:**

- `make verify` (full, single command) — never run, by anyone, on this
  tree. This pass ran the static/architecture slice above instead, fresh,
  as the responsibly-scoped substitute; T089 stays open rather than
  credited from that slice alone.
- The general pytest suite beyond `tests/unit/tools`+`tests/architecture`,
  `console-check`, and `console-visual` — not attempted. 23 agent worktrees
  were present on the host at read time (`ls .claude/worktrees | wc -l`),
  and `console-visual`'s true state is independently corroborated by
  reading the real commits behind it (see T002 evidence above) rather than
  by re-running a multi-thousand-test gate that pass two's own account says
  "always died at the same point" in the background.
- Any live read against staging, the cluster, the hypervisor, or
  Alertmanager — not run, by explicit instruction not to touch any of them.
  Every claim in this report comes from reading the two `EVIDENCIA.md`
  files, their seventeen screenshots (six new, opened in full; eleven prior,
  re-opened where a specific claim needed a second, independent look), and
  the source tree.
- No test was written test-first in this pass. Nothing was found both
  missing and inside this feature's own implementable surface
  (`tools/demo_evidence/`, its test, the docs, `backlog.md`). Every task
  this pass moved to done was already proven by already-committed evidence;
  every task left open needs either a live environment this pass does not
  touch, or an orchestrator-level judgment (T077's ownership question for
  what remains, T079's cross-feature verdicts, T065's decision-versus-
  observation reading) this pass does not make unilaterally.

## Control reconciliation

**`specs_v7/080-incidente-fecha-o-laco/tasks.md`**: moved from 61 of 92 to
**71 of 92** boxes checked. Ten moved from open to done — T002, T014, T015,
T037, T039, T040, T042, T044, T068, T077 — each on evidence opened directly
in this pass (a screenshot, a commit, or a source file), never on the
narrative's word alone. T038, T016, and T070 were investigated in the same
depth and deliberately left **partial**: real, substantial evidence now
exists for each, and each still fails one part of its own stated bar. T065
was left exactly as the operator's own prior commit set it, with the
ambiguity named rather than resolved either way. The other twenty stay
exactly as pass three left them, each re-examined rather than merely
re-stated: T034–T036, T049, T053–T056, and T061–T063 by explicit
instruction, T041/T071/T073/T074/T078/T079/T089 by a fresh check that found
no new evidence closing them, and the remainder by a spot-check against the
current tree that found no drift in either direction.

**`specs_v7/080-incidente-fecha-o-laco/controle.md`**: a new "Quarta
auditoria" section was added, following the file's own established pattern
of layering a new dated pass on top of prior ones — the "Segunda auditoria"
and "Terceira auditoria" text is untouched. One factual slip made while
drafting the new section (calling the whole loop's `e3-02-incidente.png` by
the read loop's own filename, `e3-02-detalhe.png`) was caught and corrected
in place before this report was written, rather than left for a fifth pass
to find.

**`backlog.md`**: three new entries (incident title, incident header naming
the wrong host, cost reported two ways), one entry rewritten in full (the
loop-never-attempted closing entry, now describing what was actually
watched and what specifically remains missing), and one entry corrected for
accuracy (the monitoring-container resolver claim, now naming which
container resolves and which does not, rather than claiming universal
failure). All five checked against the file's own forbidden-pattern rule
and against `tools.check_docs_drift`, both clean.

**`specs_v7/CONFRONTO.md`** and **`evidence/EVIDENCIA.md`** (the original
gabarito), **and both dated evidence directories**
(`evidence/demo-2026-08-24/`, `evidence/laco-de-leitura-2026-08-24/`): all
read, none written. `CONFRONTO.md` for the reason pass two and three already
gave — it is measured by the orchestrator, not edited by a feature
confrontation, and its self-contradiction (one section still says "não
executado," a later section narrates the whole demo) is named again here
rather than fixed. `evidence/EVIDENCIA.md` remains the untouched, blank
gabarito the narrative documents supersede in substance. The two dated
evidence directories are left exactly as their traversals produced them —
including the achado-3 misattribution inside `demo-2026-08-24/EVIDENCIA.md`
and `achados.md`, which this report corrects in `backlog.md` and here rather
than by editing someone else's dated record of what was believed at the
time.
