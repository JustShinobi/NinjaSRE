# Deviations — 032 Mock Data Plane

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. T-015 — the capture was not run against a live cluster

**Planned.** "Run both captures against the reference cluster."

**Done.** The capture is fully implemented — both sources, the allowlist, the
projection, the provenance, the missed-endpoint report — and it was *not* run.
The committed dataset was produced by running the declared shape of the survey
through the same pipeline instead.

**Why.** This feature was implemented autonomously, on a machine with no route
to the reference cluster, no SSH identity for it, and no running NinjaSRE
deployment to record. FR-001g is explicit that the identity is supplied at run
time and never written down; there was nothing to supply it with. Faking a
connection would have produced fixtures that claimed to be a recording and were
not — which is precisely the failure mode FR-001d and the provenance test exist
to prevent.

**What was done instead.** `tools/mockplane/dataset/profile.py` declares the
measured shape of the deployment — the counts, the ratio between kinds, the node
skew, the per-volume fill, the datastore statuses, the thin-pool metadata
percentage, the backup jobs and their coverage, the failed-unit sets, the
pending packages, the quorum arithmetic. Every number is what the survey
recorded. Every *name* is a pseudonym, because the survey is not in this
repository and its identifying values never were. That profile goes through
`capture.projection.project` — the same function the live capture's output goes
through — and then through `anonymise.pipeline.process`, which is the only path
into the fixture tree and is asserted to be so by
`tests/architecture/test_one_fictional_deployment.py`.

**What this costs.** The capture's transport is exercised against a recorded
runner rather than a real one, so the one thing not proven here is that `ssh`
and `pvesh` behave as expected on a real node. Everything downstream of the
transport — the parsers, the projection, the provenance, the missed-read report,
the refusal of a command outside the allowlist — is proven against recorded
output in `tests/unit/tools/mockplane/`.

**What has to happen next.** Somebody with access runs
`python -m tools.mockplane capture` against the reference deployment and cluster,
then `python -m tools.mockplane build` from the result, and diffs the committed
dataset against it. That is a one-command operation by design, and NFR-004 is
what makes it routine rather than an event.

---

## 2. The OpenAPI document is generated here, because nothing generated it before

**Planned.** The technical-context table says validation uses "the gateway's
committed OpenAPI document, the same copy feature 033 generates the client from".

**Done.** There was no committed OpenAPI document anywhere in the repository.
This feature generates one from the real `create_app`, commits it at
`fixtures/contract/openapi.json`, and adds `python -m tools.mockplane contract`
to regenerate it.

**Why this rather than validating against the live application.** Validating
against `create_app(...).openapi()` directly would have been simpler and would
have caught drift the moment it happened — but it would also have meant the
fixture set had no committed statement of what it was validated against, so a
fixture and a route could change together and nothing would notice. The
committed document is the statement; a drift test
(`test_the_committed_document_is_what_the_application_generates`) keeps it equal
to what the routes produce, so a route change fails the build rather than
silently redefining the contract.

**The projected half needed a second document.** The estate, observation and
Proxmox endpoints do not exist, so no generator can produce their schemas.
`fixtures/contract/projected.json` declares them by hand in the same dialect, and
two tests keep it honest: the projected paths must be exactly the projected
endpoints, and none of them may appear in the gateway's own document. When one of
them is really served, it is deleted from both files by the same change.

---

## 3. The JSON Schema validator is written here rather than depended upon

**Not in the plan at all.** FR-016 asks that fixtures validate against the
OpenAPI document; nothing says how.

**Done.** `tools/mockplane/contract.py` implements the subset of JSON Schema that
FastAPI actually emits — objects, arrays, the scalar types, `enum`, `const`,
`anyOf`/`oneOf`/`allOf`, and `$ref` into `components/schemas`.

**Why.** `jsonschema` is not in this repository's dependency tree, and Article X's
"the operator owns their data" is enforced by `make check-deps` over that tree.
Adding a package so a development fixture can be checked is a package every
operator then has to audit. The subset is about a hundred and fifty lines, and
anything outside it raises rather than passing silently — a validator that
quietly accepts what it does not understand is worse than no validator, and that
is asserted.

---

## 4. Phase 7's console wiring is against the Python console, because that is the console

**Planned.** Phase 7 is "gated on 033 standing the toolchain up", and T-046/T-047
wire "the console development loop" and "the console test harness" to the mock.

**Done.** Both, against `surfaces/console` — the server-rendered Python console
that feature 021 shipped. `python -m tools.mockplane console` starts the mock and
the console in front of it in one process, and
`tests/contract/fixtures/test_console_against_the_mock.py` drives the real
`Console` against the mock across every screen and three scenarios.

**Why.** Feature 021's own deviations record why the console is Python rather
than TypeScript; the short version is that `make verify` is the definition of
done and it is Python-only. Waiting for 033 would have left this feature's
handover phase unproven, and there is a console to wire *now*. When 033 stands a
TypeScript toolchain up, the mock it points at is this one: the mock is an ASGI
application on the gateway's own paths, so it does not care what is in front of
it.

---

## 5. Two defects the checks found, both fixed rather than worked around

Recorded because they are the argument for writing the verification before the
pipeline, which is what the task order asked for.

**The credential denylist was destroying the dataset.** Removing any field whose
name carried `token`, `credential` or `secret` took out `tokens` (a list of
records), `token_id` (an identifier every reference depends on), `total_tokens`
(a count) and `credential_fields` (a form schema). The contract validator named
every one. The rule is now two-part and stated as such: only a *string* is
removed, and a key ending in an identifier suffix is exempt. A credential in a
JSON payload is a scalar; a list called `tokens` is a collection.

**The timestamp shift was anchoring on the wrong instant.** Moving the *latest*
timestamp onto the reference instant meant one machine token expiring a year out
dragged the whole history three hundred and twenty-five days into the past — so
every episode appeared to have been created before the run that produced it, and
the plausibility check said so. The shift now anchors on the moment the capture
was taken, which is passed in.

A third, smaller one: the referential check caught anonymisation breaking a
reference — `principal_id` was pseudonymised and `user_id` was not, so every
grant named nobody. That is the exact edge case the spec lists ("two names that
had to stay equal").

---

## 6. Anonymisation is idempotent, under a flag that only the builder sets

**Not in the plan.** Nothing says what happens when the pipeline runs over its
own output.

**Why it had to be decided.** The committed dataset is built by running an
already-pseudonymous profile through the pipeline. The field map recognises
`node` and deliberately does not recognise `name` — `name` means twenty things —
so a second pass renamed a node under one key and not the other, and the estate
ended up disagreeing with itself about what a node was called. The console joins
those two fields.

**Done.** `PseudonymBook(already_pseudonymous=True)` leaves a value that is
already in the book's own output shape alone, making the pipeline a fixed point
over its own output. It is **off by default and must stay off for a capture**,
because a real deployment may genuinely have a node called `node01` and passing
that through would be a leak. A test asserts both halves of that.

---

## 7. The adversarial scan runs in two nets, and only one of them can run in CI

**Planned.** T-024: "adversarial identifier scan taking the operator's real
values from a file outside the repository; fails the build on any match", and
"the identifier scan runs in the gate".

**Done.** The scan is in the gate and it is demonstrated to fail on a seeded real
value. But the operator's file is by definition not available to a contributor
cloning the repository, so what runs unconditionally is the **pattern net**:
private address ranges, private domain suffixes, manufacturer MAC addresses,
e-mail addresses outside the fictional domain, and credential-shaped values. The
operator's list is the second net and is supplied at scan time:

```bash
python -m tools.mockplane verify --identifiers ~/real-values.txt
```

**Why this is not a weakening of T-024.** The alternative readings were both
worse. A gate that required the file would be red on every clone. A test that
skipped when the file was absent would be a test that never ran. What is here
instead is a net that always runs and a stronger one that runs whenever somebody
has the list — and `test_a_seeded_real_value_is_found_and_named` proves the
stronger one works, in CI, on every commit.

---

## 8. Structure — modules the plan's phases imply and do not name

The plan describes seven phases; it does not name modules. These are where they
went, and the two that are not obvious:

| Module | Why it is its own module |
|---|---|
| `tools/mockplane/endpoints.py` | The catalogue *and* the gateway/projected split. T-003 says the split is data the capture reads rather than a comment; this is that data. |
| `tools/mockplane/identifiers.py` | Shared by the anonymiser (which replaces the values) and the scan (which hunts for them). One list, read once, or the two disagree about what is real. |
| `tools/mockplane/paths.py` | "Which directory" is the first question every other part asks, and three answers to it is how a test writes into the repository. |
| `tools/mockplane/seed.py` | FR-028's handover surface. It exists now, before feature 042, so the assertion that there is exactly one fictional deployment has something to assert against. |
| `tools/mockplane/dataset/profile.py` | See deviation 1. |
| `config/constants/fixtures.py` | `make check-constants` rejects an environment-variable name written outside the constants tier, and this feature declares nine. |

The whole of it lives under `tools/` because the root `AGENTS.md` defines that as
"repository tooling — NOT agent-callable, NOT packaged, NOT import-linted", which
is exactly what a development and test facility is. `fixtures/` is at the
repository root because the plan says so and the reason holds: it is read by the
console, by the seeder and by both test suites.

---

## 9. FR-028's demo seeder is an interface, not a seeder

**Planned.** T-048: "Wire feature 042's demo seeder to this dataset; it defines
none of its own."

**Done.** `tools/mockplane/seed.py` exposes `records_for_seeding()` — the dataset
flattened into rows with the demonstration label attached — and
`tests/architecture/test_one_fictional_deployment.py` asserts that the
organisation this dataset describes is named nowhere outside it.

**Why.** Feature 042 has not been built. There is no seeder to wire. What can be
done now, and was, is to make the interface exist and to make a second fictional
deployment fail the build the moment somebody writes one — which is the property
FR-030 actually asks for, and it holds today rather than when 042 lands.

---

## Not deviations, recorded because they look like they might be

- **`degraded` and `scale` hold no committed files.** `degraded` is `populated`
  plus a declaration of which endpoints misbehave; `scale` is generated from a
  fixed seed. Both are what FR-020 and NFR-002 ask for, and a test asserts each
  stays that way — duplicating forty files into `degraded` is how the two drift.
- **`scale` keeps the declared runs and resources and adds to them.** The first
  version renumbered everything, and ten thousand broken references followed:
  the approvals, episodes and audit trail underneath it name those runs. It is
  the same deployment with more in it, not a parallel one.
- **The write endpoints' fixtures are written against the document rather than
  captured.** A capture that posted an investigation to somebody's deployment
  would be a capture that changed the thing it was measuring, so `capture_gateway`
  records reads only and reports every write as missed with that reason. The
  referential check skips those records for the same reason: a write's answer
  describes a state that follows a mutation the fixture set does not contain.
- **`fixtures/contract/openapi.json` is 134 KB of the 4 MB budget.** It is
  generated, it is checked for drift, and it is the thing every fixture is
  measured against. Committing it is the point.
