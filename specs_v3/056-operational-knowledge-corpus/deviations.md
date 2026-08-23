# Deviations — 056 The written history

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each acceptance item is proven

The definition of done asks for six things. These are where each is asserted.

| Item | Where it is proven |
|---|---|
| 1. The corpus ingests with path-derived classification | `tests/unit/platform/knowledge/base/test_corpus_source.py::TestClassificationComesFromThePath` and `tests/unit/platform/knowledge/base/test_corpus_sync.py::TestOneRunOverTheWholeCorpus::test_every_allowed_document_is_stored_with_its_derived_type`. The real corpus's counts are **not** recorded — see §8 |
| 2. "AdGuard DNS" returns both post-mortems and the runbook, the explaining one marked | `tests/unit/platform/knowledge/base/test_corpus_search.py::TestSearchingForTheSymptom` (five assertions). The live transcript is **not** recorded — see §8 |
| 3. Re-sync without change creates no version; an edit creates one | `tests/unit/platform/knowledge/base/test_corpus_sync.py::TestReSyncing` (four assertions, including `touch`) |
| 4. A resource resolves to the documents naming it | `tests/unit/platform/knowledge/base/test_estate_links.py`, `tests/unit/gateway/http/test_resource_documents.py`, `console/tests/unit/surfaces/resource-documents.test.tsx` |
| 5. The credential fixture is refused by name, the value nowhere | `tests/unit/platform/knowledge/base/test_corpus_sync.py::TestTheDocumentCarryingACredential` (six assertions: report, log, stored chunks, and the document row) |
| 6. The verification queries exist as disabled candidates with source excerpts | `tests/unit/platform/knowledge/base/test_detector_candidates.py`, `tests/unit/gateway/http/test_proposed_detector_routes.py`, `console/tests/unit/surfaces/detector-candidates.test.tsx` |

<!-- proof: tests/unit/platform/knowledge/base/test_corpus_source.py::test_a_path_classifies -->
<!-- proof: tests/unit/platform/knowledge/base/test_corpus_sync.py::test_the_value_reaches_no_log_line -->
<!-- proof: tests/unit/platform/knowledge/base/test_corpus_sync.py::test_touching_every_file_changes_nothing -->
<!-- proof: tests/unit/platform/knowledge/base/test_corpus_search.py::test_the_entry_that_carries_the_cause_is_ranked_above_the_one_that_does_not -->
<!-- proof: tests/unit/platform/knowledge/base/test_estate_links.py::test_a_document_naming_a_resource_writes_one_edge -->
<!-- proof: tests/unit/gateway/http/test_resource_documents.py::test_the_detail_lists_the_documents_that_mention_this_resource -->
<!-- proof: tests/unit/gateway/http/test_proposed_detector_routes.py::test_nothing_it_would_find_reaches_the_observations -->
<!-- proof: tests/synthetic/test_postmortem_extraction_ablation.py::test_structural_alone_recovers_thirty_seven_of_forty_one_fields -->

---

## 1. The fixture corpus is under `tests/corpus/`, not `fixtures/`

**Planned.** `tasks.md` T-001 and the constitution check both say a fixture
corpus committed under `fixtures/`.

**Done.** `tests/corpus/operational/`, twenty-eight files.

**Why.** `fixtures/` is not a general fixture directory. It is the mock data
plane: a generated dataset with `manifest.json`, `contract/openapi.json`, a
builder (`python -m tools.mockplane build`) whose output is asserted byte-for-byte
against what is committed, and — decisively — an adversarial scan,
`tools/mockplane/verify/identifiers.py::scan_tree`, which walks every `.md`,
`.json` and `.txt` under that root looking for credential shapes and private
addresses.

Acceptance item 5 requires a fixture file that **carries a credential**. Putting
it under `fixtures/` would have put a deliberate credential-shaped string inside
the tree whose whole purpose is that no such string is there, and
`python -m tools.mockplane verify` would have failed on it. The two requirements
are directly incompatible, and the corpus is test data rather than console data.

`tests/synthetic/proxmox/` is the precedent: a committed corpus of test data
under `tests/`, with its own loader and its own shape.

**One thing this cost.** `.gitignore` needed one negation
(`!tests/corpus/operational/.env.local`), because `.env.*` is ignored repository-
wide and that decoy exists precisely so a test can say the corpus source never
opens one. The values in it are invented.

---

## 2. `DocumentType` gained `POLICY` and `REFERENCE`; there is no `DECISION`

**Planned.** `plan.md`: "`docs/adr/*` → DECISION, `policies/**` → POLICY … If
`DocumentType` lacks POSTMORTEM/POLICY members they are added".

**Done.** `POSTMORTEM` already existed. `POLICY` and `REFERENCE` were added.
`docs/adr/*` maps to the existing `ARCHITECTURE`.

**Why no `DECISION`.** An architecture decision record *is* an architecture note
— it is the document that records intent and the reasoning behind it — and the
enumeration's own docstring already says "an architecture note describes intent".
`platform/knowledge/base/sync/git.py::TYPE_DIRECTORIES` has mapped `adr` to
`ARCHITECTURE` since that adapter shipped. Adding a synonym would have given the
corpus two names for one kind and made the two Markdown sources disagree about
what an ADR is.

**Why `REFERENCE` rather than reusing `PROCEDURE`.** The plan asks for "a general
type" for the rest of `docs/`. In the real repository that is `analysis/`,
`plans/`, `prd/`, `specs/` and `migration/` — project context. `PROCEDURE` means
"an operational routine", and filing a capacity review as one would make it a
thing an agent might follow. `REFERENCE` is the one kind an agent must *not*
follow, which is why it needs a name of its own rather than the `RUNBOOK`
default. The docstring says all of this.

**No closed-enum test needed updating.** The plan anticipated one
(043-deviations' precedent for editing a closed taxonomy test); there is none for
`DocumentType`. Nothing was edited to accommodate the new members.

---

## 3. The document↔resource edge runs resource → document, and is a new kind

**Planned.** `plan.md` Scope C: "topology edges (document node → resource node)".

**Done.** `EdgeKind.DOCUMENTED_BY`, from the **resource** to the document, plus
`NodeKind.DOCUMENT`.

**Why the direction is reversed.** The topology port has exactly one method that
returns edges, `edges_from`, and it walks outward. The question this feature
exists to answer is "what has been written about *this resource*", asked from the
resource. With the edge pointing the other way that question would need either a
new port method (a change to the port, both backends, and the contract suite) or
a full traversal. Written from the resource, it is one existing call.

**Why a new kind rather than `DEPENDS_ON`.** A document cannot fail. Reusing a
dependency kind would put a runbook in a resource's blast radius, and "what does
this outage take with it" would answer with a document. `DOCUMENTED_BY` is
excluded from every dependency traversal exactly as `INVOLVED` is —
`platform/persistence/fakes/topology_graph.py::UNTRAVERSED` and
`platform/persistence/postgres/graph/queries.py::UNTRAVERSED_KINDS`, which is now
a named set rather than one spelled-out exclusion repeated in six statements.

**What this changed in a shared port.** `TopologyGraph.edges_from` gained a
keyword-only `kinds` filter, defaulting to the empty tuple, which means the
dependency edges — the reading reconciliation makes, unchanged. Naming kinds
returns exactly those, including the untraversed ones. Both backends implement
it; `tests/unit/platform/knowledge/base/test_estate_links.py::TestWhatTheGraphHolds::test_the_edge_is_only_returned_when_it_is_asked_for_by_kind`
asserts both halves.

**What is not asserted.** `NodeKind.DOCUMENT` is written and no test reads it
back, because the port's `upsert_node` merge takes the *given* kind when it is
set and a bare read-back node's kind is `SERVICE`. There is no `get_node`. The
node's `name` and properties are asserted; what the kind buys — that no traversal
treats a document as infrastructure — is asserted directly, on the traversals.

---

## 4. Matching is by fully-qualified name only, never by display name

**Planned.** `spec.md`: "The link is by hostname and by domain".

**Done.** Exactly that, and the decision is worth recording because the
alternative is tempting: matching a resource's `display_name` would have linked
far more documents.

**Why not.** Half of any estate is called something like `backup`. A document
containing the word would attach itself to a resource it is not about, and a
wrong edge costs more than a missing one — the missing one costs a search, and
the wrong one costs an investigation reading a runbook for a different machine.

Two boundary rules earned their own tests after failing in development:

- **A name at the end of a sentence is still a name.** `host-adguard.example.invalid.`
  is the commonest way a hostname appears in prose, and the first boundary rule
  silently missed every one of them.
- **The tag form counts.** A workload's tag (`host-<name>`) is what an operator
  copies into a runbook when writing down which machine they mean, so both the
  bare name and the tagged form match — while `not-adguard.example.invalid` and
  `adguard.example.invalid.example` still do not.

---

## 5. Detector candidates are returned as a configuration *patch*, never written

**Planned.** `plan.md` Scope D: "candidates are stored as ordinary detector rows
with `enabled=false` and an `origin` naming the document".

**Done.** They are ordinary detector rows —
`DetectorSettings`/`DetectorDeclaration` gained `origin` and `origin_excerpt`,
and `DetectorDeclaration.proposed` is `origin` being set. What the sync does not
do is write them.

**Why.** A detector is configuration, not a row: `DetectorService.settings_with`
already establishes that even a *toggle* is a configuration patch rather than a
mutation, "because persisting the change is a configuration write and the
configuration service owns those — including the audit line, the field locks, and
the approval gate". A sync that wrote detectors around that service would be a
document changing what a deployment watches with no record of who agreed. So
`CorpusSync` returns the candidates and `settings_patch()` returns the document
the configuration service takes.

**What this means for the definition of done.** Item 6 — "the verification
queries exist as disabled candidate detectors with source excerpts" — is met
end to end: `tests/unit/gateway/http/test_proposed_detector_routes.py` writes
them through `PUT /v1/config/{node}` exactly as an operator's own detector is
written, then asserts the row is listed as a proposal, that a dry run shows what
it would have found, that nothing it would find reaches `/v1/observations`, and
that enabling it is the ordinary route.

**What this leaves genuinely open.** Nothing in the shipped code calls
`settings_patch`. See §14 — that is the spec's own requirement rather than an
omission, but the proposal still has nowhere scheduled to arrive.

**One thing left deliberately undecided.** A candidate carries a firing value and
no hysteresis, because the document states one number. `declaration_of` defaults
the clear value to the firing value, which is the declaration the document
actually supports. Choosing the gap is part of what the operator is being asked
to decide, and inventing one here would hide that decision inside a proposal.

---

## 6. `CorpusSync` exists, and its implementation was written before its tests

**Planned.** Nothing in `tasks.md` asks for a composed entry point; the four
scopes are separate modules.

**Done.** `platform/knowledge/base/sync/corpus_run.py` — one pass that ingests,
links, proposes, and reports what degraded, in that order.

**Why it exists.** Without it the feature is four mechanisms and no way to run
them, and the order between two of them is load-bearing: a document refused at
the ingestion boundary must not reach the graph, so the link pass reads the
sync's own report rather than the source's output. That property has nowhere to
live except in the thing that sequences them.
`tests/unit/platform/knowledge/base/test_corpus_run.py::TestTheRefusedDocumentReachesNothing`
is the assertion.

**Why this is a deviation.** `CLAUDE.md`: "the failing test lands before the
implementation, and is confirmed failing." For this module the implementation was
written first and the tests immediately after, and they passed on the first run.
Their value as regression tests is established; their value as specifications of
behaviour that did not yet exist is not. Every other module in this feature was
written test-first with the failure confirmed — see §7 for the two other places
that claim needs qualifying.

---

## 7. Three test files passed on their first run because the mechanism already existed

**Planned.** T-004 and T-005 are written as "failing tests … then implement the
sync loop".

**Done.** The tests were written first, run first, and passed first —
`tests/unit/platform/knowledge/base/test_corpus_sync.py`, all twelve.

**Why.** There was nothing to implement. `plan.md` predicted this in as many
words: screening, the chunk ceiling, content-based idempotence and versioning are
all inherited from `KnowledgeIngestor.ingest` and `KnowledgeSync.run`, and the
corpus source is an ordinary `DocumentSource`. The tests are therefore
*acceptance* tests over inherited behaviour rather than specifications of new
behaviour, and they are worth having as exactly that: nothing else in the suite
asserts that a corpus-shaped document carrying a credential is refused with the
value in neither the report, the log, the stored chunks, nor the document row.

The same is true of `tests/synthetic/test_postmortem_extraction_ablation.py`
(T-009), which is a measurement rather than a behaviour, and where a red phase
would have been meaningless.

---

## 8. The real cluster corpus was never synced, and no live transcript exists

**Planned.** T-013: "Against the cluster: sync `/root/infra-cluster` `docs/` +
`policies/`; record in deviations the counts (54 runbooks, 10 post-mortems, 3
ADRs), any rejected file, and the AdGuard search transcript." The definition of
done's items 1 and 2 both name the live run.

**Not done, and it could not be.** There is no `/root/infra-cluster` on this
machine, and no copy of it anywhere on the filesystem. The repository the spec
describes is not present in this environment.

**What stands in for it.** `tests/corpus/operational/` is shaped like the real
tree — the two AdGuard post-mortems with their heading structure and their
recurrence link, an ADR set, firewall policy YAML, and the decoys that matter
(`.env.local`, tofu state, a lockfile, a shell script, a `.txt`, a `.bak`, and a
`README.md` under `policies/`). Twenty of twenty-eight files are readable; one of
the twenty is refused for credential material; nineteen are stored. The ten
post-mortems are real in number, because the ablation needed ten.

**What is therefore genuinely unproven.** That the real corpus's fifty-four
runbooks classify as runbooks; that its ten post-mortems all carry headings this
extractor reads (the ablation says one in ten of the *fixture* does not, which is
a guess at the real rate rather than a measurement of it); that fifteen thousand
files stay under `MAX_CORPUS_FILES` once `docs/` and `policies/` are the only
roots walked; and that a live search for "AdGuard DNS" ranks as the fixture one
does. Everything the mechanism can be asserted to do without the cluster is
asserted. Nothing here has met the corpus it was written for.

**Why this is a deferral and not a handoff.** There is no later feature whose
scope this belongs to. Syncing the real corpus is an operational run of *this*
feature, not work for 057 or 058 or 061, and handing it to one of them would be
filing it under a scope that does not contain it. It is instead an instance of
something the whole wave keeps hitting: a mechanism built against fixtures
because the cluster it was written for is not reachable from where the work
happens. 049 recorded the same shape for its hypervisor laboratory.

<!-- defer: theme=live-cluster-verification -->

---

## 9. `Document` gained a metadata bag, and it is outside the checksum

**Planned.** `plan.md` Scope B: "extracted fields land in the document's metadata
bag (the metadata-key pattern of `platform/knowledge/base/models.py`)".

**Done.** `Document.metadata`, stored under a single `EXTRA_KEY` inside the
stored bag rather than as fields spread across it.

**Why one key.** `from_stored` would otherwise need a blocklist of the seven
known keys to know what was "extra", and that list is one member behind whatever
last wrote a document. One sub-mapping round-trips without anything to keep in
step.

**Why it is outside the checksum.** The checksum is over the body, and it is what
decides whether a document is a new version. An extractor that improved — a new
heading alias, a model that answers better — would otherwise supersede every
post-mortem in a corpus nobody edited, at one re-embedding pass each.

---

## 10. Search re-ranking moves post-mortems against each other and nothing else

**Planned.** T-008: "querying the AdGuard symptom returns both post-mortems and
the recovery runbook, with the entry carrying the root cause distinguishable in
the result shape."

**Done.** Both: `RetrievedChunk.postmortem` and `.explains` are the result shape,
and `explaining_first` reorders.

**Why the re-rank is as narrow as it is.** It moves post-mortems only among the
positions post-mortems already occupied. A runbook stays exactly where similarity
put it, and a result with fewer than two post-mortems is returned untouched.
Anything wider would be this module deciding that a document's metadata outranks
how well it matched the query, which is a ranking model rather than a tie-break.
`tests/unit/platform/knowledge/base/test_corpus_search.py::TestTheRankingIsNarrow`
asserts both the untouched case and that two runs of one query agree.

**One judgement that is load-bearing.** A heading called "Root cause" under which
somebody wrote *"Not established."* is a section and not a cause. `explains`
checks the text against `NO_CAUSE_PHRASES` before answering, because treating any
such heading as a cause is exactly what would rank the entry that found nothing
above the one that found everything — which is the failure this whole scope
exists to prevent.

---

## 11. The gateway test file was renamed to avoid a basename collision

`tests/unit/gateway/http/test_detector_candidates.py` and
`tests/unit/platform/knowledge/base/test_detector_candidates.py` collided:
the tree has no `__init__.py`, so pytest imported one and refused to collect the
other — the footgun 038-deviations §16 records. The gateway file is now
`test_proposed_detector_routes.py`. It passed alone and failed the suite, which
is the only way this is ever noticed.

---

## 12. The two ablation numbers

`tests/synthetic/test_postmortem_extraction_ablation.py`, over the ten
post-mortems, scored against a human reading of which fields each document
actually answers:

| Arm | Fields recovered | Documents naming a cause | Model calls |
|---|---|---|---|
| structural only | **37 / 41 (90.2%)** | 8 of 9 | 0 |
| structural, model fallback | **41 / 41 (100%)** | 9 of 9 | 1 |

The model earns four fields and one document, for one call over the whole corpus
— cached by checksum, so a re-sync of an unchanged corpus costs nothing. A
deployment with no provider configured loses those four fields and is told which
document it lost them on, by name, in the sync report.

The number is pinned rather than bounded. A change that moves it is a change to
what the corpus gets for free, and it should be read rather than absorbed.

---

## 13. Two constants the plan asked for, and what exceeding each one does

`plan.md` II: "file-count/size limits for the sync as named constants". They
behave differently on purpose.

- **`MAX_CORPUS_FILES`** refuses the whole run, naming the constant. The case it
  catches is a source pointed at a repository root rather than at its
  documentation directory, and the honest answer to that is to stop rather than
  to embed the first two thousand lockfiles it reached.
- **`MAX_CORPUS_FILE_BYTES`** skips one file, naming the constant in the reason
  and the file in the report. One manual that happens to end in `.md` must not
  stop sixty-six runbooks syncing.

---

## 14. Nothing calls `settings_patch`, and that is the design rather than an omission

**Found by the done-auditor**, and it is a fair thing to have asked: no shipped
code path applies the candidate detectors. `CorpusSync.run` returns them;
`settings_patch` renders them as a configuration document; the only caller of
either is a test.

**Why it is correct as it stands.** `spec.md` is explicit: "Esta spec não as
transforma em detectores automaticamente — propõe cada uma como candidata, com o
texto de origem, para um humano habilitar." A corpus sync that wrote detectors
into a team's configuration would be doing exactly the thing the scope forbids,
and it would do it through a service — the configuration service — whose entire
job is that a change to what a deployment watches has a name attached to it.

**Why it is nevertheless a gap worth naming.** "Proposed" needs somewhere for
the proposal to arrive. Today it arrives in `CorpusReport.candidates`, which is a
return value: a caller has it, and there is no scheduled corpus-sync job in this
feature to be that caller. Composing one — a job kind, a schedule, and the
surface an operator reviews the queue on — is composition rather than mechanism,
and this feature builds the mechanism.
`tests/unit/gateway/http/test_proposed_detector_routes.py` is what stands in for
the missing caller: it writes the candidates through the real
`PUT /v1/config/{node}` route, exactly as the absent job would, and then asserts
every property the definition of done asks for against a running gateway.

<!-- handoff: to=061-proposed-changes what="schedule the corpus sync and give its detector candidates a review queue; 061 declares a dependency on 056 and reuses the disabled-with-origin detector shape, so the proposal surface belongs there" -->

---

## 15. The proof marks named a class, and the mark grammar has no room for one

**Found by the close step**, which rejected six of this feature's eight `proof`
marks with "does not exist — write the test or drop the claim". All six tests
existed, passed, and still do. The claims were true; the *references* were
unreadable to the thing that reads them.

**What was written.** `tests/…/test_corpus_sync.py::TestReSyncing::test_touching_every_file_changes_nothing`
— a full pytest node id, three segments.

**What the grammar is.** A `proof` mark takes `tests/path.py::test_name` — two
segments: a path, and a test's name. (Spelled out rather than shown, because a
second literal mark in this file would itself be read as a claim, and a grammar
example is not one.)

**Why the three-segment form cannot work.** The resolver is not pytest. Every
one of the six node ids collects — `pytest --collect-only` names all six, and
running them passes 15 tests — so a collection-based checker would have found
them. It matches on the test's *name* instead, and given three segments it
searches for a test literally called
`TestReSyncing::test_touching_every_file_changes_nothing`, which nothing is.

**What settled the fix.** Across every `deviations.md` in the repository there
are 66 accepted two-segment Python marks and 14 accepted path-only marks, and
this feature held the only six three-segment marks ever written. Two things
follow. Nesting is not the problem: the two accepted marks in
`console/tests/e2e/shell.spec.ts` name tests that sit *inside* a
`test.describe` block, with the group omitted from the mark — the resolver
finds a test by name at whatever depth it lives. The extra segment is the
problem.

**Done.** The six marks drop the class and keep the test:
`tests/…/test_corpus_sync.py::test_touching_every_file_changes_nothing`. Each
of the six names occurs exactly once in the file it names, so nothing is
ambiguous. No test was moved, renamed, split, or weakened, and no claim was
dropped — the behaviour these marks assert is the behaviour that was already
asserted, cited in the form the reader supports. The table in §*Where each
acceptance item is proven* still names the classes, which is where a human
wanting the precise location should look.

**What this cost, and the general lesson.** One close cycle, for a punctuation
mismatch between two ways of naming the same test. The node id is the form
every other tool in this repository takes — `pytest`, the failure output, the
IDE — so reaching for it here was the natural mistake rather than a careless
one. It is worth knowing that this one reader wants the shorter form.

---

## Gates

`make lint format-check typecheck check-imports check-constants` green
throughout.

`make verify` green, twice: **13,190 passed, 25 skipped** — 429s on the first
run, 408s on the re-run. The identical counts are the useful part: pytest
collects from the filesystem rather than from git, so both runs saw the same test
set including `test_corpus_run.py`, which was on disk and untracked during the
first.

Re-run after the §15 mark correction, on the final tree: **13,190 passed, 25
skipped**, 408s, exit 0 — the same counts as both earlier runs, which is what a
change confined to a gitignored document should produce. The six tests the close
step called missing were run directly first and pass: 15 tests, counting the
eleven parametrisations of `test_a_path_classifies`.

One commit landed after the second run — `ac10f0d`, which deletes a helper
nothing called. `lint`, `format-check`, `typecheck`, `check-imports` and
`check-constants` are green on the final tree, as are every suite that commit
could reach: `tests/unit/platform/knowledge`, `tests/unit/platform/observation`,
both gateway route files, `tests/contract/persistence`, and the ablation — 629
passed, 16 skipped. The close step runs `verify` again regardless.

`make test-postgres` green: **471 passed, 15 skipped**, 298s, against a real
PostgreSQL. This matters for this feature specifically — the knowledge store's
metadata bag changed shape (`EXTRA_KEY` round-tripping through JSONB) and the
topology graph gained an edge kind that every dependency traversal has to
exclude, in hand-written recursive SQL rather than in the fake's Python. Both are
exactly what that suite exists to catch, and both hold against the real store.

### Determinism

The previous wave shipped a suite whose two runs disagreed, so this one was
checked rather than assumed. Every test file this feature touches was run three
times over — 216 passed, three times, no reordering of outcomes — and the console
pair twice. The one file with a genuine wall-clock dependency,
`test_proposed_detector_routes.py` (signals at real timestamps, a dry run against
`datetime.now`), was run five times on its own.

Four things were pinned rather than left to chance while writing them:

- **The corpus's own order.** `CorpusSource.readable` sorts. A filesystem
  promises no order, and `rglob` returns whatever the directory gives it, so two
  syncs of an unchanged tree would otherwise produce reports that diff.
  `test_corpus_source.py::TestWhatTheSourceEnumerates::test_the_order_is_the_same_twice`.
- **The search's order.** `explaining_first` is a stable partition, not a sort on
  a float, and `…::TestTheRankingIsNarrow::test_the_same_query_twice_returns_the_same_order`
  asserts the chunk ids match between two runs of one query.
- **The link order.** `mentioned_resources` returns matches in the estate's own
  order rather than in the order the names happen to appear in the text.
- **The extraction.** Structural extraction is a pure function of the body, and
  the ablation asserts both arms score identically twice
  (`test_both_arms_score_the_same_twice`) — a measurement whose two runs disagree
  is not a measurement.

**A correction.** An earlier draft of this file recorded `make test-postgres` as
not run, "because this environment has no Docker daemon available to the task".
That was wrong and was not checked before it was written — Docker was available.
This is the same mistake 038-deviations §0 records, made again: reporting a gate
as unrunnable on an assumption rather than on a check. The gate has now been run
and is green; the wrong sentence is left recorded here rather than quietly
replaced.
