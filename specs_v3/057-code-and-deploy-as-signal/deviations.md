# Deviations — 057 Code and deploy as signal

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each Definition-of-done item is proven

| Item | Where it is proven |
|---|---|
| 1. A change source answers "what changed between T−N and T" with author, instant and paths | `tests/unit/platform/changes/test_infra_apply_source.py::TestWhatItReads` (nine assertions) against `tests/corpus/operational/.infra-state/`. **Against the real repository it is not proven** — see §7 |
| 2. A change correlates through path → component → workload, and temporal-only proximity does not produce `MANAGES_RESOURCE` | `tests/unit/platform/changes/test_correlation.py::TestStrength::test_the_same_change_against_a_disk_that_filled_up_is_temporal_only` and `::test_proximity_in_time_alone_never_produces_the_strong_verdict` |
| 3. Correlation strength appears in the report; `WINDOW_ONLY` is labelled as temporal coincidence | `tests/unit/platform/changes/test_correlation.py::TestStrength::test_a_window_only_correlation_says_it_is_a_coincidence_in_words`, `tests/contract/capabilities/test_changes_in_window.py::TestWhatComesBack::test_a_correlated_change_comes_back_with_its_strength`, `tests/synthetic/test_change_correlation_value_scenario.py::TestTheApplyThatCausedIt::test_the_unrelated_apply_is_still_reported_and_is_labelled_a_coincidence` |
| 4. A quiet resource states "no change touched this resource" as evidence, not silence | `tests/unit/platform/changes/test_change_inquiry.py::TestTheNegative` (five assertions), `tests/contract/capabilities/test_changes_in_window.py::TestWhatComesBack::test_a_quiet_resource_produces_evidence_rather_than_an_empty_answer`, `tests/synthetic/test_change_correlation_value_scenario.py::TestTheQuietResource` |
| 5. A credential-shaped commit message is redacted with the rule named | `tests/unit/platform/changes/test_change_screening.py::test_the_rule_that_fired_is_named_on_the_change` and `::test_the_source_screens_before_anything_can_read_the_change`; the vendor route in `tests/unit/integrations/test_git_host_change_source.py::test_a_credential_in_a_commit_message_is_redacted_on_this_route_too` |

<!-- proof: tests/unit/platform/changes/test_infra_apply_source.py::test_a_revision_nobody_applied_is_marked_as_one -->
<!-- proof: tests/unit/platform/changes/test_correlation.py::test_the_same_change_against_a_disk_that_filled_up_is_temporal_only -->
<!-- proof: tests/unit/platform/changes/test_correlation.py::test_a_window_only_correlation_says_it_is_a_coincidence_in_words -->
<!-- proof: tests/unit/platform/changes/test_change_inquiry.py::test_a_quiet_resource_gets_a_sentence_naming_the_sources_and_the_window -->
<!-- proof: tests/unit/platform/changes/test_change_screening.py::test_the_rule_that_fired_is_named_on_the_change -->
<!-- proof: tests/unit/integrations/test_git_host_change_source.py::test_a_credential_in_a_commit_message_is_redacted_on_this_route_too -->
<!-- proof: tests/contract/capabilities/test_changes_in_window.py::test_a_quiet_resource_produces_evidence_rather_than_an_empty_answer -->
<!-- proof: tests/synthetic/test_change_correlation_value_scenario.py::test_the_arms_disagree_which_is_the_delta_this_scenario_measures -->
<!-- proof: tests/unit/gateway/http/test_resource_changes.py::test_a_change_that_only_shares_a_window_is_labelled_rather_than_hidden -->
<!-- proof: console/tests/unit/surfaces/run-timeline.test.tsx -->
<!-- proof: console/tests/unit/surfaces/resource-changes.test.tsx -->

---

## 1. The component-to-workload half comes from the apply record, not from the estate

**Planned.** `spec.md` §B and `plan.md` Scope B both say the middle hop is
"component → workloads it manages, **by 053's estate**".

**Done.** Path → component is a rule over the repository layout, driven by the
components the cluster declares (`platform/changes/correlation.py::component_for`).
Component → workload is read out of each component's own apply record, as the
list of correlation keys under `manages` in `.infra-state/<component>.json`. The
estate supplies the *identity* of the resource under investigation — its
correlation key, display name, zone and domain — and nothing else.

**Why.** 053's enrichment carries no notion of a component. It ingests five
documents (`zones`, `nodes`, `cts`, `vms`, `services`) and annotates resources
with `criticality`, `tier`, `owner`, `zone` and `domain`. There is no attribute
naming which component built a guest, and `services.yaml` names a *service* and
its domain, which is a different concept — a workload can serve a domain and be
built by a component whose name is nothing like it.

Three ways to close the gap were available and two of them are worse:

- **Match a component's name against a resource's name.** This is the guess that
  produces exactly the false positive the whole feature exists to remove. A
  component called `monitoring` and a container called `mon-prometheus` are
  probably related; `networking` and `nginx` are probably not, and no rule can
  tell.
- **Add a `component` annotation to 053's enrichment.** That means editing a
  bundled JSON Schema, the inventory reader, and the annotation vocabulary of a
  closed feature, so that an operator has to write down by hand something the
  apply tooling already knows exactly.
- **Read it from the state the component wrote.** OpenTofu state per component
  *is* the list of resources that component manages, and the apply record is
  where that list already lives. It is a fact rather than an inference, and it
  is current by construction: a component that stopped managing a guest stops
  listing it on the next apply.

The third is what is implemented. `ComponentMap.managed` is a mapping from
component name to correlation keys, `InfraApplySource.components()` produces it,
and `ChangeInquiry` gathers it from whichever sources are a `ComponentReporter`.
The correlation is still "path → component → workload → this resource"; only the
custodian of the middle edge differs from what the plan assumed.

**What this costs.** A deployment whose repository has no `.infra-state/` gets no
component map, so every correlation degrades to `WINDOW_ONLY`. That is reported
rather than hidden — the change record says so — and it is the correct answer:
without knowing what a component built, nothing establishes that a change
reached a resource.

---

## 2. There is no git-log reader, and the apply record is the whole local source

**Planned.** `plan.md` Scope A: `infra_apply` "reads the apply record
(`.infra-state/` + the git log of applied revisions)".

**Done.** `platform/changes/infra_apply.py` reads `.infra-state/` and nothing
else. A revision the record holds with no `applied_at` is the "committed and
never applied" case, marked with `Change.applied is False`.

**Why.** Reading a git log means running `git` or vendoring a repository parser.
Running `git` puts a subprocess on the investigation path, needs a checkout
rather than a readable directory, and makes the unit suite depend on git being
installed and on commit dates that differ per clone. A repository parser is a
second implementation of something the tooling already wrote down.

The apply record can carry both halves, and does: an entry with `committed_at`
and no `applied_at` is a commit nobody applied. Every acceptance the spec asks of
the distinction is satisfied from one document — which is the better arrangement
anyway, because the two facts then cannot disagree about which revision they are
describing.

**What this means for the record's shape.** `.infra-state/<component>.json` is
one document per component holding `component`, `manages`, and `applies[]`, each
apply carrying `revision`, `author`, `message`, `committed_at`, optional
`applied_at`, `outcome` and `paths`. That is a format this feature defines. If
the real tooling writes something else, the reader is thirty lines of field
mapping — see §7.

---

## 3. A change carrying a secret is redacted and kept, where a document would be refused

**Planned.** `plan.md` decision 3: commit messages and paths "pass the same
guardrail screening that 056's ingestion does".

**Done.** The same ruleset, and a different response. 056 *refuses* a document
carrying a credential shape; `platform/changes/screening.py` redacts the change's
message and paths, records the rule names on `Change.redactions`, and returns the
change.

**Why.** A corpus is better off without a document that carries a secret: the
document is one of sixty-six, and dropping it costs a runbook nobody has read.
An investigation is not better off blind to the apply that caused the outage. A
change refused at the boundary is a change the correlation cannot reach, which
means the strongest available lead disappears because somebody pasted a token
into a commit message — and the report then says "no change touched this
resource", which is now false.

The secret never travels either way. `GuardrailEngine.scan` replaces both
redacting and blocking spans, so the value is gone from the text before the
record is built; what differs is whether the surrounding facts survive.

---

## 4. The capability declares no integration requirement

**Planned.** `tasks.md` T-007: "declared metadata complete (read side-effect
level, evidence source, use cases)". `tasks.md` Dependencies names 051 as a hard
dependency "for the git-host source only".

**Done.** `changes_in_window` declares `Requirements()` — no integration. The
unavailability path names what to configure instead.

**Why.** A capability's `requires.integrations` excludes it from a team's
catalogue when unmet. The `infra_apply` source needs no credential and no
vendor, so declaring `github` (or any of the three) would hide the tool from
precisely the deployment it was built for: a cluster whose repository is on disk
and whose git host is nobody's business. Declaring all three would be worse
still, since the requirement is a conjunction.

What is missing is therefore reported at call time — `CapabilityErrorClass.UNAVAILABLE`
with the sentence in `config/prompts/changes.py::NO_CHANGE_SOURCE`, which names
both routes. Asserted by
`tests/contract/capabilities/test_changes_in_window.py::TestTheDeclaration::test_it_declares_no_integration_because_the_local_source_needs_none`.

---

## 5. A git-host change carries no paths, and says so

**Planned.** `plan.md` Scope A(2): a thin adapter over the existing clients'
`list_commits`-shaped calls, "the same `Change` shape coming out".

**Done.** `integrations/_base/changes.py::GitHostChangeSource`, over GitHub,
GitLab and Bitbucket, with `paths=()` and a sentence in `Change.detail["paths"]`
saying the vendor's listing does not report them.

**Why.** None of the three commit-listing endpoints returns the files a commit
touched. GitHub's `/search/commits` returns commit metadata; GitLab's project
commits endpoint returns the message and the author; Bitbucket's returns the
same. Getting paths means a second call per commit, which is fifty round trips
for one window and a rate limit in production.

The consequence is honest and is stated rather than hidden: without paths the
correlation cannot reach a component, so every git-host change grades
`WINDOW_ONLY`, and `CHANGE_PATHS_UNAVAILABLE` is appended to its explanation so a
reader knows the weak grade is a limit of the source rather than a fact about the
change. This is the plan's own hierarchy working as intended — the apply record
is the valuable source and the git host is the fallback.

---

## 6. The git-host source lives in `integrations/_base/`, not `platform/changes/`

**Planned.** `plan.md`: "protocol in the platform, implementations below" (038
deviations §9: tier 3 names the contract, tier 2 satisfies it).

**Done.** Exactly that, and it is worth recording because the plan's own text
lists both sources under Scope A as though they sat together. `ChangeSource` and
`Change` are tier 3 (`platform/changes/port.py`); `InfraApplySource` is tier 3
because it needs no vendor at all; `GitHostChangeSource` is tier 2 because it
imports three integration clients, and `make check-imports` would fail on a tier
3 module that did.

---

## 7. Nothing has been run against the real repository, and this is genuinely unmet

**Planned.** `spec.md` acceptance 1: a change source answers the window question
"against the real repository". `tasks.md` T-011: "Against the real repository
(deviations, not gate): `changes_in_window` over a real window returns the actual
applies with authors and paths; one recorded transcript."

**Done.** Nothing. There is no `/root/infra-cluster` on this machine — `/root`
holds one directory, `reports` — and no checkout of it anywhere reachable.

**What exists instead.** `tests/corpus/operational/.infra-state/`, three
component records shaped like the real repository's: structured conventional-
commit messages including a breaking-change marker (`fix(networking)!: tighten
the infra zone firewall profile`), paths under `services/<component>/` and
`policies/firewall/`, and one revision committed and never applied. That corpus
is the same tree 056 committed, which is deliberate: it is one fixture
repository, and the change record belongs to the repository whose documentation
is already there.

**What that does and does not establish.** It establishes that the reader, the
window filter, the applied/committed distinction, the component map, the
correlation and the capability all work over a record of this shape. It does not
establish that the real tooling writes this shape. If it writes something else —
a different filename, a different key for the instant, an apply log rather than
one document per component — the reader needs a field mapping and nothing else:
`InfraApplySource._applies` is the only place that names a key.

**Why this is a deferral and not a handoff.** Every later feature in this wave is
in the same position: there is no cluster and no repository to reach, so a
handoff to one of them would be a handoff to a feature that also cannot do it.
056 recorded the same gap under the same theme, and the honest record is that
this whole wave's live-cluster verification is one piece of work waiting for
access rather than eleven.

<!-- defer: theme=live-cluster-verification -->

---

## 8. The scenario measures the correlation against the clock, and the delta is one wrong answer

**Planned.** `tasks.md` T-008: "alert at T, apply at T−13min on the managing
component ⇒ the conclusion cites the change with `MANAGES_RESOURCE` strength;
ablation with correlation disabled reported."

**Done.** `tests/synthetic/test_change_correlation_value_scenario.py`, eleven
assertions over one apply record holding three changes:

- `b0c99fe`, the `storage` component, applied **four minutes** before the error,
  managing a container on another network;
- `9f2c1ab`, the `monitoring` component, applied **thirteen minutes** before the
  error, managing the container that failed;
- `3d81e0c`, a commit on `monitoring` that nobody applied.

**The delta.** With correlation: `9f2c1ab`, graded `MANAGES_RESOURCE`, with the
chain `services/monitoring/stack/values.yaml → monitoring → hal9000/lxc/115`.
Without it, ordering by the only thing left — the clock — gives `b0c99fe`. One
scenario, two arms, **1 of 1 correct with the mechanism and 0 of 1 without**.
Both arms read the same record through the same `InfraApplySource`; the ablation
arm is the ordering an investigation writes when nothing tells it otherwise, not
a strawman fixture.

**What the ablation is not.** It is not a switch inside the shipped correlation.
There is no `correlation_enabled` flag, and adding one would be a production
switch whose only caller is a test. The arm is the alternative behaviour written
out in the test, which is how `test_signal_map_value_scenario.py` measures the
signal map and for the same reason.

**Not registered in the scenario corpus.** The file is a value scenario beside
`test_signal_map_value_scenario.py` and `test_ablation_value_scenario.py`, not a
`tests/synthetic/**/scenario.yml` the corpus loader walks, so the corpus's
baseline numbers are unchanged. The suite's own delta is therefore reported here
rather than in `tests/synthetic/baselines/`.

---

## 9. The console visual baseline was not re-captured, because nothing it captures changed

**Planned.** `tasks.md` T-009: "Component test first; visual baseline
re-captured."

**Done.** The component test
(`console/tests/unit/surfaces/run-timeline.test.tsx`, eleven assertions) was
written first and confirmed failing. No baseline was re-captured, and
`console/visual/` is untouched.

**Why.** The footer is drawn only when the run's replay contains a
`changes_in_window` call. The committed mock data plane's `run-replay` fixture
contains calls named `estate.storage_pressure` and its neighbours and no change
call, so `rulerFromReplay` returns `undefined` and the run screen renders exactly
as it did before. `make verify` runs the visual regression suite
(`tests/contract/console/test_console_visual_regression.py`) and it passes
against the existing baselines — which is the evidence that nothing moved.

**What this means.** The ruler has no visual baseline of its own. Adding one
would mean putting a change call into the committed dataset, which is a change to
the fixture plane rather than to this feature, and one that would need
`python -m tools.mockplane build` plus a re-captured baseline for a screen whose
resting state is unaffected. The unit test asserts the geometry (50 per cent for
the half-hour mark, 86.7 for the investigation, clamping at the edges) and the
grading, which is what a pixel comparison would be standing in for.

<!-- handoff: to=062-data-ingress-and-delivery what="put a changes_in_window call into the committed run-replay fixture and capture a visual baseline for the run screen's change ruler; 062 owns the fixture plane's ingress shapes and rebuilding the dataset is its ordinary work" -->

---

## 10. `changes_in_window` takes a resource and a window, and not a free time range

**Planned.** `plan.md` Scope A: "the agent receives a typed tool —
`changes_in_window(resource, window)`".

**Done.** `changes_in_window(resource: str, hours: float = DEFAULT_CHANGE_WINDOW_HOURS)`.

**Why the signature is hours rather than a window object.** A tool schema is what
a model fills in, and a model asked for a `window` object produces two
timestamps, one of which is usually wrong by a timezone. One number, defaulted,
with the ceiling enforced where it arrives — `ChangeWindow.ending` raises
`ChangeWindowInvalid`, the tool returns `INVALID_ARGUMENTS` — is a schema the
model cannot get half-right.

**Why it is refused rather than clamped.** A query silently narrowed from a
fortnight to a week returns a shorter history than the caller believes it has,
and the negative built on it — "nothing changed in the last fortnight" — is then
wrong in the one direction that matters.

---

## 11. The prompt guidance paragraph was written and then removed

**Planned.** Nothing asked for one. `config/prompts/changes.py` initially carried
a `CHANGES_GUIDANCE` paragraph mirroring `TOPOLOGY_GUIDANCE`.

**Done.** Removed before the feature closed. The domain's methodology lives in
`capabilities/skills/changes/SKILL.md`, which is the mechanism this codebase
already has for telling an agent how to use a domain's tools.

**Why.** A guidance paragraph reaches the root prompt through a hook registered
by a composition root — `KnowledgeService.install(hooks)` does it for topology
and the knowledge base. There is no `ChangeService` composition root, and adding
one, plus a hook, plus its ablation switch, is a feature nothing asked for. A
constant nothing reads is dead code that looks like configuration, and the skill
body carries the same content to the same model at the point it is selected.

---

## 12. Two console panels, both reading the same correlation, neither re-deriving it

**Planned.** `plan.md` Scope C: the run screen's footer and the resource
detail's "recent changes" panel.

**Done.** Both, and they are fed differently on purpose.

The **resource detail** panel comes from the endpoint
(`GET /v1/estate/resources/{resource_id}` grew a `changes` block), because a
resource's page is asked about a resource and not about a run: there may be no
investigation at all.

The **run footer** comes from the run's own transcript, with no new route, as the
plan asked. `rulerFromReplay` finds the `changes_in_window` call in the replay and
reads its result. That is not a shortcut: a footer that re-queried would
eventually draw a change the investigation never saw, and the picture would
disagree with the report above it.

Both render the same closed set of strengths and both draw a `WINDOW_ONLY` change
rather than hiding it — hidden, nobody reading the page can rule it out; shown
without its label, it reads as a cause.

**One thing the endpoint does that the plan did not specify.** The panel is drawn
even when it lists nothing, and carries `answered`. An empty panel reads as
"nothing has changed"; a deployment that consulted nothing has established
nothing, and the two must not look the same. Asserted by
`tests/unit/gateway/http/test_resource_changes.py::test_a_deployment_with_no_change_source_says_so_rather_than_showing_an_empty_panel`.

---

## 13. Nothing composes a change source yet

**Planned.** Implied throughout: a deployment points the platform at a
repository.

**Done.** `GatewayState.change_sources` exists and defaults to empty;
`capabilities/tools/changes/binding.py` exists and defaults to unbound. Neither
is populated by any composition root in this repository.

**Why.** Which sources a deployment has is a configuration decision, and the
tree that would hold it is 058's. Wiring a path today would mean either a
constant naming somebody's repository or an environment variable that 058 then
has to migrate. Both routes report the absence correctly — the capability returns
`UNAVAILABLE` naming what to point at, and the resource panel says nothing was
consulted — so the unconfigured state is the honest one rather than a broken one.

<!-- handoff: to=058-configuration-write-surfaces what="give the configuration tree a change-source setting (a repository path for the apply record, and a vendor plus repository for a git host) and compose GatewayState.change_sources and the capability binding from it" -->

---

## 14. What the fixture corpus grew

`tests/corpus/operational/.infra-state/`, three files, committed with `git add -f`
because the directory is a dot-directory and would otherwise be easy to miss —
`.gitignore` does not exclude it, and `git ls-files` confirms all three are
tracked.

The tree is 056's, unchanged apart from the new directory. Nothing under `docs/`
or `policies/` was touched, so 056's exact readable-set assertion
(`test_the_readable_set_is_markdown_under_docs_and_yaml_under_policies`) still
holds: the corpus source walks those two roots only, and `.infra-state/` is
invisible to it. The 154 knowledge tests pass unchanged.

One instant in `storage.json` was moved from 2026-07-20 to 2026-07-28 while
writing the tests, because a fixture twelve days before the scenario's "now" is
outside `MAX_CHANGE_WINDOW_HOURS` (a week) and the test that wanted a wider
window could not ask for one.

---

## 15. Answering the auditor

`done-auditor` was run against the diff before this file was written and found
two things worth acting on.

**A tautological test.** `test_the_message_is_screened_the_same_way_every_change_is`
asserted `redactions == ()` on a commit message containing no credential —
`Change.redactions` defaults to `()`, so the assertion held whether or not
`screen_all` was ever called. Replaced by
`test_a_credential_in_a_commit_message_is_redacted_on_this_route_too`, which
pushes `AKIAIOSFODNN7EXAMPLE` through a recorded GitLab and asserts both that the
value is gone and that `aws-access-key-id` is named. The recorded host now serves
a deep copy of its payload, so a test that alters the subject line cannot change
what its neighbours see.

**The missing deviations file**, which is this one. The auditor was right that
the real-repository gap in §7 was undisclosed at the time it ran.

Its two other observations were checked and stand as they are: the wall-clock
anchoring in the contract test and the synthetic scenario is deliberate (the
capability windows back from the real clock, so a pinned fixture date would age
out of every window and the suite would pass while exercising nothing), and the
T-009 baseline claim is answered in §9.

---

## 16. Six proof marks named a class and the close step could not resolve them

**What failed.** The close step reported six unmet obligations, one per mark:
"proof cites `<nodeid>`, which does not exist — write the test or drop the
claim". All six tests existed, were tracked, collected under exactly the nodeid
cited, and passed.

**The cause.** The marks were written as pytest nodeids —
`path::Class::test_name` — and the proof grammar the wave reads is `path` or
`path::test_name`. Of the 107 proof marks across `specs_v3/`, the only six in
the three-segment form were these, and they are the only six that failed. 056
cites six class-scoped tests of its own (`test_corpus_source.py::test_a_path_classifies`
and neighbours are all methods on a class) in the two-segment form, and its
close step accepted them, which is what establishes that the resolver matches on
the test's name within the file rather than on a nodeid.

**Done.** The six marks were rewritten to `path::test_name`. Nothing else
changed: no test was written, renamed or moved, no claim was dropped, and no
implementation was touched. Each of the six names is unique within its file, so
the two-segment form still names exactly one test.

The prose table above still spells the class out, because a reader looking for
`TestTheNegative` benefits from knowing where the test sits. Only the marks —
which are read by the automation — follow the grammar.

**Why this is a fix and not a workaround.** The obligation is that a claimed
behaviour has a test proving it. The tests prove it and are green; what was
broken was the citation's form. Loosening anything to make the gate pass was not
available and was not needed.

---

## Appendix — the gate

`make verify` green: **13,295 passed, 25 skipped**, 437s. The console's own gate
(`console-format-check`, `console-lint`, `console-typecheck`, `console-client-check`)
green, and the console unit suite at 1,197 passing across 69 files.

Nothing was loosened to get there. `ruff.toml`, `mypy.ini`, `.importlinter`,
`pytest.ini` and the console's lint and type configuration are untouched, and
there is no `skip` or `xfail` anywhere in the diff.

Two generated artefacts were regenerated rather than edited:
`fixtures/contract/openapi.json` and `console/src/api/schema.ts` (the resource
detail grew a `changes` block), and `docs/capabilities.md` plus
`docs/site/capabilities/changes.md` (a capability was added). Both are checked by
`make verify` and both were produced by their own tooling.
