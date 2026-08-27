# Deviations — 059 Team operating context

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. Sections are a mapping, not a list, and that is what makes them inherit

**Planned.** The plan is explicit: *"**Named sections** (`tuple[ContextSection,
...]`, each `name` + `body`) … Distinct names enforced by a validator (the
`_names_are_distinct` pattern already in `AgentsConfig`)."*

**Done.** `OperatingContext.sections` is a `Mapping[str, str]` — section name to
body.

**Why the plan's own reasoning demands it.** The plan gives the reason for named
sections in the sentence immediately before: *"a section is the unit of
inheritance: a child node can add, override (same name), or remove … one section
without touching the rest."* A tuple cannot do any of that.
`platform/config_service/merge.py` states the rule with a requirement number
behind it — **lists replace entirely** — so a child that wanted to add one
section to what the organisation wrote would have had to restate every section
its ancestors wrote. That is the exact failure this whole feature exists to fix,
one level down: the spec's own argument against a single free-text block ("uma
seção pode ser herdada, sobrescrita ou removida por nível, e um bloco só pode ser
substituído inteiro") applies word for word to a list of sections.

A mapping merges per key, which gives the three operations for free and gives
per-section provenance for free with them: the path
`agents.operating_context.sections.<name>` is an ordinary leaf, so
`MergeResult.provenance` attributes it the way it attributes every other value.
Nothing in the config service was changed to make this work.

**Distinctness therefore needs no validator**, and that is a stronger guarantee
than the one the plan asked for: two sections cannot share a name in a mapping,
so there is no document that could express the collision. What the validator
does instead is refuse a name that cannot be *addressed* — one containing the
path separator, one that is blank, one longer than a heading — because a name is
a path segment in the provenance table as well as a heading in a prompt.

`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_a_child_adds_a_section_without_restating_its_parents -->`
`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_a_child_overrides_one_section_by_name_and_keeps_the_rest -->`
`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_each_section_reports_the_node_that_supplied_it -->`
`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_a_section_name_carrying_a_dot_is_refused -->`

**Two removals, not one, because they are different operations.** Emptying a
section's body at a child silences an inherited section — the text stops being
sent. Clearing the *field* (058's `remove`) puts the ancestor's text back. Both
are offered and both are tested; conflating them would repeat the mistake 058
recorded in its own §2.

`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_a_child_removes_an_inherited_section_by_emptying_its_body -->`

---

## 2. T-001 and T-002 landed in one commit

The budget is a `model_validator` on the class T-001 introduces, and splitting
them would have meant a commit in which the field exists and its ceiling does
not — an unbounded free-text field paid on every model call, for the length of
one commit. 058 recorded the same decision for the same reason in its §3.

Both behaviours are still named by their own tests, in their own section of the
file.

---

## 3. Credential screening needed no new code, which is the outcome worth recording

**Planned.** T-003: *"Implement the screening in validation."*

**Already there.** `ConfigValidator.secret_errors` walks `paths.scalars` over the
whole document and scans every string with the shipped guardrail ruleset,
refusing with the rule name and the path and never the value. A section body is
an ordinary scalar at `agents.operating_context.sections.<name>`, so the field
was covered by the existing scan the moment it existed.

What this feature added is the *tests*, and they are worth having rather than
assumed: this is the one field in the schema that invites an operator to paste
what they know about their environment, and what somebody knows about their
environment is sometimes how to log into it. The refusal names the section, never
quotes what it found, and the prose the field exists for — CIDRs, MTUs, vmid
rules — passes.

`<!-- proof: tests/unit/platform/config_service/test_config_validation.py::test_a_credential_pasted_into_an_operating_context_section_is_refused -->`
`<!-- proof: tests/unit/platform/config_service/test_config_validation.py::test_the_refusal_of_a_context_section_never_quotes_what_it_found -->`
`<!-- proof: tests/unit/platform/config_service/test_config_validation.py::test_an_operating_context_describing_an_estate_is_not_mistaken_for_a_secret -->`

---

## 4. The assembly is a hook, and the reason is that a specialist is a session too

**Planned.** T-004: *"Implement the append at the prompt-assembly site."* The
plan hedges: *"`prompt_for(role)` (or the run-composition site that calls it —
wherever the prompt is finally assembled for the model)"*.

**Done.** Both, and they are the same function underneath.

- `AgentsConfig.system_prompt_for(role)` is the configuration-side assembly:
  the shipped-or-overridden prompt, plus the rendered context, for the roles in
  `OPERATING_CONTEXT_ROLES`. This is what the console previews.
- `OperatingContextGuidance` (`platform/config_service/guidance.py`) is an
  `on_run_start` hook that appends the same text to `session.system_prompt`,
  through the same `with_operating_context` function, so the two cannot render
  it differently.

**Why a hook rather than only composition.** A sub-agent runs in *its own
session*, built from `SUBAGENT_SYSTEM_PROMPT` rather than from the
investigator's prompt, and driven through the same registry
(`ReActLoop._run_subagent`). Appending at composition time would have reached
the investigator and left every specialist reading the same evidence without the
facts that say how to read it — and the LXC-metrics fact is exactly the sort a
metrics specialist needs most. The hook fires per session, so it reaches both.
It is also the pattern this repository already uses for prompt additions
(`platform/knowledge/guidance.py`, `platform/memory/guidance.py`), including the
registered name an ablation unregisters by.

`<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_a_specialist_reasons_about_the_same_estate_as_its_parent -->`
`<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_what_the_model_gets_is_byte_identical_to_what_a_preview_would_show -->`

### 4a. The override did not reach the model at all, and now does

Not a deviation so much as a hole the task's own acceptance walked into.
`RunRequest.system_prompt` existed and **nothing in the pipeline ever set it**:
`GatherEvidenceStage._request` built a request with an objective, a source, a
session id and a context, and no prompt — so `AgentsConfig.prompt_for` had no
production caller and a configured override reached nobody.

T-004 asks for a run "composed with an override *and* operating context". That
is not assertable until the override travels, so `GatherEvidenceStage` and
`build_pipeline` now take `system_prompt`, from
`RuntimeBindings.system_prompt_for`. It is the smallest change that makes the
acceptance a statement about the product rather than about a helper.

`<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_the_override_and_the_operating_context_both_reach_the_model -->`
`<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_a_deployment_that_configured_none_of_this_sends_exactly_what_it_sent_before -->`

**And the limit of that, stated so nobody reads item 1 as more than it is.** Found
by the done-auditor against this diff, which is why one is run. `build_pipeline`
has *no* caller outside `tests/`, on any feature: nothing in `gateway/` turns an
arriving alert into a pipeline run yet. So "a run composed with an override and
operating context sends the model one system prompt containing both" is proven
against the real bindings, the real hook, the real gather stage and the real
loop — everything the composition root would use — and the composition root
itself does not exist to be pointed at. That is a whole-repository condition
rather than something this feature introduced or was scoped to fix, and the two
lines it will need are the ones this test writes.

---

## 5. T-005 is structural, and is a stronger result than the task asked for

**Planned.** *"Failing test: intake/diagnose do not receive the context by
default. Implement."*

**Nothing to implement.** Intake and diagnosis are `llm.invoke_structured` calls
inside their stages, with `system=INTAKE_SYSTEM_PROMPT` written at the call
site. They never construct a `Session` and never run through the hook registry,
so there is no configuration that could give them the context — it is not a
default that could be changed, it is a path that does not exist.

`OPERATING_CONTEXT_ROLES` is still a named constant and
`system_prompt_for("intake")` is still byte-identical to `prompt_for("intake")`,
because the *console* has to be able to say which roles receive the text, and a
client holding its own copy of that list would explain the wrong thing the day
it changed.

`<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_intake_does_not_receive_the_operating_context -->`
`<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_a_role_outside_the_named_set_is_byte_identical_to_its_prompt -->`

---

## 6. The ablation is a standalone value scenario, not a ninth mechanism

**Planned.** T-006: *"Synthetic scenario + ablation … Report the scenario-suite
delta and the ablation number."*

**Done.** `tests/synthetic/test_operating_context_value_scenario.py`, built on
054's precedent (`test_signal_map_value_scenario.py`) rather than on the
eight-mechanism table in `tests/harness/ablation/switches.py`.

**Why not the table.** That table is a shared, closed list with its own contract
tests and its own trace-key assertions, and adding a ninth row touches
`ABLATION_MECHANISMS`, `MECHANISMS`, `MechanismSwitches`, `RootConfig.trace_summary`
and the tests that count them — a cross-cutting change to a structure three other
features in this wave also read. The signal map, which is the most similar
mechanism in the repository, is not in that table either and ships a standalone
value scenario. This follows it.

**The number.** One scenario, two arms, one switch
(`agents.operating_context.enabled`, which is the ablation lever the field ships
with). With the context, the run cites the host-side series for guest 100 and
reads **0.94**, above the 0.90 a memory-pressure conclusion is drawn at; without
it, against the same estate, it cites the in-guest series and reads **0.31**.
Contribution: **one scenario from wrong to right, 0 → 1.** The scenario-suite
delta is one new scenario, five tests, all passing; no existing scenario moved.

**What it measures and what it does not.** The agent double is a policy, not a
script — it reads the prompt the hook actually built and decides from what is
there, which is how `test_ablation_value_scenario` already states the same
limitation. It measures *the mechanism* — a fact reaching the agent in a form it
can act on — not how reliably a particular model exploits one.

`<!-- proof: tests/synthetic/test_operating_context_value_scenario.py::test_the_fact_changes_which_source_the_pressure_claim_cites -->`

---

## 7. The template's zone networks are inferred, and the template says so

**Planned.** *"zones with their CIDRs (053's `ZoneMap`)"*.

**`ZoneMap` is not stored anywhere.** It is built at *ingestion* from the
networks declared in an estate-discovery request
(`gateway/http/routes/estate_discovery.py` → `ZoneMap.of(request.zones)`), used
to place resources, and discarded. What survives on a resource is its `zone`
attribute and its `address`.

**Done.** The network offered for a zone is the prefix covering the addresses the
estate actually holds for that zone, at `ALERT_ZONE_INFERENCE_PREFIX` — the same
constant and the same rule alert resolution already uses for an address no
declared network covers, whose own comment says "the estate's own resources on
the same network say which zone it is".

**And where it cannot say, it does not guess.** A zone whose resources sit on two
different /24s renders as "network not established" rather than as one of them:
an operator correcting a line that is wrong in a way they would have to already
know the answer to catch is worse off than one filling in a blank.

`<!-- proof: tests/unit/platform/estate/test_operating_context_template.py::test_the_template_carries_each_zone_and_the_network_its_addresses_sit_on -->`
`<!-- proof: tests/unit/platform/estate/test_operating_context_template.py::test_a_zone_whose_addresses_disagree_offers_no_network_rather_than_one_of_them -->`

### 7a. The builder lives in `platform/estate/`, not in the config service

The plan puts the template beside the context. It is derived from the estate —
kinds, zones, addresses, and the signal map — so it lives with what it derives
from, and the config service does not gain a dependency on the estate. The
structural test the plan asks for (no path to `core.llm`) is there and parses the
module's own imports rather than trusting a convention.

`<!-- proof: tests/unit/platform/estate/test_operating_context_template.py::test_the_builder_cannot_reach_a_model -->`

---

## 8. The screen needed a preview route the plan did not name

058's discipline is "nothing is saved without seeing the effect", and here the
effect is literally the text a model will read. `GET /operating-context` can only
show the prompt for what is *already saved*; showing it for a pending edit needs
the deployment to assemble it, so `POST /v1/config/{node_id}/operating-context/preview`
exists. It runs the same merge and the same validator the write runs, and
returns the assembled prompt, the token cost, and every reason the document
would be refused.

**A refused document renders no prompt at all.** Found while writing the test:
the first version echoed the pending text back inside a block labelled "what the
model will be sent", which for a section carrying something credential-shaped is
the opposite of what the refusal is for. There is also nothing to preview — that
text is never going to be sent.

`<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_the_preview_shows_the_prompt_a_pending_change_would_send -->`
`<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_a_credential_in_a_pending_section_is_refused_without_being_quoted -->`

### 8a. `ConfigService.validation_of` is new, and is deliberately the same validator

A surface showing why a document *would* be refused while somebody can still
edit it needs the write path's own check. A second implementation in the console
would agree until a rule moved and then refuse nothing while the write refused
everything.

---

## 9. The budget is enforced per node, and a chain can still exceed it

Worth stating plainly rather than leaving to be found.

`ConfigValidator` validates **a node's own document**, which is a property of the
configuration service that predates this feature — required fields, for
instance, are checked against the accumulated policy precisely because the node
document alone cannot answer. So a four-level chain whose nodes each write 1,000
tokens of context stores happily and resolves to 4,000.

**What happens then is safe and silent.** `RootConfig.read` refuses the merged
section, `EffectiveConfig.build` falls back to the default, and the deployment
sends **no** operating context at all — every other setting survives. Nothing is
truncated and nothing over-budget reaches a model.

**Where it stops being silent** is the preview: `over_budget` is computed against
the *merged* result, so an operator adding the section that would tip the chain
over is told before they save. That is where somebody can still act on it.

`<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_a_context_that_only_goes_over_budget_once_merged_is_still_named -->`

Making the *write* refuse a merged overage is a change to how the configuration
service validates every field, not to this one, and it belongs with whoever
takes that on rather than being smuggled in here.

`<!-- handoff: to=061-proposed-changes what="validate a write against the resolved chain rather than the node's own document, so a bound like OPERATING_CONTEXT_TOKEN_BUDGET is refused at the write that crosses it instead of only in the preview" -->`

---

## 10. The screen is its own area, and eleven baselines moved because of it

D2 puts "Contexto da equipe" in the Ajustes zone as an item of its own, and that
is what was built: `/team-context`, in the settings group, taking `config.read`.

The consequence is the one 058 recorded in its own §16: the sidebar is in
`Shell`, `Shell` wraps every route, so a new navigation entry moves **every**
screenshot. Eleven of twenty baselines differed, all in the same strip of
sidebar, and the twelfth change is the new screen's own baseline. The diffs were
read before anything was accepted — `runs-1440-light`'s diff is three rows of
sidebar and nothing else — and recaptured with `make console-visual-accept`, so
`git diff console/visual/baselines/` is the review.

The nine that did not move are the gallery and sign-in routes, which carry no
sidebar, and the 320px capture, where it is collapsed. That is the check that
this changed what the feature changed and nothing else.

### 10a. A comment inside the braces hides an area from a contract test

Costing about twenty minutes, so it is written down. `declared_areas()` in
`tests/contract/console/test_console_shell.py` matches `\{\s*id:\s*'…'`, so an
entry whose comment sits *between* the brace and `id:` is invisible to it — and
the area then fails `test_the_deploy_walk_covers_exactly_the_areas_the_console_declares`
as "walked but not declared". `first-run` has exactly that shape and gets away
with it only because it is not in the deploy walk either. The comment now sits
above the brace.

---

## 11. The mock plane's operating context is written, not derived

Same decision, and the same reason, as 058's §6. The dataset is a plausible
deployment and it is what the visual suite photographs; deriving the template
here would have meant a screenshot of a screen offering its own starting
document over a filled-in one, which is two states at once.

Two smaller notes on it:

- **`tokens_used` is written rather than counted.** A fixture that computed it
  would be a second implementation of the budget. The real count is proven where
  it lives, against the estimator, in `test_operating_context.py`.
- **The network section carries no CIDR.** The dataset is anonymised on the way
  out, and an address rewritten inside a sentence came back as
  `198.51.100.71/24` — a host with a prefix on it, which is not a network, in the
  one section whose job is to state one correctly. It names the zone instead.

---

## 12. What is not built, and is therefore still open

- ~~**The two browser tests for this screen are written and have not been run
  here.**~~ **Withdrawn — they run and they pass.** See §14: the browser was
  never provisioned by anything, which is a hole in the toolchain rather than a
  property of this worktree, and "installing it reached nothing" was simply
  wrong. Both T-009 tests now execute in the gate.
  `<!-- proof: console/tests/e2e/surfaces.spec.ts -->`
- **Nothing removes a section from the console.** The editor adds sections,
  edits them, and silences an inherited one by emptying it — which is the
  operation that changes what the model receives. Clearing the *override* so an
  ancestor's text returns is the `remove` list on the write route, which the
  courier forwards and which no control calls.
  `<!-- handoff: to=060-agent-visible-and-tunable what="give the team-context editor a clear-this-override control per section, distinct from emptying the body; PUT /v1/config/{node_id} already takes the remove list and the courier already forwards it" -->`
- **The `enabled` switch has no control on the screen.** It is in the schema, it
  is the ablation lever, and it is rendered nowhere: the screen shows the text
  and the prompt. Switching a team's whole operating context off is a
  consequential action and deserves the treatment the kill switch got rather
  than a checkbox added at the end of a feature.
  `<!-- handoff: to=060-agent-visible-and-tunable what="offer agents.operating_context.enabled as a control on the team-context screen, with the preview showing the empty prompt it produces" -->`

None of these is in the Definition of done, which is why the feature is reported
as meeting it; the two that remain are in the spec's scope, which is why they are
named here rather than quietly dropped.

---

## 13. Definition of done, item by item

1. **Both the distributed prompt and the operating context provably reach the
   model in one run.** Through the real bindings, the real hook, the real
   `ReActLoop` and a scripted `core.llm` client, and the string the client
   received is asserted equal to the string the console previews.
   `<!-- proof: tests/unit/core/pipeline/stages/test_operating_context_prompt.py::test_the_override_and_the_operating_context_both_reach_the_model -->`
2. **Sections inherit with provenance like any config value.** Through the real
   merge, and again over HTTP across two levels.
   `<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_each_section_names_the_level_that_supplied_it -->`
3. **Over-budget context is refused naming the excess.**
   `<!-- proof: tests/unit/platform/config_service/test_operating_context.py::test_the_refusal_names_the_overage_in_tokens -->`
4. **Credential-shaped content is refused, value nowhere.**
   `<!-- proof: tests/unit/platform/config_service/test_config_validation.py::test_the_refusal_of_a_context_section_never_quotes_what_it_found -->`
5. **The initial template arrives pre-filled with discovered zones and signal
   sources.**
   `<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_the_template_carries_the_zones_and_networks_the_estate_discovered -->`
6. **The screen shows the final model-bound text before save.**
   `<!-- proof: console/tests/unit/surfaces/operating-context.test.tsx -->`
   `<!-- proof: tests/unit/gateway/http/test_operating_context_route.py::test_the_prompt_is_the_whole_string_the_next_run_will_be_sent -->`

---

## 14. The gate was red after the rebase, and neither cause was this feature's code

Recorded here because the fix is committed on this branch and is not about the
operating context at all. Both faults are in the console's browser harness, both
predate this feature, and both were latent until something ran the browser suite
in a fresh worktree — which is what §12's first bullet was, misread as a property
of the machine.

### 14a. Nothing ever provisioned the browser

`tools/console_e2e.py` pointed `PLAYWRIGHT_BROWSERS_PATH` at
`console/.toolchain/browsers/` — inside the checkout, deliberately, so two
checkouts pinned to two builds cannot take each other's. **No step filled it.**
`make console-setup` provisioned Node, pnpm and `node_modules` and stopped there,
so a worktree got a browser only if somebody had run `playwright install` in it
by hand. The worktree next door had; this one had not.

The symptom was the worst available one: sixty-two tests reporting failure, the
two written for this feature among them, for a reason that is not a defect in any
of them. `tools/console_toolchain.py` opens by naming its own acceptance —
*"the same Node, the same package manager and the same browser as CI"* — and the
browser was the item it did not do.

**Fixed where the gap is.** `ensure_browsers` is a toolchain step, listed as step
5 of that docstring, run by `provision()` and again by the harness on every run
so a contributor who never ran setup is not punished for it. It is idempotent by
construction: `playwright install` compares the build its own version wants
against what is unpacked. The build is not pinned beside it — Playwright refuses
to drive a revision other than the one it ships against, so the pin is already
the `@playwright/test` version in the committed lockfile, and a second number
could only disagree with the first.

`PLAYWRIGHT_BROWSERS_PATH` moved from a literal at the one launch site into
`environment()`, so the command that installs the browser and the command that
launches it cannot look in two places. It stays a `setdefault`: an air-gapped
machine with a populated cache still points at its own.

A browser that cannot be fetched now raises `ToolchainError` → exit 2 → a named
skip, which is the status the harness already reserved for "nothing was run".
It never again arrives as a failing suite. That distinction is the whole point:
a missing browser is something to install, a red test is something to fix, and
sixty-two of the first is where a real one of the second goes to hide.

`<!-- proof: tests/unit/tools/test_console_toolchain.py::test_a_console_command_looks_for_its_browser_inside_the_checkout -->`
`<!-- proof: tests/unit/tools/test_console_toolchain.py::test_the_browser_is_installed_where_the_suite_will_look_for_it -->`
`<!-- proof: tests/unit/tools/test_console_toolchain.py::test_a_browser_that_cannot_be_provisioned_is_not_reported_as_a_failing_suite -->`
`<!-- proof: tests/unit/tools/test_console_toolchain.py::test_a_browser_directory_an_operator_chose_is_left_alone -->`

### 14b. The harness bound two fixed ports, and under concurrency answered about the wrong console

This is the one worth reading twice. `CONSOLE_E2E_PORT` (8423) and
`CONSOLE_E2E_MOCK_PORT` (8424) were bound unconditionally. Another worktree on
this machine was running its own suite on them, and the failing log carries the
whole sequence:

```
⨯ Failed to start server
Error: listen EADDRINUSE: address already in use 127.0.0.1:8423
[Errno 98] error while attempting to bind on address ('127.0.0.1', 8424)
```

**And the run continued.** `_wait_for` asks whether *something* answers on the
port, and something did — the other checkout's console. It checks
`process.poll()` first, but our server had not finished dying yet, so the wait
returned against the stranger before the corpse was cold. The browser was then
pointed at a build from a different branch.

That is not a flake, it is a wrong answer: the suite would have been equally
willing to report green. A gate that can silently grade the wrong tree is worse
than one that is red, and it is the failure mode the task's own rule about
readings that vary is about.

**Fixed by not sharing an address.** `ports()` takes the pinned numbers and
returns them when they are free, or ones the kernel picks when they are not,
reserving every port before returning any so two servers in one run cannot be
handed the same one. The suite is told its base URL through
`NINJASRE_CONSOLE_BASE_URL` already, so nothing downstream cared what the number
was — only `playwright.config.ts`'s default, which is for a developer driving a
console they started themselves and is untouched. The chosen addresses are
printed, because a log that does not name the console it drove is the artefact
this bug hid behind.

The check-then-bind gap survives and is stated rather than papered over: a few
milliseconds against a listener that lives for minutes, and the loser now gets
`EADDRINUSE` on a port no other console is serving — the honest failure, not the
quiet one.

`<!-- proof: tests/unit/tools/test_console_e2e.py::test_a_port_another_run_is_holding_is_replaced_rather_than_collided_with -->`
`<!-- proof: tests/unit/tools/test_console_e2e.py::test_two_servers_in_one_run_are_never_handed_the_same_port -->`
`<!-- proof: tests/unit/tools/test_console_e2e.py::test_a_free_port_is_handed_back_exactly_as_it_was_asked_for -->`
`<!-- proof: tests/unit/tools/test_console_e2e.py::test_a_replacement_port_is_one_that_can_actually_be_bound -->`

### 14c. What this changes about §12

The T-009 acceptance is no longer deferred. Both browser tests —
`the operating context names the level each section came from` and `the operating
context shows the prompt before it offers a save` — run and pass, and the
`browser-suite-acceptance` defer is withdrawn rather than carried.

### 14d. One trap found while fixing the above, for whoever hits it next

Interrupting `make verify` can leave the working tree dirty in a way that fails
the *next* run for a reason unrelated to anything: `tests/contract/console/`
proves each console check by copying a deliberately broken fixture into
`console/src/lib/` and deleting it in teardown. Teardown does not run when the
process is killed, so a cancelled gate can leave `src/lib/reaching.ts` behind and
every subsequent run fails lint, correctly, about a file nobody wrote.

Not fixed here — a fixture cannot clean up after a signal it never receives, and
the alternative (seeding into a copy of the tree) is a change to how the console
gate is proven rather than to this feature. Recorded because the failure names a
file that is not in `git log` and does not look like a fixture, and `git status`
is the thirty seconds that answers it.
