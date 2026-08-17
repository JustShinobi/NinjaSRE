# Adding an integration

Everything in this document exists to make one number true: a typical REST
vendor goes from nothing to a passing contract suite in about two hours, and
adding it edits zero existing files.

Both halves matter. The first is what makes a catalogue of integrations a plan
rather than a wish. The second is what makes them addable *concurrently* — a
central registry would be a merge conflict on every pull request, and the line
somebody eventually forgets is the one that makes an integration invisible while
everything reports healthy.

## Start here

```bash
uv run python tools/scaffold_integration.py <vendor> --domain <domain>
```

Nine files, no edits. It prints what it deliberately did not decide; read that
list, because the two items at the top are the ones that make the difference
between an integration that works and one that reports that it does.

## The seven artefacts

Every integration ships all seven. `make verify` fails naming both the
integration and the artefact when one is missing, which is what makes "full
parity" a property rather than an aspiration.

| # | Artefact | Where | Without it |
|---|---|---|---|
| 1 | `schema.py` | `integrations/<vendor>/` | An operator configuring it is guessing at field names |
| 2 | `verifier.py` | `integrations/<vendor>/` | A wrong token is discovered during an incident |
| 3 | `client.py` | `integrations/<vendor>/` | Ad-hoc HTTP with its own retry, its own errors, and its own way past the proxy |
| 4 | `tools/` | `integrations/<vendor>/` | The agent cannot call it, so nothing in an investigation reaches this vendor |
| 5 | `SKILL.md` | `capabilities/skills/<vendor>/` | The agent knows the API and not the method |
| 6 | `docs.md` | `integrations/<vendor>/` | Setup is tribal knowledge, and the third team configures it wrongly |
| 7 | scenario | `tests/synthetic/integration_scenarios/<vendor>.py` | Nothing exercises it end to end, so it rots quietly |

Five of the seven are in the vendor's own package and two are not. Those two —
the skill and the scenario — are the ones a contributor forgets, which is the
argument for checking all seven in one place rather than letting each directory
check its own.

## What the framework gives you

**`integrations/_base/client.py`** is the only sanctioned path for an
authenticated external call. Inherit it and you get proxy routing, retry with
backoff, timeouts, rate-limit handling, bounded response bodies, and structured
errors. It has no constructor parameter for a credential and no attribute to
hold one: the wrong thing is unspellable rather than discouraged.

**`_base/pagination.py`** walks cursor, offset, and page-token styles, declared
per endpoint. A single vendor commonly cursors its search and offsets its list,
and there is no version of "the vendor's pagination style" that is true of both.
The difference that matters is where the walk *ends*: token styles end when the
vendor stops returning one, and offset ends on a short page, because nothing else
says it has.

**`_base/errors.py`** maps every failure onto seven categories — `auth`,
`permission`, `not_found`, `rate_limited`, `transient`, `invalid_request`,
`unavailable`. One table, so two integrations cannot disagree about what a 403
means and the loop's behaviour does not depend on which vendor it called.

**`_base/regions.py`** turns a multi-region vendor into data. The region map is
also the egress allow-list — one tuple, not two, because two would drift and the
drift widens egress.

**`_base/schema.py`** has the four credential shapes almost every vendor has:
bearer token, API key, basic auth, key pair.

**`_base/access.py`** is how a capability gets a client. One binding per
process, set by whoever composes the deployment; a capability either has it or
reports itself unavailable by name. A tool that built its own client from
ambient configuration would be one lookup away from acting on somebody else's
estate.

**`_verification/`** runs connectivity and each permission, and words the
result. **`_catalogue/`** discovers everything by walking, checks parity, and
records health.

## The two decisions the scaffold refuses to make

**The side-effect level.** It has no default, structurally: a tool that does not
say what it does to the world cannot be constructed. `read_sensitive` is right
whenever the result can carry what a user typed, which log bodies almost always
can. Anything above it needs an approval reason and a rollback plan.

**The permission list.** A guessed permission is worse than a missing one: the
verifier reports success for a credential that cannot do the job, and the
failure surfaces during an incident as a tool error with no sign that it was
knowable at setup time. Write the vendor's own names, say what each grants, name
the capabilities that stop working without it, and say where it is granted.

## Verification, and the vendors that cannot be asked

A verifier answers two questions: does the credential work, and may it do what
the capabilities need. The second is where the effort pays, because a credential
that authenticates can still be scoped without one permission.

Reading a failure correctly is most of the work:

- **403** — the permission is missing. Name it.
- **404** — **the call was permitted.** The probe named an object that is not
  there, which is what makes probes cheap. Reporting it as a denial sends an
  operator into a permissions console after a policy that is already correct.
- **401** — nothing was learned about the permission, because the credential
  itself was rejected. It is *unchecked*, not denied.
- anything else — the check did not complete, and saying so is more useful than
  reporting "granted" because no denial arrived.

Some vendors cannot be asked what a credential may do. Then the probe is the
cheapest form of the read the capability itself makes, and the probe says so —
a permission that was inferred rather than reported is something the person
reading the result needs to know.

## The contract suite

One suite, parameterised over the discovered catalogue. Adding an integration
adds rows, never a file:

```bash
uv run pytest tests/contract/integrations
```

It asserts, per integration: parity, schema validity, that the schema and the
injection rule have not drifted, that every call routes through the proxy, that
no credential is reachable from the client, that failures map onto the shared
taxonomy, that each paginated endpoint declares a style the walker implements,
that the capabilities declare what selection and approval need, that the skill
directs tools that exist, that the documentation says what an operator has to
do, and that a scenario exercises it.

Two more checks run in the same gate:

```bash
make check-integrations        # parity and permission probes, no credentials needed
make check-integration-docs    # the generated catalogue page is current
```

## Live runs, and why a vendor's break does not fail your build

The contract suite runs against recorded responses, so it is fast and runs on
every change. Live runs are scheduled separately, and a failure there marks the
integration **degraded** rather than failing the build.

That is deliberate. A vendor's breaking change is not the operator's change,
they cannot fix it, and a red build across the whole catalogue tells them
nothing about which one broke — the pressure that creates is to disable the live
run, and then the drift is undetected rather than merely unfixed. Degrading
names the vendor and what stopped working, in the catalogue the console reads,
while everything else keeps running.

An integration nothing has run against is `unknown`, not `healthy`. A vendor
that broke and a vendor nobody checked are different facts.

## Methodology templates

Eleven domains, each carrying the investigative discipline of its class:

| Domain | Core discipline |
|---|---|
| `logstore` | Statistics before samples |
| `metrics` | Baseline, change point, then correlate |
| `tracing` | Exemplar, span tree, latency boundary |
| `cloud_control_plane` | Recent changes, then state, then quotas |
| `database` | Sessions and locks before query plans |
| `vcs` | Deploy timeline, window diff, specific change |
| `cicd` | Last green, first failure, the delta between them |
| `ticketing` | Search before create; link rather than duplicate |
| `incident` | Timeline, MTTR context, prior similar incidents |
| `communication` | Structured posts that link to evidence |
| `data_platform` | Consumer lag and backlog before internals |

The scaffold's `--domain` selects one, and the skill it writes starts from that
template's ordering. Keep the ordering: it is the part that carries the
methodology rather than the shape.

## Before you open the pull request

```bash
make verify
```

The parity check, the contract suite, the skill binding, the token budgets, and
the credential boundary all cover the new integration from the moment it exists.
Nothing had to be registered for that to be true.
