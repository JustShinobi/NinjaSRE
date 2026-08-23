# Deviations — 061 Changes proposed by the agent

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each acceptance is proven

The definition of done asks for six things. These are where each is held.

| Acceptance | Where it is proven |
|---|---|
| 1 — a proposal carries evidence and a working link to its run | `tests/unit/gateway/http/test_proposal_loop.py::test_the_loop_closes_and_leaves_a_record_of_both_directions` |
| 2 — nothing applies without explicit human approval | `tests/unit/platform/proposals/test_nothing_applies_undecided.py` — nine cases, three origins × undecided / rejected / expired |
| 3 — approving needs the preview, or the dry run | `console/tests/unit/surfaces/proposal-review.test.tsx` and `console/tests/e2e/proposals.spec.ts` |
| 4 — a rejection needs a reason, and the reason resurfaces | `tests/unit/gateway/http/test_proposal_routes.py::test_the_reason_resurfaces_on_the_next_proposal_of_the_same_thing` |
| 5 — every applied proposal is reversible and audited with both parties | `tests/unit/platform/proposals/test_origins.py::TestRollingBackAnAppliedProposal` and `::TestApprovingWritesThroughTheOwningPath::test_the_audit_names_the_agent_and_the_approver` |
| 6 — credential- or guardrail-touching proposals are refused at the origin | `tests/unit/platform/proposals/test_screening.py` — the two containment tests at module level, and `TestTheSeal` for the credential half |

`<!-- proof: tests/unit/gateway/http/test_proposal_loop.py::test_the_loop_closes_and_leaves_a_record_of_both_directions -->`
`<!-- proof: tests/unit/platform/proposals/test_nothing_applies_undecided.py::test_an_undecided_proposal_refuses_at_the_applier_entry_point -->`
`<!-- proof: tests/unit/gateway/http/test_proposal_routes.py::test_the_reason_resurfaces_on_the_next_proposal_of_the_same_thing -->`
`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_a_change_to_the_containment_is_refused -->`
`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_emptying_a_sealed_section_is_a_change_like_any_other -->`

---

## 1. The extraction is four small things, not a base class

**Planned.** T-002: "Extract the shared propose-screen-queue shape with
`proposal_type`; knowledge origin migrated onto it."

**Done.** `platform/proposals/` holds the vocabulary (`ProposalState`,
`ProposalType`, `AgentProposal`), the screen, the queue service, and exactly one
shared *function* — `queue_request`, which writes the approval request and its
rollback plan in one unit of work. `platform/knowledge/proposals.py` keeps its
own `KnowledgeProposal`, its own `ProposalQueue`, and its own document-shaped
argument keys; what it now shares is the state enum and that one function.

**Why not more.** The obvious reading of "extract the shape" is a base class the
four origins subclass. That would have forced the knowledge origin's stored form
to change — its arguments are `title`/`body`/`document_type` at the top level,
not a `payload` — and the characterisation test written first (T-001,
`tests/unit/platform/knowledge/test_proposal_characterisation.py`) exists
precisely to say that the stored form is a compatibility surface rather than an
implementation detail. An approval written last quarter is read back by whatever
this module becomes.

So the shared piece is the invariant that actually has to be identical: the
request and the undo land together or neither lands. Everything else the four
origins genuinely do differently, and a base class would have made them look the
same while they were not.

**What that leaves.** `AgentProposal.from_request` reads *both* spellings —
`node_id` and the knowledge queue's `team_node_id`, and falls back to the
remaining arguments as the payload. That is what makes the unified queue show a
proposal the capability wrote before this feature existed, without migrating a
stored approval's arguments. Rewriting those would rewrite what somebody was
asked to approve.

`<!-- proof: tests/unit/platform/knowledge/test_proposal_characterisation.py::test_the_stored_request_is_the_shape_a_later_reader_expects -->`

---

## 2. Knowledge is in the unified queue, and the plan said it need not be

**Planned.** The plan lists knowledge as an origin that "exists" and treats the
work as the other three.

**Done first, and it was wrong.** `proposal_appliers_for` initially omitted
`ProposalType.KNOWLEDGE`, with a docstring arguing that routing it through the
new queue as well would give one proposal two places to be approved.

**What caught it.** T-009, written next: "a scripted investigation calls
`knowledge_propose`; **the proposal appears**". It did not. `/v1/proposals`
listed three origins and the fourth — the only one an agent can actually reach
today — was on a different screen.

**Why the first version was wrong.** The argument assumed two rows. There is
one: `ProposalType.KNOWLEDGE.action` is `"knowledge.proposal"`, which is
byte-for-byte the `PROPOSAL_APPROVAL_ACTION` feature 012 already stores under.
Wiring the applier does not create a second queue; it gives the one queue its
fourth origin, and the row it reads is the row the capability wrote.

**What shipped.** `KnowledgeProposalApplier.apply` calls the knowledge queue's
`apply` rather than its `approve` — the decision is already a row by the time
the applier runs, and approving twice is refused by the store, correctly.

`<!-- proof: tests/unit/gateway/http/test_proposal_loop.py::test_the_queue_shows_the_capabilitys_own_row_rather_than_a_copy -->`

---

## 3. The seal covers autonomy as well as the guardrail

**Planned.** Acceptance 6 and the scope note say "credencial ou guardrail".

**Done.** `SEALED_CONFIG_PREFIXES` is four: `policies.guardrails`,
`policies.masking`, `policies.approvals`, `policies.autonomy`.

**Why.** The spec's own sentence for the guardrail is the reason: "é o arquivo
que impede o resto; um agente que propõe afrouxar a própria contenção é
exatamente o que não se quer." Every one of those four is that file. An agent
that may not propose observe-only mode but may propose an autonomy statement
raising its own posture has the same outcome by a different path, and the path
is shorter.

The scope note that *does* mention autonomy — "essa decisão é da política de
autonomia (058), não desta spec" — is about who decides whether proposals
auto-apply. It is not permission to propose changes to that policy.

**A second thing the seal caught, in writing the tests.** An empty section or
list is a change. `policies.autonomy.statements = []` revokes every autonomy
statement a team has, and a walk that only yielded scalars let the most
destructive form of a sealed edit through as the one with nothing in it. The
leaf walker yields empty containers for that reason.

`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_a_change_to_the_containment_is_refused -->`
`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_emptying_a_sealed_section_is_a_change_like_any_other -->`

---

## 4. The credential half is a protocol, not the configuration validator

**Planned.** "the schema-marked secret set — 051's config-route seal is the same
rule".

**Done.** `platform/proposals/screening.py` declares a `SecretFields` protocol
with one method, and `gateway/http/routes/proposals.py` implements it over the
same integration directory the configuration validator reads.

**Why not the validator itself.** `platform/proposals` sits below
`platform/config_service`, and importing it from there closes a loop:
`config_service.bindings` imports `platform.knowledge.policy`,
`platform/knowledge/__init__` imports its proposals module, and that imports
`platform.proposals.models`. Python would resolve it today and break on the
first import-order change, which is a worse property than a one-method protocol.

The same reasoning applies to the leaf walker. `platform/config_service/paths.py`
does exactly what `_leaves` does, and reaching it means importing the package's
`__init__`. Ten lines is cheaper than an import order nobody can see.

---

## 5. The store gained `list_decided`, and it needed a port method

**Planned.** T-007: "the recall is a query over decided approvals by that key."

**Done.** `ApprovalStore.list_decided(action=…, limit=…)`, implemented in both
the fake and PostgreSQL, with two contract assertions.

**Why a port method rather than a filter over `list_pending`.** There was no way
to read a decided approval at all. `list_pending` is pending by definition, and
`get_request` needs an identifier you do not have. Two readers need the history —
the rejection recall and the acceptance figure — and both are about *deciding*
rather than about one decision.

**One detail worth naming.** The fake sorts by `(decided_at, approval_id)`
descending, identifier included and descending too. Two rows decided in one
transaction share a timestamp, and a fake that broke the tie ascending would read
them in the opposite order from PostgreSQL on exactly those rows — a suite whose
two backends disagree only sometimes.

`<!-- proof: tests/contract/persistence/test_approval_store.py::test_decided_requests_come_back_most_recently_answered_first -->`

---

## 6. Approving-after-the-effect is a client guarantee, and says so

**Planned.** T-006: "Approve control absent until the effect has rendered
(acceptance 3); e2e drives the bypass attempt."

**Done.** Exactly that, and no server-side token.

**Why, in 058's own words.** `console/src/surfaces/preview.tsx` states the rule
this feature inherits: "no API can know whether a person read the diff, and a
save that demanded a preview token would only prove the browser had asked. What
can be built is a document with nothing in it to press." A token here would have
been the same theatre with a worse failure mode — a check that looks like a
server rule and is not.

So the guarantee is structural in the document: `ProposalReview` renders no
approve control until an effect has come back, the e2e lands on the queue and
requires that the page contains none, and the reject control needs no effect at
all because refusing narrows rather than widens.

`<!-- proof: console/tests/e2e/proposals.spec.ts -->`

---

## 7. A corpus candidate already answered is not offered again

**Planned.** The handoff from 056 asks for the corpus sync to be scheduled and
its candidates given a review queue. Nothing says what a second pass does.

**Done.** `DetectorProposals.offer` skips any candidate whose correlation key is
already pending *or* already decided, and names each skip with why.

**Why decided counts as answered.** The spec's three-strikes insight is about a
*recurrence*: "este sintoma apareceu três vezes". A recurrence is an
investigation hitting the same symptom again, which arrives through the agent. A
nightly sync over a file nobody edited is not a recurrence, and a queue that
regrew every morning is one people stop opening — which would cost exactly the
visibility this feature exists to create.

`<!-- proof: tests/unit/platform/proposals/test_corpus_candidates.py::test_a_candidate_already_refused_is_not_offered_again -->`

---

## 8. The corpus sync is a job definition, and there is no runner for it

Stated plainly rather than left to be found, because the handoff asked for
"schedule the corpus sync".

`corpus_sync_job()` returns a `ScheduledJob` an operator's configuration or a
console can hand straight to `ScheduleStore.upsert_job`, idempotent by
construction, carrying the source and the team. That is what
`knowledge_sync_job` and `topology_discovery_job` are, and it is the precedent
this follows.

**What does not exist, in this feature or before it.** `platform/scheduler/` runs
*investigations*: `JobExecutor.execute` starts a run and drives the pipeline.
There is no dispatcher that looks at a job's `kind` and calls something other
than the investigation pipeline — which is why `knowledge.sync` and
`topology.discovery` have had definitions and no runner since they were written.
Building one is a scheduler change affecting every job kind, not a corpus
change, and doing it inside this feature would have been the second time a
generic dispatcher was smuggled in under a specific need.

The half that was missing and is now built is the one the handoff was actually
about: the candidates have somewhere to arrive.

`<!-- handoff: to=062-data-ingress-and-delivery what="give the scheduler a dispatcher keyed on job kind, so knowledge.sync, knowledge.corpus_sync and topology.discovery run rather than only being registerable; three definitions have had no runner since they were written" -->`

`<!-- handoff-done: id=7f7483fe -->`

---

## 9. Chain validation refuses only what the write introduces

**Planned.** The handoff from 059 asks that a write be validated "against the
resolved chain rather than the node's own document, so a bound like
`OPERATING_CONTEXT_TOKEN_BUDGET` is refused at the write that crosses it".

**Done.** `ConfigService._validate_chain`, running after the node-local
validation on every `set_settings`, and refusing only the errors the write
*adds*.

**Why the subtraction is not optional.** A chain can already be over budget:
every node's document was within budget on its own, which is how 059's §9
describes the state, and they were stored before this check existed. Validating
the merged result without subtracting what is already broken would refuse every
unrelated edit anywhere beneath the overage — so the person fixing a typo three
levels down would be told to shorten somebody else's paragraph, and the first
thing they would do is look for a way round the check.

**The merge is the preview's.** `preview.merged_with` was extracted from
`preview_of` and both now call it. Two implementations of "what would this node
resolve to if its document were X" is how a preview and a save come to disagree,
which is the failure 058 built the preview to avoid.

`<!-- proof: tests/unit/platform/config_service/test_chain_validation.py::test_a_write_that_only_crosses_the_bound_once_merged_is_refused -->`
`<!-- proof: tests/unit/platform/config_service/test_chain_validation.py::test_an_unrelated_edit_below_an_already_broken_chain_still_works -->`

`<!-- handoff-done: id=18c62fd7 -->`

---

## 10. The bridged catalogue is re-deferred, and this says why

**Asked for.** 060's handoff: "compose a bridged catalogue at the gateway and
serve it, so an MCP server's tools appear in the capability catalogue with their
origin, their classification and their server's health."

**Not done here.** `capabilities/protocols/catalogue.py::bridged_catalogue` still
has no production call site.

**Why not, in one sentence each.** Composing it means a `ProtocolAdapter` per
registered server, reached over the network, on a route the console reads on
every page load. That needs three things this feature has no reason to hold: a
live adapter composed at the gateway, a cache with a stated staleness, and a
timeout policy per server — and getting any of them wrong turns a console read
into a fan-out of network calls with no ceiling. 060 called it "a piece of work
rather than a route" and that was the right reading.

**Why it is not this feature's.** Nothing about it touches a proposal. 060 handed
it here because 061 was next, not because the two share a mechanism; the honest
version of "061 owns the proposal surface" does not extend to owning every open
console read.

**Where it belongs.** 062 is *"de onde veio, para onde vai"*: outside systems,
what they deliver, and whether they are answering. Its own scope already asks for
"estado ao vivo: última entrega recebida, contagem por janela, e as últimas
rejeitadas com o motivo" — which is the same shape as an MCP server's tools, its
classification and its health, and needs the same caching and timeout answers.
Building both once is cheaper and more consistent than building one here badly.

`<!-- handoff: to=062-data-ingress-and-delivery what="compose a bridged catalogue at the gateway and serve it — an MCP server's tools with their origin, their classification and their server's health — using the same per-source liveness, caching and timeout policy 062 already needs for ingress state" -->`

`<!-- handoff-done: id=0fa60227 -->`

---

## 11. The list-of-objects editor is re-deferred, and this says why

**Asked for.** 060's handoff: "give the configuration editor a way to change a
list of objects (`agents.subagents` is the first), then give the agent screen
click-through per specialist and a topology template applied through
preview-then-save."

**Not done here.** 058's editor still edits scalars only and still says so on the
screen.

**Why not.** It is three features wearing one sentence: a control for an ordered
list of objects (add, remove, reorder, edit a field of an entry), a
click-through per specialist on a screen this feature did not build, and a
template flow. The first is the hard one and it is hard for a stated reason —
058 §1 and §12: a list replaces entirely on write, so a control over one lets a
typo drop every entry but the one somebody retyped. Doing that safely means a
write that addresses an *entry* rather than the list, which is a change to the
configuration write path's shape rather than a control on a form.

**Why it is not this feature's.** The one thing 061 needed from a list of objects
— proposing a detector into `policies.observation.detectors` — is solved
correctly and narrowly by `DetectorProposalApplier`: it reads the list, merges
the one entry, and writes the whole back, so enabling one candidate cannot delete
the rest. That is the safe read-modify-write the generic control would need, in
the one place that needed it, and generalising it into a form control from here
would be designing the control against a single caller.

**Where it belongs.** 062 builds routing rules — "regras avaliadas em ordem, cada
uma dizendo: que sinais casam, para qual equipe vão, e o que acontece". That is
an *ordered list of objects in configuration*, edited by a person, and 062 cannot
ship without a control for one. `agents.subagents` becomes its second consumer
rather than its motivating case, which is the right order to design a control in.

`<!-- handoff: to=062-data-ingress-and-delivery what="build the configuration editor's control for an ordered list of objects — 062's routing rules are the motivating case — then apply it to agents.subagents, with click-through per specialist on the agent screen and a topology template through preview-then-save" -->`

`<!-- handoff-done: id=08dfec21 -->`

---

## 12. The proposals area is its own item in Settings

**Planned.** D2's "Mudanças propostas" with a counter, in the settings zone.

**Done.** `/proposals`, in `settings`, with the sidebar count and the dashboard's
attention band both fed from one read.

**Why not a tab of Approvals.** They answer different questions. Approvals is
"may the agent do this *now*"; this is "should the deployment be different
tomorrow". They are read at different times, often by different people, and the
spec's own §E is about the failure of hiding one behind the other: "uma fila que
só existe atrás de um item de menu é uma fila que cresce até alguém descobri-la."

**The count is one read, not one count endpoint.** `/v1/proposals/count` exists
and is served and tested — it is the cheap read for a client that renders no
rows. The console does not use it, because both surfaces that show the number
also show the rows: the sidebar badge is derived from the same
`loadAttention` list the dashboard band renders. One read means the badge and the
band cannot disagree, which is what the plan's "both read one count endpoint" was
protecting.

**The cost, as 058 and 059 both recorded.** The sidebar is in `Shell`, `Shell`
wraps every route, so a new navigation entry moves every screenshot. Twenty-three
baselines were recaptured.

`<!-- proof: console/tests/unit/surfaces/proposals.test.tsx -->`

---

## 13. Two ceilings are new, and one existing one is reused

`config/constants/proposals.py` adds `PROPOSAL_DECISION_TTL_HOURS` (72, against
the knowledge queue's 168) and `MAX_DECIDED_PROPOSAL_HISTORY` (200).

**Why the shorter expiry.** A knowledge proposal is text; deciding it late costs
nothing but delay. A configuration, context or detector proposal changes what the
deployment *does*, and it is justified by a recurrence somebody observed. A
decision taken a week after that recurrence is taken by somebody who no longer
remembers the cluster it happened on, which is not review.

`config/constants/proposals.py` is not re-exported from `config/constants/__init__.py`.
Four existing modules are not either (`console`, `hypervisor_scenarios`,
`signals`, `workflow`), and nothing asserts the re-export; adding one would have
meant touching a 2,400-line file for no reader.

---

## 14. What the queue does not do

- **No auto-apply, at any confidence.** Out of scope by the spec, and there is
  nothing in the code that could be turned on to get it: `apply` reads the store
  and refuses on anything but a recorded approval, and there is no path that
  writes an approval without a reviewer's identifier.
- **The queue does not decide on a pattern.** Three rejections of the same
  correlation key render as three rejections. The spec's insight — that the
  fourth attempt means either the reason is not being learned or the operator is
  wrong — stays human, because both readings are useful and a queue that
  auto-refused the fourth would have taken the decision away from the person the
  whole design exists to keep.
- **Proposal *generation* is unchanged.** What the agent proposes and when is the
  existing capability and the guidance synthesis. This feature is the human side.

---

## 15. The seal's proof was cited at a node identifier that does not exist

Found by the close step, after the feature was committed. Recorded here rather
than fixed silently, because the cause is a habit rather than a typo.

**What was wrong.** §3 cited
`test_screening.py::TestTheSeal::test_a_change_to_the_containment_is_refused`.
The test existed and passed; the *identifier* did not resolve. Two reasons, and
either alone is enough: the test was nested in a class, and it was parametrized,
so what pytest actually collects is four ids each ending `[guardrails]`,
`[masking]`, `[approvals]`, `[autonomy]`. A proof mark names one behaviour at one
identifier, and a class-qualified id is a form no other proof in this repository
uses — 220 marks across thirteen features, and this was the only one.

**What shipped.** The containment test is module level, not parametrized, and
**derives its cases from `SEALED_CONFIG_PREFIXES` instead of listing the four
again**. That last part is the reason this is a code change rather than an edit
to a comment. The old test named the sections that were sealed the day it was
written; a fifth prefix added to the seal would have been covered by nothing and
the suite would still have been green. Reading the constant means a section joins
the seal and its case exists in the same commit.

**The emptiness invariant is now its own test, and was proven by mutation.** §3
claims that an empty section or list is a change and that the leaf walker yields
empty containers for exactly that reason. That claim was only ever *incidentally*
covered — two of the four old parameters happened to hold `[]`. It is now
`test_emptying_a_sealed_section_is_a_change_like_any_other`, covering
`policies.<sealed> = {}`, `= []` and `.statements = []` for every sealed prefix.
Dropping the two `and values` guards from `_leaves` was tried against it: the
test fails, the other nine pass. Nothing else in the suite holds that invariant.

**Net coverage.** The old parametrized case is gone and nothing is lost with it:
the seal is path-based, so the realistic values it carried (`mode: observe`,
`enabled: False`) proved nothing the generated paths do not. Ten tests where
there were twelve, over strictly more of the seal.

`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_a_change_to_the_containment_is_refused -->`
`<!-- proof: tests/unit/platform/proposals/test_screening.py::test_emptying_a_sealed_section_is_a_change_like_any_other -->`

---

## 16. The visual baselines were captured against a stale build, and five of them were the 404 page

Also found by running `make verify` after the close step failed. Unrelated to the
proof mark, and a worse defect than it.

**What was wrong.** `console-visual` failed on twenty-five of twenty-six
baselines. Not a flake: two runs on the untouched commit produced the same
twenty-five, and the capture pins its clock to the dataset's own `captured_at`,
so there is no wall clock in the reading to vary.

**The tell was in the file sizes.** Five baselines committed in `99433c0` —
`agent-1440-light`, `agent-tools-1440-light`, `agent-autonomy-1440-light`,
`data-1440-light`, `team-context-1440-light` — were *byte-identical* at 55,727
bytes, across five screens that look nothing like each other. One of them had
been 389 KB the commit before. Opening it: **"There is no such page. The address
does not name an area of this console."** The 404.

**The cause.** That recapture ran against a stale `.next/standalone` build. The
routes did not exist in the built server, so the capture walked to `/agent`,
`/data`, `/team-context` and photographed the not-found page — and recorded it as
the truth. The sidebar in those images is the proof and the date stamp: no
**Proposed changes** entry, and no **Team context** either, so the build predated
059's screen as well as this feature's. Every *other* screen differed for the
same reason, by the width of the two missing sidebar entries, which is why the
count was twenty-five and not five.

**Why nothing caught it.** `accept` rewrites the baselines and then the suite
compares against what it just wrote, so a botched capture is self-consistent and
green. The gate can only compare an image to an image; it has no way to know one
of them is a screenshot of a 404. The commit is the review, exactly as
`console-visual-accept` says — and this one was not looked at.

**What shipped.** Recaptured against a current build. Twenty-five baselines
changed, twenty-six pass, and the five 404s are now the screens they were meant
to be — `agent-1440-light` back to 392 KB, `data-1440-light` to 325 KB. The
dashboard reads "15 items need you" over the two proposal rows, the sidebar
carries **Team context** and **Proposed changes 2**, and nothing in the set is
identical to anything else.

**Worth naming for the next feature that recaptures.** Look at the sizes in
`git show --stat` before committing baselines. Several screens arriving at the
same byte count is not a coincidence and is not compression; it is the same
image, and the same image is almost always an error page.

---

## 17. The e2e viewer could not decide, so the approval half of the queue never rendered

Found in the same `make verify` run, and the cause is one line of fixture.

**What was wrong.** Two of the three browser tests in `proposals.spec.ts` failed:
`approve-first` was not on the page, and neither was `approve` after the effect
had rendered. Both are inside `decidable`, and `decidable` was false.

**The cause.** The console gates the decision controls on `approval.review`,
which is what `POST /v1/proposals/{id}/decision` requires — the console is
correct and matches the gateway. The dataset's principal holds fourteen
permissions and that was not one of them, though its role is `owner` and the
roles fixture grants an owner `approval.review`. So the browser signed in as
somebody who may read the queue and may not answer it, and the suite was
asserting against a viewer the tests were never written for.

**Why it surfaced only now.** This is the first console surface to gate on
`approval.review`. The approvals screen next door gates on `remediation.approve`,
which the principal *does* hold — which is why the permission had never been
missed.

**What shipped.** `approval.review` added to the principal in all three
scenarios. The three were byte-identical before and are again: `empty` and
`first-run` serve no proposals at all, so nothing renders differently there, and
leaving them to diverge would only invite the question of why one owner may
review and another may not.

**What was deliberately not done.** No check that a principal's permissions match
its role's. The three principals hold a curated fourteen against the owner
role's twenty-nine — `org.manage`, `sso.manage`, `credential.write` and the rest
are absent on purpose, because the fixture is a *person to render as*, not a
transcript of the role table. A guard asserting the two agree would have to be
satisfied by granting all twenty-nine, which changes what every screen shows to
fix a one-line omission.

`<!-- proof: console/tests/e2e/proposals.spec.ts -->`

---

## 18. The dataset is generated, and the permission belongs in the generator

A correction to §17's first attempt, kept because the mistake is an easy one to
repeat.

`fixtures/scenarios/*/principal.json` was edited by hand. The suite caught it
immediately — `test_rebuilding_the_dataset_reproduces_what_is_committed` — and it
was right to: the three scenarios are *built* from
`tools/mockplane/dataset/served.py`, and a hand-edited fixture is one the next
`python -m tools.mockplane build` silently reverts.

`approval.review` now sits in `OPERATOR_PERMISSIONS`, which is the one list the
three principals are generated from. That is also the real answer to §17's
question of whether to change one scenario or all three: they are not three
files that happen to agree, they are one constant rendered three times.

---

## 19. Two things 061 added to the console were never added to what checks it

Both found by the same `make verify`, both older than this session's work, and
both the same shape: the feature added a surface and did not add it to the list
that walks surfaces.

**The deploy walk did not know `/proposals` existed.**
`test_the_deploy_walk_covers_exactly_the_areas_the_console_declares` compares the
console's declared areas against `SHELL_PATHS` in `tools/console_smoke.py`, and
reported `declared but not walked: ['/proposals']`. The smoke walk is what opens
every screen against a real deployment and requires 200 from each; the one screen
this feature exists to build was the one screen it did not open. Added, in
sidebar order, after `/team-context`.

**The dataset could not answer a decision.** `proposal-decision` was declared in
`tools/mockplane/endpoints.py` as an endpoint the console consumes, and nothing
in the dataset served it — so three contract tests failed and the only thing a
person can *do* on the proposals screen was unreachable in every environment
backed by fixtures. `proposal_records()` now serves one per proposal, `POST`,
shaped as `DecisionResult` really is: `proposal_id`, `state`, and the `applied`
sentence the owning path returns, spelled the way `ConfigurationProposalApplier`
spells it.

**What the two have in common, worth saying once.** The screen, its route, its
component tests and its browser tests all existed and all passed. What was
missing both times was the *registration* — the entry in the list that some other
check iterates. A feature is finished when the things that enumerate the system
know about it, and neither of these would have been caught by writing another
test of the screen.

`<!-- proof: tests/contract/console/test_console_shell.py::test_the_deploy_walk_covers_exactly_the_areas_the_console_declares -->`
`<!-- proof: tests/contract/fixtures/test_dataset_contract.py::test_every_console_consumed_endpoint_has_a_fixture -->`
