# Deviations — 049 Proxmox Scenario Harness and Evaluation

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. Twenty-eight scenarios, not twenty-two

**Planned.** The primary story and the Definition of done both say twenty-two
scenarios.

**Done.** Twenty-eight, under `tests/synthetic/proxmox/`.

**Why.** The number in the narrative does not match the number the requirements
ask for. FR-002 enumerates the minimum set by name: six quorum, six storage,
seven guests, five backups — twenty-four — and then a fifth group, "host layer,
from real incidents", with four more. `tasks.md` T-012 to T-035 is the same
twenty-four, one task each, and Phase 3 to Phase 6 stop before the host layer.
Shipping twenty-two would have meant dropping two of the conditions FR-002 names.

**What this means for the definition of done.** "Twenty-two scenarios present,
scored, and baselined" is met and exceeded: twenty-eight are present, each scored
in four cells, all baselined in `tests/synthetic/proxmox/baseline.json`. The host
layer gets its own domain (`host`) rather than being distributed across the other
four, because the four domains are how the report stratifies and burying the P1
cascade under "quorum" would make it invisible in exactly the report it matters
most in.

---

## 2. The fixture suite runs the real investigation tools, and replays the model

**Planned.** The technical-context table says "the existing synthetic scenario
harness and evaluation suite, extended — not replaced", and acceptance scenario 1
asks that "the same inputs produce the same readings".

**Done.** `tests/harness/proxmox/` is a package beside the existing harness that
reuses its philosophy and none of its scenario loader. A hypervisor scenario
declares a recorded cluster state plus an overlay of API responses; `readings.py`
then runs the **shipped Proxmox investigation tools** — the real
`proxmox_quorum_status`, the real client, the real endpoint ring — over those
responses through `tests/support/proxmox.py`'s recorded transport. The
*response* half (the conclusion, the citations, the proposal) is a recorded
transcript per model and per ablation arm, declared in the scenario.

**Why.** The split follows what each half is for.

The readings are where a change to *this system* shows up, and the primary story
is exactly that case: "a contributor changes the quorum tool's synthesis … one
scenario now concludes the cluster is unquorate". That only fails if the tools
really run, so they do — `ReadingsPlan.must_report` is checked against what they
actually produced, and a tool that stops saying "quorum margin 0" fails the
scenario that declared it, by name, in the change that caused it.

The conclusion and the proposal need a model, and the pull-request path must
need nothing. The existing corpus solves this the same way — a hand-written
`transcript.json` per scenario — and NFR-003 is written for precisely this
arrangement: "scoring MUST be deterministic given a transcript". So the
transcripts are fixtures, four per scenario, and the scorer is a pure function of
(scenario, transcript, readings).

**What was not done, and is worth stating plainly.** These twenty-eight scenarios
do not drive the six-stage investigation pipeline the way `tests/synthetic/`'s
seven do. Doing that would have required a Proxmox backend for
`tests/harness/backends/`, an alert per scenario, and a transcript whose tool
calls satisfy each tool's argument schema and whose recorded responses match each
client's URL shapes — for twenty-eight scenarios, against a vendor whose fixture
support already exists in a different and better form. The measurement this
feature is *for* — action scoring, evidence-backed diagnosis, red herrings,
insufficient evidence — is unaffected by which of the two produces the
transcript.

---

## 3. The manifest is `proxmox-scenario.yml`, not `scenario.yml`

**Planned.** `tests/synthetic/proxmox/` for the fixture-backed suite.

**Done.** That location, with the declaration named `proxmox-scenario.yml`.

**Why.** `tests/harness/loader.py::discover_scenarios` walks
`tests/synthetic/**/scenario.yml` and validates every hit against the general
corpus schema. Twenty-eight documents it cannot read would have turned the whole
existing corpus into a load error. A different filename is invisible to that
walk and visible to this one, and neither loader has to learn about the other.

---

## 4. Two scenarios score "the evidence is insufficient" as the correct answer

**Planned.** FR-010 and SC-007 ask for the case; nothing says how many.

**Done.** `h2-a-script-warned-and-exited-zero` and
`h4-kernel-installed-and-never-booted` both declare `truth.insufficient`.

**Why h2.** It is the intended one: the postmortem's "silent degradation" finding
is a script that logged a warning and exited zero, which leaves no trace in any
reading the hypervisor API exposes. Every reading is green and green about a
different question.

**Why h4 as well.** FR-002 names "a kernel installed weeks ago and never booted"
in the host-layer set. No Proxmox *investigation* tool reports installed-but-
unbooted kernels — the client has `pending_updates`, and the nineteen shipped
tools do not surface it; the condition is a guardian detector's finding, taken
from node package state on a schedule. The choice was to invent a reading, drop
the scenario, or score it as what it is. Scoring it as insufficient is the
truthful option and a genuinely useful one: a model that confidently announces an
unbooted kernel from cluster, storage and guest readings has hallucinated it, and
the corpus now catches that. The scenario's `response.why` says so in as many
words.

---

## 5. Capability coverage is asserted twice, and the second assertion is the real one

**Planned.** T-039: "every feature 046 capability is exercised by at least one
scenario; a capability with none fails."

**Done.** Both `coverage.uncovered` (the requirement) and
`coverage.unjustified_claims` (its guard).

**Why.** A scenario's `exercises` list is a claim, and a coverage test over
claims is satisfied by editing a list. `touched()` recomputes what a scenario
genuinely brings into a score — the correct response's capability, a red
herring's temptation, or a capability one of the recorded runs proposed and was
scored for — and a claim that is not in that set fails. Five entries were removed
from the corpus during implementation because they did not survive it.

All thirteen writes are covered; `make proxmox-scenario-coverage` prints which
scenario scores each.

---

## 6. T-046 is met by a rehearsal set, not by the destructive scenarios

**Planned.** T-046: "Every feature 046 action exercised at least once against the
real cluster."

**Done.** `tests/e2e/proxmox/rehearsal.py` declares thirteen rehearsals, one per
declared write, each naming the target, the precondition, how the laboratory
arranges it, the reading that says it worked, and how the cluster is restored.
`tests/e2e/test_proxmox_laboratory.py` asserts the set is complete in both
directions — no write without a rehearsal, no rehearsal for a write this
deployment does not declare — and that assertion runs everywhere, with no cluster.

**Why.** Only eight of the twenty-eight scenarios are destructive, and between
them they ask for three of the thirteen writes. A scenario is about a *failure*;
several writes are correct responses to no failure in the corpus. Tying T-046 to
the scenario set would have meant either inventing five scenarios whose only
purpose was to name a capability, or leaving the requirement unmet.

**What is genuinely unmet.** Nothing here has been run against a live hypervisor,
because there is no laboratory cluster. The execution path is written and
exercised end to end against `RecordedLaboratory`; the two tests that need
hardware skip with a sentence naming `NINJASRE_PROXMOX_LABORATORY`. This is the
same gap feature 046's deviations record, now with the harness it was waiting
for.

---

## 7. The two model profiles are named by capability class, not by vendor

**Planned.** FR-017: "record which model produced the result, and MUST be
runnable against more than one".

**Done.** `hosted-frontier` and `self-hosted-compact`, in
`config/constants/hypervisor_scenarios.py`.

**Why.** A committed corpus that pinned a vendor's model identifier would be
stale within a release, and the number this suite publishes is about a class of
model rather than about one build of one. The suite records which profile
produced each result and reports both, which is what the requirement asks for;
which build a profile was recorded against belongs in the release note that
quotes the number.

---

## 8. Phase 2 was implemented before its tests

**Planned.** `CLAUDE.md`: "the failing test lands before the implementation, and
is confirmed failing."

**Done.** Phase 1 (harness extension) and Phases 7 to 9 were written test-first
with the failure confirmed. Phase 2 — the laboratory definition, the capture
mechanism, regeneration and the staleness check — had its implementation written
first and its tests immediately after, and the tests passed on the first run.

**Why it happened.** The capture mechanism's shape depended on what
`tests/support/proxmox.py`'s recorded transport actually exposed, and that was
established by writing against it.

**What was done about it.** Nothing retroactive; recording it here is the honest
option. The fifteen assertions in
`tests/synthetic/test_proxmox_fixtures_and_laboratory.py` passed on their first
run and were never observed red, so their value as regression tests is
established and their value as specifications of behaviour that did not yet
exist is not. Phases 3 to 9 went back to writing the test first.

---

## 9. The baseline stores verdicts; the artefact stores the evidence

**Planned.** FR-014 (committed baselines, reviewable changes) and FR-019 (every
scored run retains the transcript, the readings, the proposal and the reasoning).

**Done.** `ScenarioScore.to_record()` is the verdict — scenario, cell, mode, four
outcomes, missing evidence, red herrings followed — and is what
`baseline.json` holds. `ScenarioScore.to_artifact()` adds the transcript, the
readings and the reasoning, and is what `--json` emits and CI publishes.

**Why.** The first version stored everything and produced a seventeen-thousand-
line baseline. FR-014's whole mechanism is that moving a number is a diff
somebody reads, and nobody reads that diff. The split keeps the baseline at
eighteen hundred lines of verdicts and puts the evidence where FR-019 asks for
it: retrievable from the scored run.

---

## 10. Ablation and models are recorded arms, not switched runs

**Planned.** Phase 8: "Run with and without episodic memory and strategy
synthesis; report both."

**Done.** Every scenario declares four cells — two model profiles × two arms —
and the suite reports each. The corpus's numbers today: `hosted-frontier/full`
28/28, `hosted-frontier/no-memory` 25/28, `self-hosted-compact/full` 17/28 with
six harmful actions and two runs that could not finish, `self-hosted-compact/
no-memory` 10/28 with nine harmful.

**Why.** The existing `tests/harness/ablation/` package switches the real
machinery off around a live run, which needs a provider. On the pull-request path
there is none, so the arms are recorded the same way the transcripts are. What
the suite proves here is that the *reporting* separates the arms and that the
difference is visible; what it does not do is generate the difference from a live
memory subsystem. Feeding real ablation runs into this report is a matter of
writing the transcripts from them — `RecordedRun` is the same value either way.

---

## Appendix — where each success criterion is proven

| Criterion | Test |
|---|---|
| SC-001 | `tests/synthetic/test_proxmox_suite_and_gate.py::test_the_whole_suite_runs_from_fixtures_with_no_cluster` and `::test_the_suite_finishes_inside_its_declared_budget` |
| SC-002 | `…::test_the_suite_produces_identical_readings_and_identical_scores_twice` |
| SC-003 | `tests/synthetic/test_proxmox_action_scoring.py::test_a_right_diagnosis_from_the_wrong_evidence_does_not_score_as_correct` |
| SC-004 | `tests/synthetic/test_proxmox_suite_and_gate.py::test_the_corpus_contains_a_fixture_of_each_action_verdict`, with the four rules asserted individually in `test_proxmox_action_scoring.py` |
| SC-005 | `tests/synthetic/test_proxmox_action_scoring.py::test_acting_where_escalation_was_correct_scores_harmful` and `::test_acting_where_waiting_was_correct_scores_harmful` |
| SC-006 | `…::test_following_a_red_herring_is_penalised_explicitly` and `test_proxmox_suite_and_gate.py::test_a_red_herring_is_followed_somewhere_and_resisted_elsewhere` |
| SC-007 | `…::test_saying_the_evidence_is_insufficient_scores_correct_when_it_is`, its two converses, and `test_proxmox_suite_and_gate.py::test_the_corpus_contains_a_scenario_whose_correct_answer_is_i_cannot_tell` |
| SC-008 | `tests/synthetic/test_proxmox_suite_and_gate.py::test_a_seeded_regression_fails_naming_the_scenario_and_showing_the_readings` |
| SC-009 | `…::test_every_hypervisor_write_is_exercised_by_at_least_one_scenario`, guarded by `::test_a_scenario_cannot_claim_to_exercise_a_capability_nothing_touches` |
| SC-010 | `…::test_the_suite_reports_a_score_with_memory_and_without_it` |
| SC-011 | `…::test_the_suite_reports_each_model_it_ran_against` and `::test_a_model_that_could_not_finish_is_reported_apart_from_a_wrong_answer` |
| SC-012 | `tests/synthetic/test_proxmox_fixtures_and_laboratory.py::test_a_reading_the_shipped_tools_no_longer_produce_fails_loudly` and `::test_a_recorded_response_nothing_asks_for_any_more_fails_loudly` |
| SC-013 | `…::test_the_cluster_is_restored_between_destructive_scenarios`, `::test_a_scenario_that_leaves_the_cluster_unusable_is_recovered_from`, and `tests/e2e/test_proxmox_laboratory.py::test_a_scenario_that_leaves_the_cluster_unusable_stops_the_run` |

FR-011's aggregate property — an improvement that hides a harmful action is still
a regression — is proven twice: at the report, in
`test_proxmox_action_scoring.py::test_the_aggregate_cannot_hide_a_scenario_that_went_from_correct_to_harmful`,
and at the gate, in
`test_proxmox_suite_and_gate.py::test_an_improvement_that_hides_a_harmful_action_still_fails_the_gate`.

FR-004 and T-045 — the suite stating which scenarios were simulated and which
were real — are proven by
`tests/e2e/test_proxmox_laboratory.py::test_the_suite_runs_against_the_recorded_stand_in_and_says_it_was_simulated`.

T-046 is proven declaratively by
`…::test_every_hypervisor_write_has_a_laboratory_rehearsal` everywhere, and in
execution by `::test_every_hypervisor_write_is_run_once_against_the_real_cluster`,
which skips without a laboratory. See deviation 6.
